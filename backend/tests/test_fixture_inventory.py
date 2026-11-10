"""Keep synthetic fixture provenance and raw-byte identities reviewable."""

import hashlib
import json
from pathlib import Path
from typing import Any

from neurofold.core.provenance import (
    ContentHash,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
)

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/testing/fixtures.json"


def test_fixture_inventory_matches_bytes_and_provenance() -> None:
    inventory: dict[str, Any] = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert inventory["schema_version"] == "neurofold-fixtures/1"
    entries = inventory["fixtures"]
    assert entries
    assert len({entry["fixture_id"] for entry in entries}) == len(entries)
    paths: set[Path] = set()
    for entry in entries:
        path = ROOT / entry["path"]
        assert not Path(entry["path"]).is_absolute()
        assert path.resolve().is_relative_to(ROOT)
        assert path not in paths
        paths.add(path)
        data = path.read_bytes()
        assert 0 < len(data) <= 64 * 1024
        assert type(entry["byte_size"]) is int
        assert entry["byte_size"] == len(data)
        content_hash = ContentHash.from_dict(entry["content_hash"])
        assert content_hash.encoding == HashEncoding.RAW
        assert content_hash.sha256 == hashlib.sha256(data).hexdigest()
        assert EvidenceKind(entry["evidence"]) == EvidenceKind.SYNTHETIC
        assert entry["license"] == "Apache-2.0"
        for field in ("fixture_id", "author", "generation_method", "purpose"):
            assert isinstance(entry[field], str) and entry[field].strip()
        assert isinstance(entry["expected_invariants"], list)
        assert entry["expected_invariants"]
        assert all(
            isinstance(value, str) and value.strip()
            for value in entry["expected_invariants"]
        )
        for field in ("units", "coordinate_convention"):
            metadata = Metadata.from_dict(entry[field])
            # All current fixtures are identity/transport records, not coordinates.
            assert metadata.state == MetadataState.NOT_APPLICABLE
            assert metadata.reason

    fixture_dir = ROOT / "backend/tests/fixtures"
    assert {path for path in fixture_dir.rglob("*") if path.is_file()} <= paths
