"""Offline pinned-reference orchestration; no HTTP, providers or concrete stores."""

from neurofold.core.biological import ReferenceRepository
from neurofold.core.errors import ArchiveIntegrityError
from neurofold.core.provenance import ContentHash, HashEncoding
from neurofold.core.variants import (
    VariantDefinition,
    VariantError,
    VariantErrorCode,
    VariantPublication,
    VariantRepository,
    define_variant,
    parse_substitution,
)


class VariantService:
    def __init__(
        self, references: ReferenceRepository, variants: VariantRepository
    ) -> None:
        self.references, self.variants = references, variants

    def create(
        self, reference_id: str, expected_reference_sha256: str, notation: str
    ) -> VariantPublication:
        # Deterministic precedence: ID, hash representation, notation syntax,
        # reference resolution, expected hash, then unchanged M1 biology.
        if type(reference_id) is not str or not reference_id.strip():
            raise VariantError(
                VariantErrorCode.INVALID_VARIANT_INPUT, "Expected a reference ID"
            )
        try:
            reference_id.encode("utf-8")
        except UnicodeError as exc:
            raise VariantError(
                VariantErrorCode.INVALID_VARIANT_INPUT, "Reference ID must be UTF-8"
            ) from exc
        try:
            expected = ContentHash(
                sha256=expected_reference_sha256, encoding=HashEncoding.SEQUENCE
            )
        except (ValueError, TypeError) as exc:
            raise VariantError(
                VariantErrorCode.INVALID_EXPECTED_REFERENCE_HASH,
                "Expected exactly 64 lowercase hexadecimal SHA-256 characters",
            ) from exc
        substitution = parse_substitution(notation)
        try:
            reference = self.references.get(reference_id)
        except KeyError as exc:
            raise VariantError(
                VariantErrorCode.REFERENCE_NOT_FOUND,
                "Pinned reference not found",
                {"reference_id": reference_id},
            ) from exc
        except OSError as exc:
            raise ArchiveIntegrityError(
                "Cannot read pinned reference dependency"
            ) from exc
        if reference.reference_id != reference_id:
            raise ArchiveIntegrityError("Reference repository returned a different ID")
        if expected != reference.protein.sequence_hash:
            raise VariantError(
                VariantErrorCode.REFERENCE_HASH_MISMATCH,
                "Expected sequence hash differs from the actual pinned reference",
                {
                    "expected_reference_sha256": expected.sha256,
                    "actual_reference_sha256": reference.protein.sequence_hash.sha256,
                },
            )
        return self.variants.publish(define_variant(reference, substitution))

    def get(self, variant_id: str) -> VariantDefinition:
        return self.variants.get(variant_id)
