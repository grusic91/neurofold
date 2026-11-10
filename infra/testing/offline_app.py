"""Explicit synthetic-only ASGI composition for container smoke tests.

This module is mounted only by compose.offline.yaml, never selected by production
configuration. Its transport cannot open a socket. All identities are fictional.
"""

import gzip
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from neurofold.adapters.biological.alignment import PolymerMapper
from neurofold.adapters.biological.mmcif import MmcifParser
from neurofold.adapters.biological.policy import Clock, RetryPolicy
from neurofold.adapters.biological.rcsb import RcsbCatalog
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.structure_storage import FilesystemStructures
from neurofold.adapters.biological.transport import Response
from neurofold.adapters.biological.uniprot import UniProtCatalog
from neurofold.adapters.variant_storage import FilesystemVariants
from neurofold.api.composition import Services
from neurofold.api.configuration import Settings
from neurofold.application.references import ReferenceService
from neurofold.application.structures import StructureService
from neurofold.application.variants import VariantService
from neurofold.core.provenance import EvidenceKind

FIXTURES = Path(__file__).resolve().parents[2] / "backend/tests/fixtures"
if Path("/app/synthetic").is_dir():
    FIXTURES = Path("/app/synthetic")


class SyntheticTransport:
    def __init__(self, fixtures: Path = FIXTURES, *, compressed: bool = False) -> None:
        self.fixtures = fixtures
        self.compressed = compressed

    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        parsed = urlsplit(url)
        path = parsed.path
        if headers.get("if-none-match") == '"synthetic"':
            return Response(304, {"etag": '"synthetic"'})
        data: object
        if parsed.hostname == "rest.uniprot.org" and path.endswith("P00001.json"):
            data = json.loads(
                (self.fixtures / "uniprot-synthetic-v1.json").read_bytes()
            )
        elif parsed.hostname == "rest.uniprot.org" and path.endswith("/search"):
            data = {
                "results": [
                    json.loads(
                        (self.fixtures / "uniprot-synthetic-v1.json").read_bytes()
                    )
                ]
            }
        elif parsed.hostname == "search.rcsb.org":
            data = {"total_count": 1, "result_set": [{"identifier": "1SYN.A"}]}
        elif path.endswith("/entry/1SYN"):
            data = {
                "rcsb_id": "1SYN",
                "rcsb_entry_info": {
                    "structure_determination_methodology": "experimental",
                    "resolution_combined": [2],
                },
                "exptl": [{"method": "X-RAY DIFFRACTION"}],
                "rcsb_accession_info": {
                    "major_revision": 1,
                    "minor_revision": 0,
                    "revision_date": "2026-11-10",
                },
                "rcsb_entry_container_identifiers": {"assembly_ids": ["1"]},
                "rcsb_primary_citation": {"pdbx_database_id_DOI": "synthetic:authored"},
            }
        elif path.endswith("/polymer_entity_instance/1SYN/A"):
            data = {
                "rcsb_id": "1SYN.A",
                "rcsb_polymer_entity_instance_container_identifiers": {
                    "entry_id": "1SYN",
                    "asym_id": "A",
                    "auth_asym_id": "X",
                    "entity_id": "1",
                },
            }
        elif path.endswith("/polymer_entity/1SYN/1"):
            data = {
                "rcsb_id": "1SYN_1",
                "rcsb_polymer_entity_container_identifiers": {
                    "entry_id": "1SYN",
                    "entity_id": "1",
                    "asym_ids": ["A", "B"],
                    "reference_sequence_identifiers": [
                        {"database_name": "UniProt", "database_accession": "P00001"}
                    ],
                },
                "rcsb_entity_source_organism": [{"ncbi_taxonomy_id": 1}],
                "entity_poly": {
                    "type": "polypeptide(L)",
                    "pdbx_seq_one_letter_code_can": "ACDEFG",
                },
            }
        elif parsed.hostname == "files.rcsb.org" and path.endswith("/1SYN.cif"):
            raw = (self.fixtures / "structure-synthetic-v1.cif").read_bytes()
            return Response(
                200,
                {
                    "content-type": "chemical/x-mmcif",
                    "etag": '"synthetic"',
                    **({"content-encoding": "gzip"} if self.compressed else {}),
                },
                gzip.compress(raw, mtime=0) if self.compressed else raw,
            )
        else:
            raise AssertionError("Unmatched synthetic provider request")
        return Response(
            200,
            {"content-type": "application/json", "etag": '"synthetic"'},
            json.dumps(data).encode(),
        )


def services(
    settings: Settings | None = None,
    fixtures: Path = FIXTURES,
    *,
    compressed: bool = False,
) -> Services:
    settings = settings or Settings.from_environment()
    store = FilesystemStore(settings.archive_root)
    transport = SyntheticTransport(fixtures, compressed=compressed)
    clock = Clock(utcnow=lambda: datetime(2026, 11, 10, tzinfo=UTC))
    proteins = UniProtCatalog(
        transport,
        store.artifact_store,
        store,
        clock=clock,
        retry=RetryPolicy(retries=0),
        evidence=EvidenceKind.SYNTHETIC,
    )
    discovery = RcsbCatalog(
        transport,
        store.artifact_store,
        store,
        clock=clock,
        retry=RetryPolicy(retries=0),
        evidence=EvidenceKind.SYNTHETIC,
    )
    return Services(
        proteins,
        ReferenceService(proteins, store, store),
        discovery,
        StructureService(
            discovery,
            store,
            MmcifParser(),
            PolymerMapper(),
            FilesystemStructures(store),
        ),
        store.artifact_store,
        store,
        VariantService(store, FilesystemVariants(store, store)),
    )
