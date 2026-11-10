"""Authored synthetic sequence hypotheses; no providers or molecular coordinates."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import MAX_SAFE_INTEGER, sequence_sha256
from neurofold.core.provenance import ContentHash, EvidenceKind, HashEncoding
from neurofold.core.variants import (
    SequenceDifference,
    Substitution,
    SubstitutionResult,
    VariantError,
    VariantErrorCode,
    apply_substitution,
    parse_substitution,
    sequence_difference,
    validate_substitution,
)

# Independent test alphabet and expected literals, not imported from production.
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"


def snapshot(sequence: str = "MACAG") -> ReferenceSnapshot:
    """Reuse frozen metadata; give authored sequence bytes their own receipt."""
    data: dict[str, Any] = json.loads(
        (Path(__file__).parent / "fixtures/biological-v1.json").read_bytes()
    )
    template = ReferenceSnapshot.from_dict(data["reference"])
    receipt = template.protein.source_receipt
    raw = sequence.encode("ascii")
    receipt = replace(
        receipt,
        receipt_id="synthetic-variant-reference-receipt",
        provider="synthetic-inline",
        query="fixture:test_variants.py:authored-sequence-bytes",
        raw_artifact=replace(
            receipt.raw_artifact,
            artifact_id="synthetic-variant-reference-raw",
            byte_size=len(raw),
            media_type="text/plain",
            content_hash=ContentHash(
                sha256=hashlib.sha256(raw).hexdigest(), encoding=HashEncoding.RAW
            ),
        ),
    )
    return replace(
        template,
        reference_id="synthetic-variant-reference",
        protein=replace(
            template.protein,
            sequence=sequence,
            sequence_hash=ContentHash(
                sha256=hashlib.sha256(raw).hexdigest(), encoding=HashEncoding.SEQUENCE
            ),
            summary=replace(
                template.protein.summary,
                sequence_length=len(sequence),
                source_receipt_id=receipt.receipt_id,
            ),
            source_receipt=receipt,
            normalization="Authored inline ASCII sequence bytes retained verbatim.",
        ),
    )


def test_exact_example_hashes_linkage_and_immutability() -> None:
    reference = snapshot()
    before = reference.to_json()
    reference_hash = reference.content_hash
    substitution = parse_substitution("A4V")
    assert substitution == Substitution(reference_aa="A", position=4, alternate_aa="V")
    assert substitution.notation_version == "nf-substitution/1"
    assert substitution.notation == "A4V"
    validate_substitution(reference, substitution)
    result = apply_substitution(reference, substitution)
    assert result.reference is reference
    assert result.substitution is substitution
    assert result.sequence == "MACVG"
    assert result.sequence_length == 5
    assert result.differences == (
        SequenceDifference(position=4, reference_aa="A", alternate_aa="V"),
    )
    assert result.differences[0].to_dict() == {
        "position": 4,
        "reference_aa": "A",
        "alternate_aa": "V",
    }
    assert result.sequence_hash.encoding is HashEncoding.SEQUENCE
    assert result.sequence_hash.sha256 == hashlib.sha256(b"MACVG").hexdigest()
    assert result.sequence_hash.sha256 == sequence_sha256(result.sequence)
    assert result.interpretation_kind == "hypothesis"
    assert (
        result.reference.protein.source_receipt.raw_artifact.evidence
        is EvidenceKind.SYNTHETIC
    )
    assert reference.protein.sequence == "MACAG"
    assert (
        reference.protein.sequence_hash.sha256 == hashlib.sha256(b"MACAG").hexdigest()
    )
    assert reference.to_json() == before
    assert reference.content_hash == reference_hash
    assert reference_hash.encoding is HashEncoding.CANONICAL_JSON
    for record, attribute, value in (
        (result, "sequence", "MACAG"),
        (substitution, "position", 1),
        (result.differences[0], "position", 1),
        (reference.protein, "sequence", "MACVG"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, attribute, value)
    exported = result.to_dict()
    exported["reference"] = {}
    assert reference.to_json() == before
    for record in (substitution, result.differences[0], result):
        assert type(record).from_dict(record.to_dict()) == record
        assert type(record).from_json(record.to_json()) == record


@pytest.mark.parametrize(("notation", "expected"), [("M1V", "VACAG"), ("G5W", "MACAW")])
def test_first_and_last_positions(notation: str, expected: str) -> None:
    result = apply_substitution(snapshot(), parse_substitution(notation))
    assert result.sequence == expected
    assert len(result.differences) == 1


@pytest.mark.parametrize(
    ("reference_aa", "alternate_aa"),
    [
        (first, second)
        for first in AMINO_ACIDS
        for second in AMINO_ACIDS
        if first != second
    ],
)
def test_all_twenty_residues(reference_aa: str, alternate_aa: str) -> None:
    substitution = parse_substitution(f"{reference_aa}1{alternate_aa}")
    result = apply_substitution(snapshot(reference_aa), substitution)
    assert result.sequence == alternate_aa
    assert result.differences == (
        SequenceDifference(
            position=1, reference_aa=reference_aa, alternate_aa=alternate_aa
        ),
    )


def test_deterministically_generated_sequences_preserve_exactly_one_change() -> None:
    for length in range(1, 13):
        sequence = "".join(
            AMINO_ACIDS[(index * 7 + length) % 20] for index in range(length)
        )
        reference = snapshot(sequence)
        for index, original in enumerate(sequence):
            alternate = AMINO_ACIDS[(AMINO_ACIDS.index(original) + 9) % 20]
            substitution = Substitution(
                reference_aa=original, position=index + 1, alternate_aa=alternate
            )
            result = apply_substitution(reference, substitution)
            assert len(result.sequence) == length
            assert result.sequence[:index] == sequence[:index]
            assert result.sequence[index] == alternate
            assert result.sequence[index + 1 :] == sequence[index + 1 :]
            assert [
                i + 1 for i in range(length) if sequence[i] != result.sequence[i]
            ] == [index + 1]
            assert (
                result.sequence_hash.sha256
                == hashlib.sha256(result.sequence.encode("ascii")).hexdigest()
            )


@pytest.mark.parametrize(
    ("notation", "code", "details"),
    [
        (
            "C4V",
            "REFERENCE_MISMATCH",
            {"position": 4, "requested_reference_aa": "C", "actual_reference_aa": "A"},
        ),
        (
            "A4A",
            "NO_OP_SUBSTITUTION",
            {"position": 4, "reference_aa": "A", "alternate_aa": "A"},
        ),
        ("A6V", "POSITION_OUT_OF_RANGE", {"position": 6, "reference_length": 5}),
        (
            "C4C",
            "REFERENCE_MISMATCH",
            {"position": 4, "requested_reference_aa": "C", "actual_reference_aa": "A"},
        ),
        ("A6A", "POSITION_OUT_OF_RANGE", {"position": 6, "reference_length": 5}),
    ],
)
def test_reference_failures_and_precedence(
    notation: str, code: str, details: dict[str, object]
) -> None:
    reference = snapshot()
    before = reference.to_json()
    for operation in (validate_substitution, apply_substitution):
        with pytest.raises(VariantError) as failure:
            operation(reference, parse_substitution(notation))
        assert failure.value.code == code
        assert failure.value.details == details
        assert str(failure.value)
        assert reference.to_json() == before


@pytest.mark.parametrize(
    "notation",
    [
        None,
        True,
        4,
        4.0,
        b"A4V",
        [],
        {},
        "",
        "A",
        "AV",
        "A0V",
        "A-1V",
        "A+1V",
        "A01V",
        "A4.0V",
        "A4e1V",
        "a4V",
        "A4v",
        " A4V",
        "A4V ",
        "A 4V",
        "A4V\n",
        "A4V\r\n",
        "A4V\t",
        "A4V\x00",
        "A4V A5W",
        "A4V;G5W",
        "A4del",
        "A4*",
        "A4X",
        "U4V",
        "B4V",
        "Z4V",
        "J4V",
        "O4V",
        "p.A4V",
        "Ａ4V",
        "A４V",
        "A٤V",
        "А4V",
        "A\u200b4V",
        "A4V\u00a0",
        "A" + "9" * 5000 + "V",
        "A9007199254740992V",
        "A9999999999999999V",
        "A10000000000000000V",
        "A\ud800V",
    ],
)
def test_strict_notation_rejected(notation: object) -> None:
    with pytest.raises(VariantError) as failure:
        parse_substitution(notation)
    assert failure.value.code is VariantErrorCode.INVALID_NOTATION


def test_maximum_representable_position_is_distinct_from_reference_length() -> None:
    substitution = parse_substitution("A9007199254740991V")
    assert substitution.position == MAX_SAFE_INTEGER
    assert Substitution.from_json(substitution.to_json()) == substitution
    with pytest.raises(VariantError) as failure:
        apply_substitution(snapshot(), substitution)
    assert failure.value.code is VariantErrorCode.POSITION_OUT_OF_RANGE


@pytest.mark.parametrize(
    "position",
    [
        True,
        False,
        4.0,
        "4",
        None,
        [],
        {},
        0,
        -1,
        MAX_SAFE_INTEGER + 1,
        pytest.param(10**5000, id="oversized-integer"),
    ],
)
def test_structured_position_invariants(position: Any) -> None:
    data: dict[str, Any] = {
        "reference_aa": "A",
        "position": position,
        "alternate_aa": "V",
        "notation_version": "nf-substitution/1",
    }
    constructors: list[Callable[[], object]] = [
        lambda: Substitution(**data),
        lambda: Substitution.from_dict(data),
    ]
    for create in constructors:
        with pytest.raises(VariantError) as failure:
            create()
        assert failure.value.code is VariantErrorCode.INVALID_NOTATION


@pytest.mark.parametrize("field", ["reference_aa", "alternate_aa"])
@pytest.mark.parametrize(
    "value", ["", "AA", "a", "X", "U", "*", " A", "Ａ", None, True, 4, ["A"]]
)
def test_structured_residue_invariants(field: str, value: object) -> None:
    data: dict[str, Any] = parse_substitution("A4V").to_dict()
    data[field] = value
    constructors: list[Callable[[], object]] = [
        lambda: Substitution(**data),
        lambda: Substitution.from_dict(data),
    ]
    for create in constructors:
        with pytest.raises(VariantError) as failure:
            create()
        assert failure.value.code is VariantErrorCode.INVALID_NOTATION


@pytest.mark.parametrize(
    "version", ["nf-substitution/2", "nf-substitution/1.1", None, 1]
)
def test_unsupported_notation_version(version: Any) -> None:
    with pytest.raises(VariantError) as failure:
        Substitution(
            reference_aa="A", position=4, alternate_aa="V", notation_version=version
        )
    assert failure.value.code is VariantErrorCode.INVALID_NOTATION
    data = parse_substitution("A4V").to_dict()
    data["notation_version"] = version
    with pytest.raises(VariantError):
        Substitution.from_dict(data)


@pytest.mark.parametrize("notation", ["A4V", "C4C", "A99A"])
def test_whole_reference_alphabet_precedes_other_failures(notation: str) -> None:
    reference = snapshot("MXCAGXU*-?")
    before = reference.to_json()
    expected = {
        "affected_residues": [
            {"position": 2, "symbol": "X"},
            {"position": 6, "symbol": "X"},
            {"position": 7, "symbol": "U"},
            {"position": 8, "symbol": "*"},
            {"position": 9, "symbol": "-"},
            {"position": 10, "symbol": "?"},
        ]
    }
    for operation in (validate_substitution, apply_substitution):
        with pytest.raises(VariantError) as failure:
            operation(reference, parse_substitution(notation))
        assert failure.value.code is VariantErrorCode.UNSUPPORTED_REFERENCE_ALPHABET
        assert failure.value.details == expected
        details = failure.value.details
        details["affected_residues"] = []
        assert failure.value.details == expected
        assert reference.to_json() == before


@pytest.mark.parametrize("symbol", ["B", "J", "O", "U", "X", "Z", "*", "-", "?"])
@pytest.mark.parametrize("position", [2, 4])
def test_noncanonical_symbols_at_or_away_from_selected_position(
    symbol: str, position: int
) -> None:
    sequence = "MACAG"
    sequence = sequence[: position - 1] + symbol + sequence[position:]
    with pytest.raises(VariantError) as failure:
        apply_substitution(snapshot(sequence), parse_substitution("A4V"))
    assert failure.value.code is VariantErrorCode.UNSUPPORTED_REFERENCE_ALPHABET
    assert failure.value.details == {
        "affected_residues": [{"position": position, "symbol": symbol}]
    }


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("", "", ()),
        ("MACAG", "MACAG", ()),
        (
            "MACAG",
            "MACVG",
            (SequenceDifference(position=4, reference_aa="A", alternate_aa="V"),),
        ),
        (
            "MACAG",
            "VACAW",
            (
                SequenceDifference(position=1, reference_aa="M", alternate_aa="V"),
                SequenceDifference(position=5, reference_aa="G", alternate_aa="W"),
            ),
        ),
        (
            "X?",
            "U*",
            (
                SequenceDifference(position=1, reference_aa="X", alternate_aa="U"),
                SequenceDifference(position=2, reference_aa="?", alternate_aa="*"),
            ),
        ),
        (
            "Aé",
            "Ae",
            (SequenceDifference(position=2, reference_aa="é", alternate_aa="e"),),
        ),
    ],
)
def test_difference_zero_one_multiple_and_exact_symbols(
    first: str, second: str, expected: tuple[SequenceDifference, ...]
) -> None:
    assert sequence_difference(first, second) == expected


@pytest.mark.parametrize(
    ("first", "second"), [("", "A"), ("A", ""), ("MACAG", "MACA"), ("MACA", "MACAG")]
)
def test_difference_rejects_unequal_lengths(first: str, second: str) -> None:
    with pytest.raises(VariantError) as failure:
        sequence_difference(first, second)
    assert failure.value.code is VariantErrorCode.SEQUENCE_LENGTH_MISMATCH
    assert failure.value.details == {
        "reference_length": len(first),
        "alternate_length": len(second),
    }


@pytest.mark.parametrize("value", [None, True, 1, 1.0, b"A", ["A"], "\ud800"])
def test_difference_rejects_invalid_inputs(value: Any) -> None:
    for first, second in ((value, "A"), ("A", value)):
        with pytest.raises(VariantError) as failure:
            sequence_difference(first, second)
        assert failure.value.code is VariantErrorCode.INVALID_DIFFERENCE_INPUT


def test_complete_142_residue_reference_is_independent_of_structural_coverage() -> None:
    # Authored alphabet repeat, unrelated to the operational public source pair.
    reference_sequence = "M" + AMINO_ACIDS * 7 + "A"
    hypothetical_structural_polymer = reference_sequence[:-1]
    assert len(reference_sequence) == 142
    assert len(hypothetical_structural_polymer) == 141
    reference = snapshot(reference_sequence)
    result = apply_substitution(reference, parse_substitution("A142V"))
    assert result.sequence == reference_sequence[:-1] + "V"
    assert result.sequence_length == 142
    assert result.differences == (
        SequenceDifference(position=142, reference_aa="A", alternate_aa="V"),
    )
    assert apply_substitution(reference, parse_substitution("M1W")).sequence[0] == "W"


@pytest.mark.parametrize("field", ["reference", "substitution"])
@pytest.mark.parametrize("value", [None, {}, "A4V", True])
def test_domain_functions_require_actual_records(field: str, value: Any) -> None:
    reference = value if field == "reference" else snapshot()
    substitution = value if field == "substitution" else parse_substitution("A4V")
    for operation in (validate_substitution, apply_substitution):
        with pytest.raises(VariantError) as failure:
            operation(reference, substitution)
        assert failure.value.code is VariantErrorCode.INVALID_VARIANT_INPUT


@pytest.mark.parametrize(
    "data",
    [
        {},
        None,
        [],
        {"reference_aa": "A", "position": 4, "alternate_aa": "V"},
        {
            "reference_aa": "A",
            "position": 4,
            "alternate_aa": "V",
            "notation_version": "nf-substitution/1",
            "extra": True,
        },
    ],
)
def test_substitution_codec_requires_every_field_and_rejects_unknowns(
    data: object,
) -> None:
    with pytest.raises(VariantError) as failure:
        Substitution.from_dict(data)
    assert failure.value.code is VariantErrorCode.INVALID_NOTATION


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"\xff",
        b'{"position":4,"position":5}',
        b'{"reference_aa":"A","position":true,"alternate_aa":"V","notation_version":"nf-substitution/1"}',
        b'{"reference_aa":"A","position":4.0,"alternate_aa":"V","notation_version":"nf-substitution/1"}',
        b'{"reference_aa":"A","position":9007199254740992,"alternate_aa":"V","notation_version":"nf-substitution/1"}',
        b'{"reference_aa":"A","position":'
        + b"9" * 5000
        + b',"alternate_aa":"V","notation_version":"nf-substitution/1"}',
    ],
)
def test_substitution_json_failures_are_typed(data: bytes) -> None:
    with pytest.raises(VariantError) as failure:
        Substitution.from_json(data)
    assert failure.value.code is VariantErrorCode.INVALID_NOTATION


def test_json_codec_rejects_nonbytes() -> None:
    with pytest.raises(VariantError) as failure:
        Substitution.from_json("{}")  # type: ignore[arg-type]
    assert failure.value.code is VariantErrorCode.INVALID_NOTATION


@pytest.mark.parametrize(
    "changes",
    [
        {"position": True},
        {"position": 0},
        {"position": -1},
        {"position": MAX_SAFE_INTEGER + 1},
        {"reference_aa": "AA"},
        {"alternate_aa": ""},
        {"alternate_aa": "A"},
        {"alternate_aa": None},
    ],
)
def test_difference_record_constructors_and_codecs_enforce_invariants(
    changes: dict[str, Any],
) -> None:
    data: dict[str, Any] = {
        "position": 4,
        "reference_aa": "A",
        "alternate_aa": "V",
    } | changes
    constructors: list[Callable[[], object]] = [
        lambda: SequenceDifference(**data),
        lambda: SequenceDifference.from_dict(data),
    ]
    for create in constructors:
        with pytest.raises(VariantError) as failure:
            create()
        assert failure.value.code is VariantErrorCode.INVALID_DIFFERENCE_INPUT


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": "MACAG"},
        {"sequence": "VACVG"},
        {"sequence": "MACV"},
        {"sequence": "MACVGG"},
        {"differences": ()},
        {"differences": []},
        {
            "differences": (
                SequenceDifference(position=1, reference_aa="M", alternate_aa="V"),
            )
        },
        {"sequence_hash": ContentHash(sha256="0" * 64, encoding=HashEncoding.SEQUENCE)},
        {
            "sequence_hash": ContentHash(
                sha256=hashlib.sha256(b"MACVG").hexdigest(), encoding=HashEncoding.RAW
            )
        },
        {"interpretation_kind": "predicted"},
        {"reference": None},
    ],
)
def test_result_cannot_claim_inconsistent_derived_fields(
    changes: dict[str, Any],
) -> None:
    result = apply_substitution(snapshot(), parse_substitution("A4V"))
    with pytest.raises(VariantError) as failure:
        replace(result, **changes)
    assert failure.value.code is VariantErrorCode.INVALID_VARIANT_RESULT


@pytest.mark.parametrize(
    "field", ["sequence", "differences", "sequence_hash", "interpretation_kind"]
)
def test_result_decoding_verifies_derived_fields(field: str) -> None:
    data = apply_substitution(snapshot(), parse_substitution("A4V")).to_dict()
    data[field] = {
        "sequence": "MACAG",
        "differences": [],
        "sequence_hash": ContentHash(
            sha256="0" * 64, encoding=HashEncoding.SEQUENCE
        ).to_dict(),
        "interpretation_kind": "experimental",
    }[field]
    with pytest.raises(VariantError) as failure:
        SubstitutionResult.from_dict(data)
    assert failure.value.code is VariantErrorCode.INVALID_VARIANT_RESULT
