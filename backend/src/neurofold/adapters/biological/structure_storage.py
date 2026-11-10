"""Atomic descriptor/map/audit bundles over the existing immutable archive."""

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.core.biological import ResidueMap, StructureDescriptor
from neurofold.core.canonical import canonical_json, parse_json, sha256_bytes
from neurofold.core.provenance import Metadata
from neurofold.core.structures import StructureImport


class FilesystemStructures:
    def __init__(self, store: FilesystemStore) -> None:
        self.store = store

    def _validate(self, record: StructureImport) -> None:
        descriptor = record.descriptor
        try:
            reference = self.store.get(record.reference.record_id)
            record.validate_reference(reference)
            if (
                self.store.describe(descriptor.raw_artifact.artifact_id)
                != descriptor.raw_artifact
            ):
                raise ValueError("Structure artifact integrity failure")
            receipts = [
                self.store.get_receipt(check.source_receipt_id)
                for check in record.checks
            ]
        except KeyError as exc:
            raise ValueError("Structure import dependency missing") from exc
        if descriptor.source.source_receipt not in receipts:
            raise ValueError("Structure source receipt mismatch")
        if not any(
            receipt.raw_artifact == descriptor.raw_artifact for receipt in receipts
        ):
            raise ValueError("Original coordinate receipt missing")
        revision = descriptor.source.source_revision.value
        if revision is None or receipts[-1].entry_version.value != revision:
            raise ValueError("Final authoritative revision mismatch")
        if receipts[-1].query != descriptor.source.source_receipt.query:
            raise ValueError("Final revision check targets a different entry")

    def publish_import(self, record: StructureImport) -> None:
        self._validate(record)
        # Audit and map are in the same staged, fsynced, no-clobber bundle.
        self.store._publish(
            "structure",
            record.descriptor.structure_id,
            canonical_json(
                {"record": record.to_dict(), "sha256": sha256_bytes(record.to_json())}
            ),
        )

    def get_import(self, structure_id: str) -> StructureImport:
        envelope = parse_json(self.store._read("structure", structure_id))
        if not isinstance(envelope, dict) or set(envelope) != {"record", "sha256"}:
            raise ValueError("Invalid structure bundle")
        if sha256_bytes(canonical_json(envelope["record"])) != envelope["sha256"]:
            raise ValueError("Structure bundle checksum mismatch")
        record = StructureImport.from_dict(envelope["record"])
        if record.descriptor.structure_id != structure_id:
            raise ValueError("Structure identity mismatch")
        self._validate(record)
        return record

    def get(self, structure_id: str) -> StructureDescriptor:
        return self.get_import(structure_id).descriptor

    def get_mapping(self, mapping_id: str) -> ResidueMap:
        if not mapping_id.endswith(":map"):
            raise KeyError(mapping_id)
        record = self.get_import(mapping_id.removesuffix(":map"))
        if record.mapping.mapping_id != mapping_id:
            raise ValueError("Map identity mismatch")
        return record.mapping

    def publish(
        self, descriptor: StructureDescriptor, mapping: ResidueMap | Metadata
    ) -> None:
        # Protocol facade permits idempotent repeats of a complete import only.
        # A caller must supply the additive audit via publish_import initially.
        try:
            record = self.get_import(descriptor.structure_id)
        except KeyError as exc:
            raise ValueError(
                "Initial publication requires complete import audit"
            ) from exc
        if descriptor != record.descriptor or mapping != record.mapping:
            raise ValueError("Conflicting immutable structure/map write")
