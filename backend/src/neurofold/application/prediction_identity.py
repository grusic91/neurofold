"""Assign output ownership before publication, preserving raw scientific bytes."""

from dataclasses import replace

from neurofold.core.canonical import canonical_json, sha256_bytes
from neurofold.core.errors import InvalidChildOutput
from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_jobs import PredictionJob
from neurofold.core.provenance import ArtifactDescriptor, ContentHash, ContentReference


def output_id(job: PredictionJob, kind: str, local: str) -> str:
    assert job.attempt is not None
    return "output-" + sha256_bytes(
        canonical_json(
            [
                "neurofold-output/1",
                job.job_id,
                job.attempt.attempt_id,
                kind,
                local,
            ]
        )
    )


def scope_outputs(job: PredictionJob, bundle: ChildBundle) -> ChildBundle:
    # Only outputs are owned here. Source receipts, locks, weights and inputs keep
    # their retained identities. The child's local IDs need only be bundle-unique.
    if (
        bundle.manifest.samples != bundle.result.samples
        or bundle.manifest.returned_sample_ids
        != tuple(s.sample_id for s in bundle.result.samples)
        or bundle.manifest.result_id != bundle.result.result_id
        or bundle.manifest.raw_artifacts != bundle.result.raw_artifacts
    ):
        raise InvalidChildOutput("Child output linkage mismatch")
    outputs = {r.record_id for r in bundle.result.raw_artifacts}

    def raw(reference: ContentReference) -> ContentReference:
        return (
            replace(
                reference, record_id=output_id(job, "artifact", reference.record_id)
            )
            if reference.record_id in outputs
            else reference
        )

    mapping_hashes: dict[ContentHash, ContentHash] = {}
    samples = []
    for sample in bundle.result.samples:
        mapping = replace(
            sample.mapping,
            mapping_id=output_id(job, "mapping", sample.mapping.mapping_id),
            sample_id=output_id(job, "sample", sample.sample_id),
            structure=raw(sample.structure),
        )
        mapping_hashes[sample.mapping.content_hash] = mapping.content_hash
        samples.append(
            replace(
                sample,
                sample_id=mapping.sample_id,
                mapping=mapping,
                structure=mapping.structure,
                raw_artifacts=tuple(raw(r) for r in sample.raw_artifacts),
                confidence=tuple(
                    replace(
                        c,
                        artifact=raw(c.artifact) if c.artifact else None,
                        mapping=ContentReference(
                            record_id=mapping.mapping_id,
                            content_hash=mapping.content_hash,
                        )
                        if c.mapping
                        else None,
                    )
                    for c in sample.confidence
                ),
            )
        )

    def descriptor(value: ArtifactDescriptor) -> ArtifactDescriptor:
        return replace(
            value,
            artifact_id=output_id(job, "artifact", value.artifact_id)
            if value.artifact_id in outputs
            else value.artifact_id,
            parents=tuple(
                sorted(
                    (mapping_hashes.get(parent, parent) for parent in value.parents),
                    key=lambda parent: f"{parent.encoding}:{parent.sha256}",
                )
            ),
        )

    manifest = replace(
        bundle.manifest,
        manifest_id=output_id(job, "manifest", bundle.manifest.manifest_id),
        result_id=output_id(job, "result", bundle.result.result_id),
        samples=tuple(samples),
        returned_sample_ids=tuple(s.sample_id for s in samples),
        raw_artifacts=tuple(raw(r) for r in bundle.manifest.raw_artifacts),
        artifacts=tuple(descriptor(a) for a in bundle.manifest.artifacts),
    )
    result = replace(
        bundle.result,
        result_id=manifest.result_id,
        manifest=ContentReference(
            record_id=manifest.manifest_id, content_hash=manifest.content_hash
        ),
        samples=tuple(samples),
        raw_artifacts=tuple(raw(r) for r in bundle.result.raw_artifacts),
    )
    return replace(
        bundle,
        result=result,
        manifest=manifest,
        artifacts=tuple(
            replace(a, descriptor=descriptor(a.descriptor)) for a in bundle.artifacts
        ),
    )
