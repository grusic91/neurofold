"""Validate the injected container-smoke composition locally, without Docker."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from neurofold.api.configuration import Settings
from neurofold.api.main import create_app
from neurofold.core.canonical import sequence_sha256


def test_container_synthetic_profile_and_retained_read(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "offline_profile", root / "infra/testing/offline_app.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixtures = root / "backend/tests/fixtures"
    settings = Settings(archive_root=tmp_path / "data/archive")
    with TestClient(
        create_app(
            settings=settings,
            service_factory=lambda: module.services(settings, fixtures),
        )
    ) as client:
        record = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": sequence_sha256("ACDEFG"),
            },
        )
        assert record.status_code == 201
        reference = record.json()
        page = client.get(record.headers["Location"] + "/structures").json()
        selected = page["items"][0]
        result = client.post(
            "/v1/structures",
            json={
                "reference_id": reference["reference_id"],
                "entry_id": selected["entry_id"],
                "entity_id": selected["entity_id"],
                "label_asym_id": selected["label_asym_id"],
                "model_id": "2",
                "assembly_id": {"state": "present", "value": "1", "reason": None},
                "operator_id": {"state": "present", "value": "2", "reason": None},
                "expected_source_revision": selected["source_revision"],
            },
        )
        assert result.status_code == 201, result.text
        assert result.json()["descriptor"]["evidence"] == "synthetic"
        assert (
            client.get(result.json()["artifact_url"]).content
            == (fixtures / "structure-synthetic-v1.cif").read_bytes()
        )
    with TestClient(
        create_app(
            settings=settings,
            service_factory=lambda: module.services(settings, fixtures),
        )
    ) as client:
        assert client.get(result.headers["Location"]).json() == result.json()


def test_local_api_server_cannot_open_outbound_connections_or_resolve_dns() -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    script = """
import socket
import offline_server
for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
    with socket.socket(socket.AF_INET, kind) as connection:
        try:
            if kind == socket.SOCK_DGRAM:
                connection.sendto(b"no external packet", ("192.0.2.1", 9))
            else:
                connection.connect(("127.0.0.1", 9))
        except RuntimeError as error:
            assert "Outbound network is disabled" in str(error)
        else:
            raise AssertionError("Outbound guard failed")
try:
    socket.getaddrinfo("example.invalid", 443)
except RuntimeError:
    pass
else:
    raise AssertionError("DNS guard failed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root / "infra/testing",
        capture_output=True,
        text=True,
        # Import independence is the contract, not cold-start speed under emulation.
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
