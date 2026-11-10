"""Durable immutable prediction graph over existing no-clobber archive primitives."""

import fcntl
import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.prediction_sqlite import SQLiteJobs
from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import sha256_bytes
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.orchestration import Publication, Registration
from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.prediction_outputs import (
    PredictionMapping,
    PredictionResult,
    SuccessfulPredictionProvenance,
    validate_publication,
)
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ArtifactStore,
    ContentReference,
)
from neurofold.core.variants import VariantDefinition


class ProposalResolver:
    def __init__(self, bundle: ChildBundle, retained: ArtifactStore) -> None:
        self.staged = {a.descriptor.artifact_id: a for a in bundle.artifacts}
        self.retained = retained

    def describe(self, artifact_id: str) -> ArtifactDescriptor:
        if artifact_id in self.staged:
            return self.staged[artifact_id].descriptor
        return self.retained.describe(artifact_id)

    def read(self, artifact_id: str) -> bytes:
        if artifact_id in self.staged:
            return self.staged[artifact_id].bytes()
        with self.retained.open(artifact_id) as source:
            return source.read(8 * 1024 * 1024 + 1)


def dependency_ids(manifest: SuccessfulPredictionProvenance) -> set[str]:
    references = [
        *manifest.raw_artifacts,
        *manifest.environment.dependency_locks,
        *(w.artifact for w in manifest.model.weights),
        *(
            a
            for aux in (manifest.msa, manifest.templates, manifest.constraints)
            for a in aux.resolved.artifacts
        ),
    ]
    if manifest.spec.code.patch is not None:
        references.append(manifest.spec.code.patch)
    return {r.record_id for r in references} | {
        manifest.source_receipt.raw_artifact.artifact_id
    }


class PredictionArchive:
    def __init__(self, root: Path, jobs: SQLiteJobs, source: ArtifactStore) -> None:
        self.store, self.jobs, self.source = FilesystemStore(root), jobs, source

    @contextmanager
    def lock(self) -> Iterator[None]:
        with (self.store.root / "publication.lock").open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _read(self, kind: str, identity: str) -> bytes:
        target = self.store._path(kind, identity)
        if target.is_symlink():
            raise ArchiveIntegrityError("Symlink prediction record")
        return self.store._read(kind, identity)

    def describe(self, artifact_id: str) -> ArtifactDescriptor:
        self._read("artifact", artifact_id)
        return self.store.describe(artifact_id)

    def read(self, artifact_id: str) -> bytes:
        self._read("artifact", artifact_id)
        with self.store.open(artifact_id) as source:
            return source.read()

    def register(
        self,
        intent_id: str,
        job: PredictionJob,
        bundle: ChildBundle,
        reference: ReferenceSnapshot,
        variant: VariantDefinition | None,
        now: str,
    ) -> Publication:
        resolver = ProposalResolver(bundle, self.source)
        assert job.attempt is not None
        validate_publication(
            job=job,
            result=bundle.result,
            manifest=bundle.manifest,
            reference=reference,
            variant=variant,
            profile=job.spec.profile,
            resolver=resolver,
            expected_version=job.version,
            attempt_id=job.attempt.attempt_id,
            fence=job.attempt.fence,
            now=now,
        )
        ids = dependency_ids(bundle.manifest)
        if not set(resolver.staged) <= ids:
            raise ArchiveIntegrityError("Uninventoried staged output")
        graph: list[Registration] = []
        for identity in sorted(ids):
            descriptor, data = resolver.describe(identity), resolver.read(identity)
            self.store.publish_artifact(io.BytesIO(data), descriptor=descriptor)
            if self.describe(identity) != descriptor or self.read(identity) != data:
                raise ArchiveIntegrityError("Registered artifact changed")
            graph.append(
                Registration(
                    "artifact", identity, descriptor.content_hash.sha256, len(data)
                )
            )
        records = [
            ("reference", reference.reference_id, reference.to_json()),
            *([("variant", variant.variant_id, variant.to_json())] if variant else []),
            *(
                ("mapping", s.mapping.mapping_id, s.mapping.to_json())
                for s in bundle.result.samples
            ),
            ("manifest", bundle.manifest.manifest_id, bundle.manifest.to_json()),
            ("result", bundle.result.result_id, bundle.result.to_json()),
        ]
        for kind, identity, data in records:
            self.store._publish(kind, identity, data)
            if self._read(kind, identity) != data:
                raise ArchiveIntegrityError("Registered record changed")
            graph.append(Registration(kind, identity, sha256_bytes(data), len(data)))
        return Publication(
            intent_id,
            job,
            ContentReference(
                record_id=bundle.result.result_id,
                content_hash=bundle.result.content_hash,
            ),
            ContentReference(
                record_id=bundle.manifest.manifest_id,
                content_hash=bundle.manifest.content_hash,
            ),
            tuple(graph),
            now,
        )

    def verify(
        self, job: PredictionJob
    ) -> tuple[PredictionResult, SuccessfulPredictionProvenance]:
        try:
            with self.lock():
                return self._verify(job)
        except (KeyError, ValueError, OSError) as exc:
            raise ArchiveIntegrityError("Retained prediction graph damaged") from exc

    def _verify(
        self, job: PredictionJob
    ) -> tuple[PredictionResult, SuccessfulPredictionProvenance]:
        if job.state != "succeeded" or job.result is None or job.manifest is None:
            raise ArchiveIntegrityError("Not a retained success")
        graph = self.jobs.graph(job.job_id)
        for kind, identity, sha, size in graph:
            data = (
                self.read(identity)
                if kind == "artifact"
                else self._read(kind, identity)
            )
            if len(data) != size or sha256_bytes(data) != sha:
                raise ArchiveIntegrityError("Retained graph mismatch")
        result = PredictionResult.from_json(self._read("result", job.result.record_id))
        manifest = SuccessfulPredictionProvenance.from_json(
            self._read("manifest", job.manifest.record_id)
        )
        if (
            result.content_hash != job.result.content_hash
            or manifest.content_hash != job.manifest.content_hash
        ):
            raise ArchiveIntegrityError("Retained roots mismatch")
        reference = ReferenceSnapshot.from_json(
            self._read("reference", job.spec.reference.record_id)
        )
        variant = (
            VariantDefinition.from_json(
                self._read("variant", job.spec.variant.record_id)
            )
            if job.spec.variant
            else None
        )
        expected = {("artifact", i) for i in dependency_ids(manifest)} | {
            ("reference", reference.reference_id),
            ("result", result.result_id),
            ("manifest", manifest.manifest_id),
            *(("mapping", s.mapping.mapping_id) for s in result.samples),
        }
        if variant:
            expected.add(("variant", variant.variant_id))
        if {(k, i) for k, i, _, _ in graph} != expected or len(graph) != len(expected):
            raise ArchiveIntegrityError("Incomplete retained registration graph")
        for sample in result.samples:
            if (
                PredictionMapping.from_json(
                    self._read("mapping", sample.mapping.mapping_id)
                )
                != sample.mapping
            ):
                raise ArchiveIntegrityError("Mapping registration mismatch")
        # Recheck M1 against the historical validated running snapshot, at its own
        # end time, while final ownership was separately checked at actual commit.
        proposed = replace(
            job,
            state="running",
            version=job.version - 1,
            stage="validating",
            ended_at=None,
            result=None,
            manifest=None,
        )
        assert proposed.attempt is not None and job.ended_at is not None
        validate_publication(
            job=proposed,
            result=result,
            manifest=manifest,
            reference=reference,
            variant=variant,
            profile=job.spec.profile,
            resolver=self,
            expected_version=proposed.version,
            attempt_id=proposed.attempt.attempt_id,
            fence=proposed.attempt.fence,
            now=job.ended_at,
        )
        return result, manifest

    def artifact(self, job: PredictionJob, artifact_id: str) -> tuple[bytes, str]:
        _, manifest = self.verify(job)
        if artifact_id not in dependency_ids(manifest):
            raise KeyError(artifact_id)
        return self.read(artifact_id), self.describe(artifact_id).media_type
