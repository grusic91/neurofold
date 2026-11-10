"""Authoritative NF-04 M1 worker seam; no adapter execution implementation."""

from pathlib import Path
from typing import Protocol

from neurofold.core.prediction_inputs import PredictionSpec as PredictionSpec
from neurofold.core.prediction_outputs import PredictionResult as PredictionResult

# One class and codec, not competing legacy/rich request representations.
PredictionRequest = PredictionSpec


class PredictionAdapter(Protocol):
    """Future adapters stage locally and return registered scientific identities."""

    def predict(
        self, request: PredictionRequest, *, output_dir: Path
    ) -> PredictionResult:
        """Retain every sample/raw output; output paths remain worker-internal."""
        ...
