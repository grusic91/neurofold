"""Initial single-protein adapter contract; no inference implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PredictionRequest:
    """Protein sequence and explicit random seed for a future prediction."""

    sequence: str
    seed: int


@dataclass(frozen=True)
class PredictionResult:
    """Paths to a generated structure and its scientific provenance manifest."""

    structure_path: Path
    provenance_path: Path


class PredictionAdapter(Protocol):
    """Implement in adapters without coupling core to a model runtime or HTTP."""

    def predict(
        self, request: PredictionRequest, *, output_dir: Path
    ) -> PredictionResult:
        """Write structure and provenance artifacts to an explicit directory."""
        ...
