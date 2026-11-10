"""Bounded child proposals, distinct from retained M1 scientific documents."""

import base64
from dataclasses import dataclass
from typing import Literal

from neurofold.core.prediction_base import PredictionRecord, require
from neurofold.core.prediction_outputs import (
    PredictionResult,
    SuccessfulPredictionProvenance,
)
from neurofold.core.provenance import ArtifactDescriptor

MAX_BUNDLE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class StagedArtifact(PredictionRecord):
    descriptor: ArtifactDescriptor
    base64_bytes: str

    def bytes(self) -> bytes:
        return base64.b64decode(self.base64_bytes, validate=True)

    def _validate(self) -> None:
        require(len(self.base64_bytes) <= MAX_BUNDLE_BYTES)
        require(len(self.bytes()) == self.descriptor.byte_size)


@dataclass(frozen=True, kw_only=True)
class ChildBundle(PredictionRecord):
    schema_version: Literal["neurofold-child-proposal/1"] = "neurofold-child-proposal/1"
    result: PredictionResult
    manifest: SuccessfulPredictionProvenance
    artifacts: tuple[StagedArtifact, ...]

    def _validate(self) -> None:
        ids = [a.descriptor.artifact_id for a in self.artifacts]
        require(len(ids) == len(set(ids)))
        require(sum(a.descriptor.byte_size for a in self.artifacts) <= MAX_BUNDLE_BYTES)
