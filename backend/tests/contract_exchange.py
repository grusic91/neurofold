"""Emit actual offline application responses for TypeScript/UI contract tests.

Invoked by Vitest/Playwright as a separate Python process. Keep the child under
socket/DNS guards too; only explicitly injected synthetic providers are used.
No listening server, biological data or provider network is involved.
"""

import base64
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest_socket
from fastapi.testclient import TestClient
from test_integration import configured, import_body, pin
from test_structures import CIF
from test_uniprot import entry, response

from neurofold.api.main import create_app


def deny(*args: object, **kwargs: object) -> None:
    raise RuntimeError("DNS is disabled in contract exchange")


def exchange() -> dict[str, Any]:
    pytest_socket.disable_socket(allow_unix_socket=True)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        setattr(socket, name, deny)
    with TemporaryDirectory(prefix="neurofold-m4-exchange-") as directory:
        settings, services, up, pdb = configured(Path(directory).resolve())
        with TestClient(
            create_app(settings=settings, service_factory=lambda: services)
        ) as client:
            up.events.append(response({"results": [entry(), entry("P00002")]}))
            proteins = client.get("/v1/proteins?gene=SYNTH&taxon_id=1").json()
            reference = pin(client, up)
            pdb.events.extend(
                [response({"total_count": 1, "result_set": [{"identifier": "1SYN.A"}]})]
            )
            from test_structures import metadata_events

            pdb.events.extend(metadata_events())
            discovery = client.get(
                f"/v1/references/{reference['reference_id']}/structures"
            ).json()
            # Fresh authoritative selection checks use 304s against retained metadata.
            pdb.events.extend([response(None, 304)] * 6)
            from test_structures import coordinate_response

            pdb.events.extend([coordinate_response(), response(None, 304)])
            created = client.post(
                "/v1/structures", json=import_body(reference["reference_id"])
            )
            assert created.status_code == 201, created.text
            structure = created.json()
            original = client.get(structure["artifact_url"])
            assert original.content == CIF.read_bytes()
            return {
                "proteinPage": proteins,
                "protein": reference["protein"],
                "reference": reference,
                "pinAudit": client.get(
                    f"/v1/references/{reference['reference_id']}/audit"
                ).json(),
                "structurePage": discovery,
                "structure": structure,
                "structureAudit": client.get(
                    created.headers["Location"] + "/audit"
                ).json(),
                "original": base64.b64encode(original.content).decode("ascii"),
                "headers": dict(original.headers),
            }


if __name__ == "__main__":
    print(json.dumps(exchange()))
