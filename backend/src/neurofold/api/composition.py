"""Composition root. Nothing here performs network IO or scientific parsing."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from neurofold.adapters.biological.alignment import PolymerMapper
from neurofold.adapters.biological.mmcif import MmcifParser
from neurofold.adapters.biological.rcsb import RcsbCatalog
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.structure_storage import FilesystemStructures
from neurofold.adapters.biological.transport import HttpxTransport
from neurofold.adapters.biological.uniprot import UniProtCatalog
from neurofold.api.configuration import ConfigurationError, Settings
from neurofold.application.biological import BiologicalService
from neurofold.application.references import ReferenceService
from neurofold.application.structures import StructureService
from neurofold.core.biological import ExperimentalStructureCatalog, ProteinCatalog
from neurofold.core.lookup import PinReceipt
from neurofold.core.provenance import ArtifactStore


class PinAudits(Protocol):
    def get_pin_receipt(self, reference_id: str) -> PinReceipt: ...


@dataclass(frozen=True)
class Services:
    proteins: ProteinCatalog
    references: ReferenceService
    discovery: ExperimentalStructureCatalog
    structures: StructureService
    artifacts: ArtifactStore
    pins: PinAudits

    @property
    def biological(self) -> BiologicalService:
        # Stateless read facade uses the exact injected catalogs/dependency graph.
        return BiologicalService(
            self.proteins, self.discovery, self.references.repository, self.artifacts
        )


def compose(settings: Settings) -> Services:
    try:
        archive = FilesystemStore(settings.archive_root)
    except ValueError as exc:
        raise ConfigurationError("Archive configuration is unsupported") from exc
    transport = HttpxTransport()
    proteins = UniProtCatalog(transport, archive.artifact_store, archive)
    discovery = RcsbCatalog(transport, archive.artifact_store, archive)
    return Services(
        proteins,
        ReferenceService(proteins, archive, archive),
        discovery,
        StructureService(
            discovery,
            archive,
            MmcifParser(),
            PolymerMapper(),
            FilesystemStructures(archive),
        ),
        archive.artifact_store,
        archive,
    )


class LazyServices:
    def __init__(self, factory: Callable[[], Services]) -> None:
        self.factory = factory
        self.lock = Lock()
        self.value: Services | None = None

    def get(self) -> Services:
        # Only admitted worker threads can wait here: no unbounded request queue.
        with self.lock:
            if self.value is None:
                self.value = self.factory()
            return self.value
