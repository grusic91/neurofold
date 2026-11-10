"""Safe strict prediction vocabulary; no runtime, IO or HTTP dependencies."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from neurofold.core._contracts import Contract
from neurofold.core.canonical import sha256_bytes
from neurofold.core.provenance import ContentHash, ContentReference, HashEncoding


class PredictionErrorCode(StrEnum):
    INVALID_REPRESENTATION = "INVALID_REPRESENTATION"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    UNSUPPORTED_PARAMETER = "UNSUPPORTED_PARAMETER"
    RESOURCE_LIMIT = "PREDICTION_RESOURCE_LIMIT"
    INCONSISTENT_INPUT = "INCONSISTENT_PREDICTION_INPUT"
    ILLEGAL_TRANSITION = "ILLEGAL_PREDICTION_TRANSITION"
    INCOMPLETE_PROVENANCE = "INCOMPLETE_PREDICTION_PROVENANCE"
    PUBLICATION_INTEGRITY = "PREDICTION_PUBLICATION_INTEGRITY"


class ValidationStage(StrEnum):
    REPRESENTATION = "representation"
    PROFILE = "profile"
    PARAMETERS = "parameters"
    INPUTS = "inputs"
    LIFECYCLE = "lifecycle"
    PROVENANCE = "provenance"
    ARTIFACTS = "artifacts"


class PredictionError(ValueError):
    """Only enumerated, producer-independent public details and static messages."""

    def __init__(self, code: PredictionErrorCode, stage: ValidationStage) -> None:
        self.code = code
        self.stage = stage
        super().__init__(code.value)

    @property
    def details(self) -> dict[str, object]:
        return {"stage": self.stage.value}


def require(
    condition: bool,
    code: PredictionErrorCode = PredictionErrorCode.INVALID_REPRESENTATION,
    stage: ValidationStage = ValidationStage.REPRESENTATION,
) -> None:
    if not condition:
        raise PredictionError(code, stage)


def identifier(value: str) -> None:
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value) is not None)


def unique(values: tuple[str, ...]) -> None:
    require(len(set(values)) == len(values))
    for value in values:
        identifier(value)


def domain(reference: ContentReference, encoding: HashEncoding) -> None:
    identifier(reference.record_id)
    require(reference.content_hash.encoding is encoding)


class PredictionRecord(Contract):
    """Reuse frozen NF-08 codec with sanitized prediction-specific failures."""

    def __post_init__(self) -> None:
        try:
            super().__post_init__()
        except PredictionError:
            raise
        except (ValueError, TypeError, UnicodeError) as exc:
            raise PredictionError(
                PredictionErrorCode.INVALID_REPRESENTATION,
                ValidationStage.REPRESENTATION,
            ) from exc

    @classmethod
    def from_dict(cls, value: object) -> Self:
        try:
            return super().from_dict(value)
        except PredictionError:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise PredictionError(
                PredictionErrorCode.INVALID_REPRESENTATION,
                ValidationStage.REPRESENTATION,
            ) from exc

    @classmethod
    def from_json(cls, data: bytes) -> Self:
        require(type(data) is bytes)
        try:
            return super().from_json(data)
        except PredictionError:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise PredictionError(
                PredictionErrorCode.INVALID_REPRESENTATION,
                ValidationStage.REPRESENTATION,
            ) from exc

    @property
    def content_hash(self) -> ContentHash:
        return ContentHash(
            sha256=sha256_bytes(self.to_json()), encoding=HashEncoding.CANONICAL_JSON
        )


@dataclass(frozen=True, kw_only=True)
class SoftwareIdentity(PredictionRecord):
    name: str
    version: str

    def _validate(self) -> None:
        identifier(self.name)
        identifier(self.version)
