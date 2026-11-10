"""Explicit opt-in compatibility probe. Real artifacts stay in ignored storage.

Run outside pytest: ordinary tests remain offline. The default transport is the
production bounded HTTPX implementation; tests can inject a synthetic transport.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from neurofold.adapters.biological.rcsb import RcsbCatalog, validate_entry_id
from neurofold.adapters.biological.transport import HttpxTransport, Response, Transport
from neurofold.adapters.biological.uniprot import UniProtCatalog
from neurofold.api.composition import Services, compose
from neurofold.api.configuration import Settings
from neurofold.api.main import create_app
from neurofold.core.biological import validate_accession
from neurofold.core.provenance import EvidenceKind

ROOT = Path(__file__).resolve().parents[2]


def stamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def causes(error: BaseException) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    while error is not None and len(result) < 8:
        result.append({"type": type(error).__name__, "message": str(error)})
        next_error = error.__cause__
        if next_error is None:
            break
        error = next_error
    return result


@dataclass(frozen=True)
class Inputs:
    accession: str
    taxon: int
    entry: str
    entity: str
    chain: str
    model: str
    discovery_limit: int = 1


class RecordingTransport:
    """Retain every bounded original response, including failed validation inputs."""

    def __init__(self, root: Path, inner: Transport) -> None:
        self.root, self.inner = root, inner
        self.calls = 0
        self.started = time.monotonic()

    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        if self.calls >= 32 or time.monotonic() - self.started > 300:
            raise RuntimeError("Live probe request/time budget exhausted")
        self.calls += 1
        stem = self.root / f"{self.calls:03}"
        event: dict[str, object] = {
            "url": url,
            "request_headers": dict(headers),
            "timeout": timeout,
            "started_at": stamp(),
        }
        start = time.monotonic()
        try:
            response = self.inner.request(url, headers, timeout=timeout)
        except Exception as error:
            event["error"] = causes(error)
            raise
        else:
            stem.with_suffix(".body").write_bytes(response.body)
            event.update(
                status=response.status,
                headers=dict(response.headers),
                byte_size=len(response.body),
                raw_sha256=digest(response.body),
            )
            return response
        finally:
            event.update(ended_at=stamp(), elapsed_seconds=time.monotonic() - start)
            save(stem.with_suffix(".json"), event)


class OfflineTransport:
    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        raise AssertionError("Retained reads must not refresh providers")


def wire(settings: Settings, transport: Transport, evidence: EvidenceKind) -> Services:
    if evidence is EvidenceKind.PREDICTED:
        raise ValueError("A biological source probe cannot label predictions")
    services = compose(settings)
    assert isinstance(services.proteins, UniProtCatalog)
    assert isinstance(services.discovery, RcsbCatalog)
    services.proteins.transport = transport
    services.discovery.transport = transport
    services.proteins.evidence = evidence
    services.discovery.evidence = evidence
    return services


def environment() -> dict[str, object]:
    packages = (
        "neurofold",
        "fastapi",
        "pydantic",
        "httpx",
        "httpx2",
        "gemmi",
        "biopython",
        "numpy",
        "uvicorn",
    )
    changed = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    return {
        "code_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "tracked_diff_sha256": digest(changed),
        "probe_source_sha256": digest(Path(__file__).read_bytes()),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {name: importlib.metadata.version(name) for name in packages},
        "locks": {
            name: digest((ROOT / name).read_bytes())
            for name in ("backend/uv.lock", "frontend/package-lock.json")
        },
    }


def run_probe(
    root: Path,
    inputs: Inputs,
    transport: Transport,
    *,
    evidence: EvidenceKind = EvidenceKind.EXPERIMENTAL,
    environment_record: dict[str, object] | None = None,
) -> dict[str, Any]:
    validate_accession(inputs.accession, canonical=True)
    validate_entry_id(inputs.entry)
    root = root.absolute()
    if (
        ".." in root.parts
        or not {"data", "outputs"}.intersection(root.parts)
        or any(p.is_symlink() for p in (root, *root.parents))
    ):
        raise ValueError(
            "Probe output must be a new private ignored data/outputs directory"
        )
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    for folder in ("api", "transport"):
        (root / folder).mkdir(mode=0o700)
    settings = Settings(archive_root=root / "archive")
    recorder = RecordingTransport(root / "transport", transport)
    report: dict[str, Any] = {
        "schema_version": "neurofold-live-probe/1",
        "started_at": stamp(),
        "inputs": {
            **asdict(inputs),
            "assembly": "explicit asymmetric unit; operators not applied",
        },
        "environment": environment()
        if environment_record is None
        else environment_record,
        "steps": [],
        "outcome": "failed",
        "limitations": [
            "One explicitly selected public source pair; "
            "no general provider or biological accuracy claim.",
            "Only one bounded discovery page; selected entry is inspected separately, "
            "not chosen as a first result.",
            "No inference, clinical interpretation or numerical structure comparison.",
        ],
    }
    counter = 0

    def api(
        client: TestClient,
        name: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        status: int = 200,
        binary: bool = False,
    ) -> Any:
        nonlocal counter
        counter += 1
        start = time.monotonic()
        response = client.get(path) if body is None else client.post(path, json=body)
        stem = root / "api" / f"{counter:02}-{name}"
        stem.with_suffix(".body").write_bytes(response.content)
        event = {
            "name": name,
            "method": "GET" if body is None else "POST",
            "path": path,
            "body": body,
            "status": response.status_code,
            "headers": dict(response.headers),
            "raw_sha256": digest(response.content),
            "byte_size": len(response.content),
            "elapsed_seconds": time.monotonic() - start,
        }
        save(stem.with_suffix(".json"), event)
        report["steps"].append(event)
        print(f"{name}: HTTP {response.status_code}", flush=True)
        if response.status_code != status:
            raise RuntimeError(
                f"{name}: expected HTTP {status}, got {response.status_code}; "
                f"retained response in {stem.name}.body"
            )
        return response if binary else response.json()

    try:
        services = wire(settings, recorder, evidence)
        with TestClient(
            create_app(settings=settings, service_factory=lambda: services)
        ) as client:
            api(client, "health", "/health")
            protein = api(client, "lookup", f"/v1/proteins/{inputs.accession}")
            assert protein["summary"]["accession"] == inputs.accession
            assert protein["summary"]["taxon_id"]["value"] == inputs.taxon
            reference = api(
                client,
                "pin",
                "/v1/references",
                body={
                    "accession": inputs.accession,
                    "expected_sequence_sha256": protein["sequence_hash"]["sha256"],
                },
                status=201,
            )
            ref_path = "/v1/references/" + reference["reference_id"]
            pin_audit = api(client, "pin-audit", ref_path + "/audit")
            page = api(
                client,
                "discovery",
                ref_path + f"/structures?limit={inputs.discovery_limit}",
            )
            report["discovery"] = {
                "availability": page["availability"],
                "warnings": page["warnings"],
                "candidates": [
                    {
                        key: item[key]
                        for key in (
                            "entry_id",
                            "entity_id",
                            "label_asym_id",
                            "source_revision",
                        )
                    }
                    for item in page["items"]
                ],
            }
            if page["availability"] != "complete":
                raise RuntimeError(
                    "Discovery did not complete; "
                    "inspect retained provider responses before retrying"
                )
            # Explicit predeclared target, independently freshly inspected. Do not
            # choose a convenient first chain/model/assembly from discovery.
            retained_reference = services.references.get(reference["reference_id"])
            source = services.structures.provider.inspect(
                retained_reference, inputs.entry, inputs.chain, fresh=True
            )
            save(root / "selected-source.json", source.summary.to_dict())
            assert source.summary.entity_id == inputs.entity
            assert source.summary.label_asym_id == inputs.chain
            assert isinstance(source.summary.source_revision.value, str)
            selection = {
                "reference_id": reference["reference_id"],
                "entry_id": inputs.entry,
                "entity_id": inputs.entity,
                "label_asym_id": inputs.chain,
                "model_id": inputs.model,
                "assembly_id": {
                    "state": "not_applicable",
                    "value": None,
                    "reason": "Explicit probe asymmetric unit",
                },
                "operator_id": {
                    "state": "not_applicable",
                    "value": None,
                    "reason": "No assembly operator applied",
                },
                "expected_source_revision": source.summary.source_revision.to_dict(),
            }
            save(root / "import-request.json", selection)
            structure = api(
                client, "import", "/v1/structures", body=selection, status=201
            )
            structure_path = "/v1/structures/" + structure["descriptor"]["structure_id"]
            audit = api(client, "structure-audit", structure_path + "/audit")
            original = api(client, "original", structure["artifact_url"], binary=True)
            descriptor = structure["descriptor"]["raw_artifact"]
            assert len(original.content) == descriptor["byte_size"]
            assert digest(original.content) == descriptor["content_hash"]["sha256"]
            assert (
                original.headers["x-checksum-sha256"]
                == descriptor["content_hash"]["sha256"]
            )
            assert int(original.headers["content-length"]) == descriptor["byte_size"]
            assert original.headers["content-type"] == descriptor["media_type"]
            assert "content-encoding" not in original.headers
            assert audit["parsing"]["coordinate_unit"] == "angstrom"
            assert (
                audit["parsing"]["coordinate_frame"] == "original-deposited-cartesian"
            )
            assert audit["parsing"]["transform_applied"] is False
            assert (
                audit["descriptor"]["selection"]["auth_asym_id"]
                == source.summary.auth_asym_id.to_dict()
            )
            rows = structure["mapping"]["rows"]
            report["records"] = {
                "reference_id": reference["reference_id"],
                "structure_id": structure["descriptor"]["structure_id"],
                "artifact_id": descriptor["artifact_id"],
                "source_revision": source.summary.source_revision.to_dict(),
                "sequence_sha256": protein["sequence_hash"]["sha256"],
                "original_sha256": digest(original.content),
                "pin_status": pin_audit["response_status"],
                "source_check_statuses": [
                    check["response_status"] for check in audit["checks"]
                ],
            }
            report["mapping"] = {
                "states": dict(Counter(row["status"] for row in rows)),
                "reference_length": structure["mapping"]["reference_length"],
                "alignment": audit["alignment"],
                "selection": structure["descriptor"]["selection"],
            }
            assert audit["alignment"]["reference_coverage"]["denominator"] == len(
                reference["protein"]["sequence"]
            )
        # New composition and empty caches, with all provider access forbidden.
        reopened = wire(settings, OfflineTransport(), evidence)
        with TestClient(
            create_app(settings=settings, service_factory=lambda: reopened)
        ) as client:
            assert api(client, "offline-reference", ref_path) == reference
            assert api(client, "offline-structure", structure_path) == structure
            assert api(client, "offline-audit", structure_path + "/audit") == audit
            assert api(client, "offline-pin-audit", ref_path + "/audit") == pin_audit
            assert (
                api(
                    client, "offline-original", structure["artifact_url"], binary=True
                ).content
                == original.content
            )
        report["outcome"] = "passed"
    except Exception as error:
        report["error"] = causes(error)
        print(f"probe failed: {type(error).__name__}: {error}", flush=True)
    finally:
        report.update(ended_at=stamp(), provider_requests=recorder.calls)
        save(root / "report.json", report)
        files = [
            {
                "path": str(path.relative_to(root)),
                "byte_size": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
            }
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]
        save(
            root / "inventory.json",
            {"schema_version": "neurofold-probe-inventory/1", "files": files},
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-live",
        action="store_true",
        help="Explicitly authorize public UniProt/RCSB requests",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New private directory under ignored data/ or outputs/",
    )
    for field in ("accession", "entry", "entity", "chain", "model"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--taxon", required=True, type=int)
    parser.add_argument("--asymmetric-unit", required=True, action="store_true")
    args = parser.parse_args()
    if not args.enable_live:
        parser.error("No requests made: --enable-live is required")
    os.umask(0o077)
    report = run_probe(
        args.output,
        Inputs(
            args.accession, args.taxon, args.entry, args.entity, args.chain, args.model
        ),
        HttpxTransport(),
    )
    print(
        f"Outcome: {report['outcome']}; provider requests: "
        f"{report['provider_requests']}; report: {args.output / 'report.json'}"
    )
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
