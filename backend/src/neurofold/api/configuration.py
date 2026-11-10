"""Explicit process configuration, independent of client inputs."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    archive_root: Path = Path("data/archive")
    workers: int = 4
    operation_seconds: float = 90.0

    def __post_init__(self) -> None:
        if type(self.workers) is not int or not 1 <= self.workers <= 8:
            raise ConfigurationError("NEUROFOLD_WORKERS must be between 1 and 8")
        if not 0 < self.operation_seconds <= 120:
            raise ConfigurationError("NEUROFOLD_OPERATION_SECONDS must be in (0, 120]")
        root = self.archive_root.absolute()
        if ".." in root.parts or not {"data", "outputs", ".cache"}.intersection(
            root.parts
        ):
            raise ConfigurationError(
                "Archive must be a private ignored data/ or outputs/ directory"
            )
        object.__setattr__(self, "archive_root", root)

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "Settings":
        env = os.environ if environment is None else environment
        try:
            return cls(
                archive_root=Path(env.get("NEUROFOLD_ARCHIVE_ROOT", "data/archive")),
                workers=int(env.get("NEUROFOLD_WORKERS", "4")),
                operation_seconds=float(env.get("NEUROFOLD_OPERATION_SECONDS", "90")),
            )
        except ValueError as exc:
            raise ConfigurationError(
                "Invalid NeuroFold environment configuration"
            ) from exc
