"""Explicit experimental selection, mapping and dependency-first publication."""

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from neurofold.core.biological import (
    MappingCoverage,
    MappingStatus,
    ReferenceRepository,
    StructureDescriptor,
    StructureSelection,
)
from neurofold.core.provenance import ContentReference, Metadata, MetadataState
from neurofold.core.structures import (
    RevisionUnavailable,
    StructureImport,
    StructureImportRepository,
    StructureMapper,
    StructureParser,
    StructureProvider,
    StructureSourceChanged,
    UnsupportedStructure,
)


class StructureService:
    def __init__(
        self,
        provider: StructureProvider,
        references: ReferenceRepository,
        parser: StructureParser,
        mapper: StructureMapper,
        repository: StructureImportRepository,
        *,
        new_id: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self.provider, self.references, self.parser = provider, references, parser
        self.mapper, self.repository, self.new_id = mapper, repository, new_id

    def import_selected(
        self,
        reference_id: str,
        entry_id: str,
        selection: StructureSelection,
        expected_source_revision: Metadata,
    ) -> StructureImport:
        if (
            expected_source_revision.state is not MetadataState.PRESENT
            or not isinstance(expected_source_revision.value, str)
        ):
            raise RevisionUnavailable("Inspect a known source revision before import")
        reference = self.references.get(reference_id)
        source = self.provider.inspect(
            reference, entry_id, selection.label_asym_id, fresh=True
        )
        revision = source.summary.source_revision.value
        if not isinstance(revision, str):
            raise RevisionUnavailable("Authoritative source revision unavailable")
        if revision != expected_source_revision.value:
            raise StructureSourceChanged(expected_source_revision.value, revision)
        if (
            source.summary.entity_id,
            source.summary.label_asym_id,
            source.summary.auth_asym_id,
        ) != (selection.entity_id, selection.label_asym_id, selection.auth_asym_id):
            raise UnsupportedStructure(
                "Selected entity/instance differs from authoritative metadata"
            )
        download = self.provider.download(entry_id, revision)
        parsed = self.parser.parse(download.decoded, source.summary, selection)
        structure_id = self.new_id()
        mapping, alignment = self.mapper.map(
            reference, structure_id, download, selection, parsed
        )
        # Check after all parsing/alignment work; never publish from stale metadata.
        final_check = self.provider.revalidate(entry_id, revision)
        descriptor = StructureDescriptor(
            structure_id=structure_id,
            raw_artifact=download.receipt.raw_artifact,
            evidence=download.receipt.raw_artifact.evidence,
            selection=selection,
            source=replace(
                source.summary,
                mapped_coverage=MappingCoverage(
                    mapped_positions=sum(
                        row.status
                        in (
                            MappingStatus.EXACT,
                            MappingStatus.MISMATCH,
                            MappingStatus.UNOBSERVED,
                        )
                        for row in mapping.rows
                    ),
                    reference_length=len(reference.protein.sequence),
                ),
            ),
            mapping=ContentReference(
                record_id=mapping.mapping_id, content_hash=mapping.content_hash
            ),
        )
        record = StructureImport(
            descriptor=descriptor,
            mapping=mapping,
            reference=ContentReference(
                record_id=reference.reference_id, content_hash=reference.content_hash
            ),
            checks=source.checks + (download.check, final_check),
            parsing=parsed.details,
            alignment=alignment,
        )
        record.validate_reference(reference)
        self.repository.publish_import(record)
        return record

    def get(self, structure_id: str) -> StructureImport:
        return self.repository.get_import(structure_id)
