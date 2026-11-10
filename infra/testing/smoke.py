"""Container/proxy synthetic acceptance; use only with compose.offline.yaml."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any


def call(
    path: str,
    body: dict[str, Any] | None = None,
    *,
    base_url: str = "http://127.0.0.1:5173/api",
) -> tuple[Any, Any]:
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(request, timeout=95) as response:
        raw = response.read()
        return json.loads(raw), response.headers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["create", "read"])
    parser.add_argument("records", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173/api")
    args = parser.parse_args()

    def invoke(path: str, body: dict[str, Any] | None = None) -> tuple[Any, Any]:
        return call(path, body, base_url=args.base_url)

    assert invoke("/health")[0] == {"status": "ok"}
    if args.mode == "create":
        protein, _ = invoke("/v1/proteins/P00001")
        reference, headers = invoke(
            "/v1/references",
            {
                "accession": "P00001",
                "expected_sequence_sha256": protein["sequence_hash"]["sha256"],
            },
        )
        assert headers["Location"] == "/v1/references/" + reference["reference_id"]
        page, _ = invoke(headers["Location"] + "/structures")
        selected = page["items"][0]
        structure, headers = invoke(
            "/v1/structures",
            {
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
        assert (
            headers["Location"]
            == "/v1/structures/" + structure["descriptor"]["structure_id"]
        )
        args.records.write_text(
            json.dumps({"reference": reference, "structure": structure})
        )
    saved = json.loads(args.records.read_text())
    assert (
        invoke("/v1/references/" + saved["reference"]["reference_id"])[0]
        == saved["reference"]
    )
    structure = saved["structure"]
    assert (
        invoke("/v1/structures/" + structure["descriptor"]["structure_id"])[0]
        == structure
    )
    audit, _ = invoke(
        "/v1/structures/" + structure["descriptor"]["structure_id"] + "/audit"
    )
    assert audit["parsing"]["transform_applied"] is False
    with urllib.request.urlopen(
        args.base_url + structure["artifact_url"], timeout=10
    ) as response:
        raw = response.read()
        assert "Content-Encoding" not in response.headers
        assert response.headers["X-Checksum-SHA256"] == hashlib.sha256(raw).hexdigest()
        assert len(raw) == int(response.headers["Content-Length"])
        assert (
            raw
            == Path("backend/tests/fixtures/structure-synthetic-v1.cif").read_bytes()
        )
    print(
        "Synthetic biological routes, original bytes, "
        "retained records and proxy passed."
    )


if __name__ == "__main__":
    main()
