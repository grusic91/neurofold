"""Read-side biological orchestration over injected core protocols."""

from neurofold.core.biological import (
    ExperimentalStructureCatalog,
    ProteinCatalog,
    ProteinPage,
    ProteinRecord,
    ReferenceRepository,
    StructurePage,
)
from neurofold.core.canonical import sha256_bytes
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.provenance import ArtifactDescriptor, ArtifactStore


class BiologicalService:
    def __init__(
        self,
        proteins: ProteinCatalog,
        structures: ExperimentalStructureCatalog,
        references: ReferenceRepository,
        artifacts: ArtifactStore,
    ) -> None:
        self.proteins, self.structures = proteins, structures
        self.references, self.artifacts = references, artifacts

    def search(
        self, *, gene: str, taxon_id: int | None, cursor: str | None, limit: int
    ) -> ProteinPage:
        return self.proteins.search(
            gene=gene, taxon_id=taxon_id, cursor=cursor, limit=limit
        )

    def protein(self, accession: str) -> ProteinRecord:
        return self.proteins.get(accession)

    def discover(
        self, reference_id: str, *, cursor: str | None, limit: int
    ) -> StructurePage:
        reference = self.references.get(reference_id)
        return self.structures.discover(reference, cursor=cursor, limit=limit)

    def artifact(self, artifact_id: str) -> tuple[ArtifactDescriptor, bytes]:
        descriptor = self.artifacts.describe(artifact_id)
        with self.artifacts.open(artifact_id) as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if (
            len(raw) != descriptor.byte_size
            or sha256_bytes(raw) != descriptor.content_hash.sha256
        ):
            raise ArchiveIntegrityError("Artifact size/checksum mismatch")
        return descriptor, raw
