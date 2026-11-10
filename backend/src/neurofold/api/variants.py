"""Strict projection of NF-03 persisted definitions; no new identity envelope."""

from typing import Annotated, Any, Literal

from pydantic import Field

from neurofold.api import biological as dto
from neurofold.core.variants import (
    SequenceDifference,
    Substitution,
    VariantDefinition,
)

VariantID = Annotated[str, Field(pattern=r"^variant-[0-9a-f]{64}$")]
Residue = Annotated[str, Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")]


class VariantRequest(dto.RequestDTO):
    reference_id: dto.OpaqueID
    expected_reference_sha256: dto.Digest
    # Syntax is deliberately validated by the service to retain domain precedence.
    notation: str


class SubstitutionDTO(dto.DTO):
    contract = Substitution
    reference_aa: Residue
    position: dto.Positive
    alternate_aa: Residue
    notation_version: Literal["nf-substitution/1"]


class DifferenceDTO(dto.DTO):
    contract = SequenceDifference
    position: dto.Positive
    reference_aa: Residue
    alternate_aa: Residue


class VariantResponse(dto.DTO):
    contract = VariantDefinition
    schema_version: Literal["neurofold-variant/1"]
    variant_id: VariantID
    reference_id: dto.OpaqueID
    reference_sequence_sha256: dto.Digest
    reference_content_hash: dto.HashDTO
    reference_accession: dto.Accession
    reference_taxon_id: dto.Positive
    reference_sequence_version: dto.MetadataDTO
    reference_entry_version: dto.MetadataDTO
    substitution: SubstitutionDTO
    notation: str
    sequence: dto.Text
    sequence_hash: dto.HashDTO
    sequence_length: dto.Positive
    differences: Annotated[list[DifferenceDTO], Field(min_length=1, max_length=1)]
    interpretation_kind: Literal["hypothesis"]


# Exact authored MACAG/A4V/MACVG example; no provider data.
EXAMPLE_REQUEST = {
    "expected_reference_sha256": (
        "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e"
    ),
    "notation": "A4V",
    "reference_id": "synthetic-variant-reference",
}
EXAMPLE_RESPONSE = {
    "differences": [{"alternate_aa": "V", "position": 4, "reference_aa": "A"}],
    "interpretation_kind": "hypothesis",
    "notation": "A4V",
    "reference_accession": "P00001",
    "reference_content_hash": {
        "algorithm": "sha256",
        "encoding": "neurofold-json/1",
        "sha256": "a36dc032d7baa24bf2d1a3a30f67491826fb4f702626b308df6d80c685a77bdb",
    },
    "reference_entry_version": {"reason": None, "state": "present", "value": 2},
    "reference_id": "synthetic-variant-reference",
    "reference_sequence_sha256": (
        "c88582ee0f845de56779787b8447097ae3330a816d1656b2808e0d439206226e"
    ),
    "reference_sequence_version": {"reason": None, "state": "present", "value": 1},
    "reference_taxon_id": 1,
    "schema_version": "neurofold-variant/1",
    "sequence": "MACVG",
    "sequence_hash": {
        "algorithm": "sha256",
        "encoding": "sequence-ascii/1",
        "sha256": "938b2b382d01f18f15d8d909f926f1b02c94bd5ad7527a057a91733787060315",
    },
    "sequence_length": 5,
    "substitution": {
        "alternate_aa": "V",
        "notation_version": "nf-substitution/1",
        "position": 4,
        "reference_aa": "A",
    },
    "variant_id": (
        "variant-4f0a7366f1a3a152596ba4337b0f2050b7b06e70640cc77ef54aafa84143f165"
    ),
}


REQUEST_ID_HEADER = {
    "X-Request-ID": {
        "description": "Request correlation ID, matching error.request_id on errors.",
        "schema": {"type": "string"},
    }
}

LOCATION_HEADER = {
    **REQUEST_ID_HEADER,
    "Location": {
        "description": (
            "Relative GET resource URL, present for both winner and verified duplicate."
        ),
        "schema": {"type": "string"},
        "example": "/v1/variants/" + str(EXAMPLE_RESPONSE["variant_id"]),
    },
}
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": dto.ErrorResponse,
        "description": description,
        "headers": {
            **REQUEST_ID_HEADER,
            **(
                {"Retry-After": {"schema": {"type": "string"}, "example": "1"}}
                if status == 429
                else {}
            ),
        },
        "content": {
            "application/json": {
                "examples": {
                    code: {
                        "value": {
                            "error": {
                                "code": code,
                                "message": message,
                                "retryable": status == 429,
                                "details": details,
                                "request_id": "synthetic-request",
                            }
                        }
                    }
                    for code, message, details in examples
                }
            }
        },
    }
    for status, description, examples in (
        (400, "Invalid query", [("INVALID_QUERY", "Unknown query parameter.", {})]),
        (
            404,
            "Absent variant or creation reference",
            [
                ("NOT_FOUND", "Requested variant was not found.", {}),
                (
                    "REFERENCE_NOT_FOUND",
                    "Pinned reference was not found.",
                    {"reference_id": "absent-pin"},
                ),
            ],
        ),
        (
            405,
            "Unsupported method; Allow identifies supported methods",
            [("HTTP_ERROR", "Requested operation is unavailable.", {})],
        ),
        (
            409,
            "Expected hash mismatch or immutable conflict",
            [
                (
                    "REFERENCE_HASH_MISMATCH",
                    "Expected hash differs from pinned reference.",
                    {
                        "expected_reference_sha256": "0" * 64,
                        "actual_reference_sha256": EXAMPLE_REQUEST[
                            "expected_reference_sha256"
                        ],
                    },
                ),
                ("ARCHIVE_CONFLICT", "Immutable content conflict.", {}),
            ],
        ),
        (
            413,
            "Request exceeds 16 KiB",
            [("SIZE_LIMIT", "Request body exceeds 16 KiB.", {})],
        ),
        (
            422,
            (
                "HTTP validation precedes M2 notation/reference/hash "
                "and M1 biological validation"
            ),
            [
                ("INVALID_INPUT", "Request validation failed.", {}),
                ("INVALID_NOTATION", "Invalid compact substitution.", {}),
                (
                    "REFERENCE_MISMATCH",
                    "Requested residue differs from pinned residue.",
                    {
                        "position": 4,
                        "requested_reference_aa": "C",
                        "actual_reference_aa": "A",
                    },
                ),
                (
                    "POSITION_OUT_OF_RANGE",
                    "Position exceeds reference length.",
                    {"position": 6, "reference_length": 5},
                ),
                (
                    "NO_OP_SUBSTITUTION",
                    "A substitution must change a residue.",
                    {"position": 4, "reference_aa": "A", "alternate_aa": "A"},
                ),
                (
                    "UNSUPPORTED_REFERENCE_ALPHABET",
                    "Reference alphabet is unsupported.",
                    {"affected_residues": [{"position": 2, "symbol": "X"}]},
                ),
            ],
        ),
        (
            429,
            "Zero-queue admission rejected; Retry-After: 1",
            [("ADMISSION_LIMIT", "All blocking workers are busy.", {})],
        ),
        (
            500,
            "Damaged retained records/dependencies or invalid outgoing response",
            [
                (
                    "ARCHIVE_INTEGRITY",
                    "Retained data failed integrity verification.",
                    {},
                ),
                ("INTERNAL_ERROR", "The operation could not be completed.", {}),
            ],
        ),
        (
            503,
            "Publication I/O outcome uncertain; no automatic retry",
            [
                (
                    "ARCHIVE_PUBLICATION_FAILED",
                    "Publication outcome is uncertain.",
                    {
                        "publication_may_complete": True,
                        "automatic_retry": False,
                        "recovery": (
                            "Verify a known variant ID with GET or deliberately "
                            "repeat the identical request."
                        ),
                    },
                )
            ],
        ),
        (
            504,
            "Response budget expired; mutating work may still publish",
            [
                (
                    "OPERATION_TIMEOUT",
                    "Work may still finish.",
                    {"publication_may_complete": True, "automatic_retry": False},
                )
            ],
        ),
    )
}
