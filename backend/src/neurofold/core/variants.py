"""NF-03 sequence hypotheses and reference-aware immutable definition contracts.

Pure standard-library logic: no structure numbering, filesystem I/O or HTTP.
Validation/error precedence and persisted identity: docs/variants.md.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal, Protocol, Self

from neurofold.core._contracts import Contract
from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import (
    MAX_SAFE_INTEGER,
    CanonicalObject,
    sequence_sha256,
    sha256_bytes,
)
from neurofold.core.provenance import ContentHash, HashEncoding, Metadata, _text

CANONICAL_AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
NOTATION_VERSION: Literal["nf-substitution/1"] = "nf-substitution/1"
MAX_NOTATION_LENGTH = len(str(MAX_SAFE_INTEGER)) + 2
_NOTATION = re.compile(r"([ACDEFGHIKLMNPQRSTVWY])([1-9][0-9]*)([ACDEFGHIKLMNPQRSTVWY])")


class VariantErrorCode(StrEnum):
    INVALID_NOTATION = "INVALID_NOTATION"
    POSITION_OUT_OF_RANGE = "POSITION_OUT_OF_RANGE"
    REFERENCE_MISMATCH = "REFERENCE_MISMATCH"
    NO_OP_SUBSTITUTION = "NO_OP_SUBSTITUTION"
    UNSUPPORTED_REFERENCE_ALPHABET = "UNSUPPORTED_REFERENCE_ALPHABET"
    INVALID_VARIANT_INPUT = "INVALID_VARIANT_INPUT"
    INVALID_DIFFERENCE_INPUT = "INVALID_DIFFERENCE_INPUT"
    SEQUENCE_LENGTH_MISMATCH = "SEQUENCE_LENGTH_MISMATCH"
    INVALID_VARIANT_RESULT = "INVALID_VARIANT_RESULT"
    INVALID_VARIANT_DEFINITION = "INVALID_VARIANT_DEFINITION"
    INVALID_EXPECTED_REFERENCE_HASH = "INVALID_EXPECTED_REFERENCE_HASH"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    REFERENCE_HASH_MISMATCH = "REFERENCE_HASH_MISMATCH"


class VariantError(ValueError):
    """Stable domain code and immutable detail snapshot, independent of HTTP."""

    def __init__(
        self,
        code: VariantErrorCode,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self._details = CanonicalObject.from_value(details if details else {})

    @property
    def details(self) -> dict[str, object]:
        return self._details.to_dict()


class _VariantRecord(Contract):
    """Use the existing strict codec, translating invalid inputs to domain errors."""

    _error_code: ClassVar[VariantErrorCode]

    def __post_init__(self) -> None:
        try:
            super().__post_init__()
        except VariantError:
            raise
        except (ValueError, TypeError) as exc:
            raise VariantError(self._error_code, str(exc)) from exc

    @classmethod
    def from_dict(cls, value: object) -> Self:
        try:
            return super().from_dict(value)
        except VariantError:
            raise
        except (ValueError, TypeError) as exc:
            raise VariantError(cls._error_code, str(exc)) from exc

    @classmethod
    def from_json(cls, data: bytes) -> Self:
        if type(data) is not bytes:
            raise VariantError(cls._error_code, "Expected immutable JSON bytes")
        try:
            return super().from_json(data)
        except VariantError:
            raise
        except (ValueError, TypeError) as exc:
            raise VariantError(cls._error_code, str(exc)) from exc


@dataclass(frozen=True, kw_only=True)
class Substitution(_VariantRecord):
    """Representable request; reference-dependent checks also reject no-ops."""

    _error_code = VariantErrorCode.INVALID_NOTATION
    reference_aa: str
    position: int
    alternate_aa: str
    notation_version: Literal["nf-substitution/1"] = NOTATION_VERSION

    def _validate(self) -> None:
        for name, residue in (
            ("reference_aa", self.reference_aa),
            ("alternate_aa", self.alternate_aa),
        ):
            if len(residue) != 1 or residue not in CANONICAL_AMINO_ACIDS:
                raise VariantError(
                    self._error_code,
                    "Expected a single canonical uppercase amino acid",
                    {"field": name},
                )
        if not 1 <= self.position <= MAX_SAFE_INTEGER:
            raise VariantError(
                self._error_code,
                "Position must be a positive safe integer (1..9007199254740991)",
            )

    @property
    def notation(self) -> str:
        return f"{self.reference_aa}{self.position}{self.alternate_aa}"


@dataclass(frozen=True, kw_only=True)
class SequenceDifference(_VariantRecord):
    """One exact unequal symbol pair; comparison itself is alphabet-independent."""

    _error_code = VariantErrorCode.INVALID_DIFFERENCE_INPUT
    position: int
    reference_aa: str
    alternate_aa: str

    def _validate(self) -> None:
        if (
            not 1 <= self.position <= MAX_SAFE_INTEGER
            or len(self.reference_aa) != 1
            or len(self.alternate_aa) != 1
            or self.reference_aa == self.alternate_aa
        ):
            raise VariantError(
                self._error_code,
                "Expected one unequal symbol pair at a positive position",
            )


def parse_substitution(notation: object) -> Substitution:
    """Strict NeuroFold compact notation, bounded before integer conversion."""
    if type(notation) is not str or not 3 <= len(notation) <= MAX_NOTATION_LENGTH:
        raise VariantError(
            VariantErrorCode.INVALID_NOTATION,
            "Expected compact substitution notation of 3..18 ASCII characters",
        )
    match = _NOTATION.fullmatch(notation)
    if match is None:
        raise VariantError(
            VariantErrorCode.INVALID_NOTATION,
            "Expected canonical uppercase residues and a positive position",
        )
    return Substitution(
        reference_aa=match[1], position=int(match[2]), alternate_aa=match[3]
    )


def validate_substitution(
    reference: ReferenceSnapshot, substitution: Substitution
) -> None:
    """Check full alphabet, position, actual reference residue, then no-op."""
    if (
        type(reference) is not ReferenceSnapshot
        or type(substitution) is not Substitution
    ):
        raise VariantError(
            VariantErrorCode.INVALID_VARIANT_INPUT,
            "Expected a pinned ReferenceSnapshot and structured Substitution",
        )
    sequence = reference.protein.sequence
    affected = [
        {"position": position, "symbol": symbol}
        for position, symbol in enumerate(sequence, start=1)
        if symbol not in CANONICAL_AMINO_ACIDS
    ]
    if affected:
        raise VariantError(
            VariantErrorCode.UNSUPPORTED_REFERENCE_ALPHABET,
            "The entire pinned reference must use the twenty canonical amino acids",
            {"affected_residues": affected},
        )
    position = substitution.position
    if position > len(sequence):
        raise VariantError(
            VariantErrorCode.POSITION_OUT_OF_RANGE,
            "Position exceeds the complete pinned reference sequence",
            {"position": position, "reference_length": len(sequence)},
        )
    actual = sequence[position - 1]
    if actual != substitution.reference_aa:
        raise VariantError(
            VariantErrorCode.REFERENCE_MISMATCH,
            "Requested reference residue differs from the actual pinned residue",
            {
                "position": position,
                "requested_reference_aa": substitution.reference_aa,
                "actual_reference_aa": actual,
            },
        )
    if substitution.reference_aa == substitution.alternate_aa:
        raise VariantError(
            VariantErrorCode.NO_OP_SUBSTITUTION,
            "A substitution must change the reference residue",
            {
                "position": position,
                "reference_aa": substitution.reference_aa,
                "alternate_aa": substitution.alternate_aa,
            },
        )


def sequence_difference(
    reference_sequence: str, alternate_sequence: str
) -> tuple[SequenceDifference, ...]:
    """Exact equal-length comparison; return zero/all changes, never align."""
    if type(reference_sequence) is not str or type(alternate_sequence) is not str:
        raise VariantError(
            VariantErrorCode.INVALID_DIFFERENCE_INPUT, "Expected exact sequence strings"
        )
    try:
        reference_sequence.encode("utf-8")
        alternate_sequence.encode("utf-8")
    except UnicodeError as exc:
        raise VariantError(
            VariantErrorCode.INVALID_DIFFERENCE_INPUT,
            "Sequence strings must be representable in UTF-8",
        ) from exc
    if len(reference_sequence) != len(alternate_sequence):
        raise VariantError(
            VariantErrorCode.SEQUENCE_LENGTH_MISMATCH,
            "Exact sequence comparison requires equal lengths",
            {
                "reference_length": len(reference_sequence),
                "alternate_length": len(alternate_sequence),
            },
        )
    return tuple(
        SequenceDifference(
            position=position, reference_aa=reference, alternate_aa=other
        )
        for position, (reference, other) in enumerate(
            zip(reference_sequence, alternate_sequence, strict=True), start=1
        )
        if reference != other
    )


def _substituted_sequence(reference: str, substitution: Substitution) -> str:
    position = substitution.position
    return reference[: position - 1] + substitution.alternate_aa + reference[position:]


@dataclass(frozen=True, kw_only=True)
class SubstitutionResult(_VariantRecord):
    """In-memory sequence hypothesis, not M2's persisted VariantDefinition."""

    _error_code = VariantErrorCode.INVALID_VARIANT_RESULT
    reference: ReferenceSnapshot
    substitution: Substitution
    sequence: str
    sequence_hash: ContentHash
    differences: tuple[SequenceDifference, ...]
    interpretation_kind: Literal["hypothesis"] = "hypothesis"

    @property
    def sequence_length(self) -> int:
        return len(self.sequence)

    def _validate(self) -> None:
        validate_substitution(self.reference, self.substitution)
        original = self.reference.protein.sequence
        if self.sequence != _substituted_sequence(original, self.substitution):
            raise VariantError(
                self._error_code, "Result sequence is not the exact substitution"
            )
        differences = sequence_difference(original, self.sequence)
        if (
            len(differences) != 1
            or self.differences != differences
            or self.sequence_hash.encoding is not HashEncoding.SEQUENCE
            or self.sequence_hash.sha256 != sequence_sha256(self.sequence)
        ):
            raise VariantError(
                self._error_code,
                "Result must contain the exact single substitution/hash",
            )


def apply_substitution(
    reference: ReferenceSnapshot, substitution: Substitution
) -> SubstitutionResult:
    """Construct precisely one change, preserving the pinned reference object."""
    validate_substitution(reference, substitution)
    sequence = _substituted_sequence(reference.protein.sequence, substitution)
    return SubstitutionResult(
        reference=reference,
        substitution=substitution,
        sequence=sequence,
        sequence_hash=ContentHash(
            sha256=sequence_sha256(sequence), encoding=HashEncoding.SEQUENCE
        ),
        differences=sequence_difference(reference.protein.sequence, sequence),
    )


VARIANT_SCHEMA_VERSION: Literal["neurofold-variant/1"] = "neurofold-variant/1"


def variant_identity_document(
    *,
    reference_id: str,
    reference_sequence_sha256: str,
    substitution: Substitution,
) -> CanonicalObject:
    """Exactly the NF-03 four-field document, without an identity envelope."""
    if type(reference_id) is not str or type(substitution) is not Substitution:
        raise VariantError(
            VariantErrorCode.INVALID_VARIANT_DEFINITION, "Invalid identity fields"
        )
    try:
        _text(reference_id)
        ContentHash(sha256=reference_sequence_sha256, encoding=HashEncoding.SEQUENCE)
    except (ValueError, TypeError) as exc:
        raise VariantError(
            VariantErrorCode.INVALID_VARIANT_DEFINITION, "Invalid identity fields"
        ) from exc
    return CanonicalObject.from_value(
        {
            "schema_version": VARIANT_SCHEMA_VERSION,
            "reference_id": reference_id,
            "reference_sequence_sha256": reference_sequence_sha256,
            "substitution": substitution.to_dict(),
        }
    )


@dataclass(frozen=True, kw_only=True)
class VariantDefinition(_VariantRecord):
    """Immutable persisted hypothesis; validate_reference checks its dependency."""

    _error_code = VariantErrorCode.INVALID_VARIANT_DEFINITION
    schema_version: Literal["neurofold-variant/1"] = VARIANT_SCHEMA_VERSION
    variant_id: str
    reference_id: str
    reference_sequence_sha256: str
    reference_content_hash: ContentHash
    reference_accession: str
    reference_taxon_id: int
    reference_sequence_version: Metadata
    reference_entry_version: Metadata
    substitution: Substitution
    notation: str
    sequence: str
    sequence_hash: ContentHash
    sequence_length: int
    differences: tuple[SequenceDifference, ...]
    interpretation_kind: Literal["hypothesis"] = "hypothesis"

    @property
    def identity_document(self) -> CanonicalObject:
        return variant_identity_document(
            reference_id=self.reference_id,
            reference_sequence_sha256=self.reference_sequence_sha256,
            substitution=self.substitution,
        )

    def _validate(self) -> None:
        if self.variant_id != "variant-" + sha256_bytes(self.identity_document.data):
            raise ValueError("Variant content identity mismatch")
        if (
            self.reference_content_hash.encoding is not HashEncoding.CANONICAL_JSON
            or self.reference_taxon_id <= 0
            or self.notation != self.substitution.notation
            or self.sequence_length != len(self.sequence)
            or self.sequence_hash.encoding is not HashEncoding.SEQUENCE
            or self.sequence_hash.sha256 != sequence_sha256(self.sequence)
            or self.differences
            != (
                SequenceDifference(
                    position=self.substitution.position,
                    reference_aa=self.substitution.reference_aa,
                    alternate_aa=self.substitution.alternate_aa,
                ),
            )
        ):
            raise ValueError("Invalid variant metadata or derived fields")

    def validate_reference(self, reference: ReferenceSnapshot) -> None:
        """Independently derive every retained field from the actual snapshot."""
        result = apply_substitution(reference, self.substitution)
        if self != _definition_from_result(result):
            raise VariantError(
                self._error_code,
                "Variant does not match the pinned reference and exact derivation",
            )


def _definition_from_result(result: SubstitutionResult) -> VariantDefinition:
    reference = result.reference
    identity = variant_identity_document(
        reference_id=reference.reference_id,
        reference_sequence_sha256=reference.protein.sequence_hash.sha256,
        substitution=result.substitution,
    )
    taxon = reference.protein.summary.taxon_id.value
    assert type(taxon) is int  # ReferenceSnapshot guarantees a present taxon.
    return VariantDefinition(
        variant_id="variant-" + sha256_bytes(identity.data),
        reference_id=reference.reference_id,
        reference_sequence_sha256=reference.protein.sequence_hash.sha256,
        reference_content_hash=reference.content_hash,
        reference_accession=reference.protein.summary.accession,
        reference_taxon_id=taxon,
        reference_sequence_version=reference.protein.source_receipt.sequence_version,
        reference_entry_version=reference.protein.source_receipt.entry_version,
        substitution=result.substitution,
        notation=result.substitution.notation,
        sequence=result.sequence,
        sequence_hash=result.sequence_hash,
        sequence_length=result.sequence_length,
        differences=result.differences,
    )


def define_variant(
    reference: ReferenceSnapshot, substitution: Substitution
) -> VariantDefinition:
    """Use unchanged M1 validation and construction before assigning identity."""
    return _definition_from_result(apply_substitution(reference, substitution))


@dataclass(frozen=True, kw_only=True)
class VariantPublication(Contract):
    """Transient repository outcome; never stored inside the definition."""

    definition: VariantDefinition
    created: bool


class VariantRepository(Protocol):
    """Offline immutable definitions with fully verified reference dependencies.

    get: KeyError only for unknown IDs; ArchiveIntegrityError for retained damage.
    publish: identical repeats return created=False; ArchiveConflict for different
    valid content, ArchiveIntegrityError for corrupt targets/dependencies, and
    ArchivePublicationError for failed I/O (complete publication may be visible).
    """

    def get(self, variant_id: str) -> VariantDefinition: ...

    def publish(self, definition: VariantDefinition) -> VariantPublication: ...
