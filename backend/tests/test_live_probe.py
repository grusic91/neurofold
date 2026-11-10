"""The opt-in probe is itself tested using authored synthetic providers only."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from test_uniprot import Fake

from neurofold.adapters.biological.transport import TransportTimeout
from neurofold.core.provenance import EvidenceKind

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_end_to_end_uses_only_synthetic_transport_and_retains_inventory(
    tmp_path: Path,
) -> None:
    probe = load("live_probe_under_test", ROOT / "backend/scripts/live_probe.py")
    profile = load("probe_synthetic_profile", ROOT / "infra/testing/offline_app.py")
    output = tmp_path / "data/probe"
    report = probe.run_probe(
        output,
        probe.Inputs("P00001", 1, "1SYN", "1", "A", "2"),
        profile.SyntheticTransport(ROOT / "backend/tests/fixtures"),
        evidence=EvidenceKind.SYNTHETIC,
        environment_record={"evidence": "synthetic"},
    )
    assert report["outcome"] == "passed", report.get("error")
    assert 0 < report["provider_requests"] <= 32
    assert report["mapping"]["selection"]["model_id"] == "2"
    assert report["records"]["pin_status"] == 304
    assert any(step["name"] == "offline-original" for step in report["steps"])
    assert json.loads((output / "report.json").read_bytes())["outcome"] == "passed"
    inventory = json.loads((output / "inventory.json").read_bytes())
    assert inventory["files"]
    for item in inventory["files"]:
        raw = (output / item["path"]).read_bytes()
        assert len(raw) == item["byte_size"] and probe.digest(raw) == item["sha256"]
    with pytest.raises(FileExistsError):
        probe.run_probe(
            output,
            probe.Inputs("P00001", 1, "1SYN", "1", "A", "2"),
            Fake(),
            environment_record={},
        )


def test_probe_requires_explicit_opt_in_before_any_network_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = load("probe_opt_in_under_test", ROOT / "backend/scripts/live_probe.py")
    output = tmp_path / "data/no-probe"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "live_probe.py",
            "--output",
            str(output),
            "--accession",
            "P00001",
            "--taxon",
            "1",
            "--entry",
            "1SYN",
            "--entity",
            "1",
            "--chain",
            "A",
            "--model",
            "1",
            "--asymmetric-unit",
        ],
    )
    monkeypatch.setattr(
        probe,
        "HttpxTransport",
        lambda: pytest.fail("No opt-in must not select a live transport"),
    )
    with pytest.raises(SystemExit) as error:
        probe.main()
    assert error.value.code == 2 and not output.exists()


def test_probe_records_failed_transport_attempt_and_enforces_request_cap(
    tmp_path: Path,
) -> None:
    probe = load("probe_recording_under_test", ROOT / "backend/scripts/live_probe.py")
    recorder = probe.RecordingTransport(
        tmp_path, Fake(TransportTimeout("Synthetic timeout"))
    )
    with pytest.raises(TransportTimeout):
        recorder.request(
            "https://rest.uniprot.org/uniprotkb/P00001.json", {}, timeout=1
        )
    event = json.loads((tmp_path / "001.json").read_bytes())
    assert event["error"][0]["type"] == "TransportTimeout"
    recorder.calls = 32
    with pytest.raises(RuntimeError, match="budget"):
        recorder.request(
            "https://rest.uniprot.org/uniprotkb/P00001.json", {}, timeout=1
        )
