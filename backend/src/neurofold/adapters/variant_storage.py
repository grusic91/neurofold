"""Checksummed NF-03 definitions over the shared no-clobber filesystem archive."""

from neurofold.adapters.biological.storage import FilesystemStore, verified_read
from neurofold.core.biological import ReferenceRepository
from neurofold.core.canonical import canonical_json, parse_json, sha256_bytes
from neurofold.core.errors import (
    ArchiveConflict,
    ArchiveIntegrityError,
    ArchivePublicationError,
)
from neurofold.core.variants import VariantDefinition, VariantPublication


class FilesystemVariants:
    def __init__(self, store: FilesystemStore, references: ReferenceRepository) -> None:
        self.store, self.references = store, references

    def _validate(self, definition: VariantDefinition) -> None:
        try:
            reference = self.references.get(definition.reference_id)
        except KeyError as exc:
            raise ArchiveIntegrityError("Variant reference dependency missing") from exc
        except OSError as exc:
            raise ArchiveIntegrityError(
                "Cannot read variant reference dependency"
            ) from exc
        definition.validate_reference(reference)

    @verified_read
    def get(self, variant_id: str) -> VariantDefinition:
        try:
            if self.store._path("variant", variant_id).is_symlink():
                raise ArchiveIntegrityError("Symlink variant records are unsupported")
            data = self.store._read("variant", variant_id)
        except OSError as exc:
            raise ArchiveIntegrityError("Cannot read retained variant") from exc
        envelope = parse_json(data)
        if type(envelope) is not dict or set(envelope) != {"record", "sha256"}:
            raise ValueError("Invalid variant bundle")
        if sha256_bytes(canonical_json(envelope["record"])) != envelope["sha256"]:
            raise ValueError("Variant bundle checksum mismatch")
        definition = VariantDefinition.from_dict(envelope["record"])
        if definition.variant_id != variant_id:
            raise ValueError("Requested variant identity mismatch")
        self._validate(definition)
        return definition

    def publish(self, definition: VariantDefinition) -> VariantPublication:
        # Recheck the full contract and actual dependency before any write.
        definition = VariantDefinition.from_json(definition.to_json())
        self._validate(definition)
        try:
            retained = self.get(definition.variant_id)
        except KeyError:
            pass
        else:
            if retained != definition:
                raise ArchiveConflict("Conflicting immutable variant definition")
            return VariantPublication(definition=retained, created=False)
        try:
            created = self.store._publish(
                "variant",
                definition.variant_id,
                canonical_json(
                    {
                        "record": definition.to_dict(),
                        "sha256": sha256_bytes(definition.to_json()),
                    }
                ),
            )
        except ArchiveConflict:
            # A racing writer won. Verify damage before classifying a conflict;
            # corruption can never be a successful duplicate or a missing ID.
            self.get(definition.variant_id)
            raise
        except OSError as exc:
            target = self.store._path("variant", definition.variant_id)
            if target.exists() or target.is_symlink():
                self.get(definition.variant_id)
            raise ArchivePublicationError("Variant publication I/O failed") from exc
        retained = self.get(definition.variant_id)
        return VariantPublication(definition=retained, created=created)
