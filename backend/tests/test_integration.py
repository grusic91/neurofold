"""Actual M4 HTTP/service/archive acceptance with authored offline providers."""

import asyncio
import gzip
import json
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any, cast
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_structures import CIF, REVISION, coordinate_response, metadata_events
from test_uniprot import Fake, Time, entry, response

from neurofold.adapters.biological.policy import RetryPolicy
from neurofold.adapters.biological.rcsb import RcsbCatalog
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.transport import TransportTimeout
from neurofold.adapters.biological.uniprot import UniProtCatalog, absent, present
from neurofold.api.composition import Services, compose
from neurofold.api.configuration import ConfigurationError, Settings
from neurofold.api.execution import AdmissionLimit, BlockingExecutor, OperationTimeout
from neurofold.api.main import create_app
from neurofold.api.routes import StructureAuditResponse
from neurofold.application.references import ReferenceService
from neurofold.core.canonical import sequence_sha256, sha256_bytes
from neurofold.core.errors import ArchiveConflict, ArchiveIntegrityError, ResourceLimit
from neurofold.core.lookup import (
    CursorError,
    ProviderError,
    ProviderTimeout,
    ProviderValidationError,
    SourceChanged,
    UnsupportedIdentifier,
)
from neurofold.core.provenance import EvidenceKind
from neurofold.core.structures import (
    RevisionUnavailable,
    StructureSourceChanged,
    UnsupportedStructure,
)


def configured(tmp_path: Path) -> tuple[Settings, Services, Fake, Fake]:
    settings = Settings(archive_root=tmp_path / "data/archive")
    services = compose(settings)
    archive = FilesystemStore(settings.archive_root)
    clock = Time().clock
    up, pdb = Fake(), Fake()
    proteins = UniProtCatalog(
        up,
        services.artifacts,
        archive,
        clock=clock,
        retry=RetryPolicy(retries=0),
        evidence=EvidenceKind.SYNTHETIC,
    )
    discovery = RcsbCatalog(
        pdb,
        services.artifacts,
        archive,
        clock=clock,
        retry=RetryPolicy(retries=0),
        evidence=EvidenceKind.SYNTHETIC,
    )
    services = replace(
        services,
        proteins=proteins,
        discovery=discovery,
        references=ReferenceService(
            proteins, services.references.repository, services.references.archive
        ),
    )
    services.structures.provider = discovery
    return settings, services, up, pdb


def pin(client: TestClient, up: Fake) -> dict[str, Any]:
    up.events.extend([response(entry(), etag='"synthetic"'), response(None, 304)])
    inspected = client.get("/v1/proteins/P00001")
    assert inspected.status_code == 200
    result = client.post(
        "/v1/references",
        json={
            "accession": "P00001",
            "expected_sequence_sha256": inspected.json()["sequence_hash"]["sha256"],
        },
    )
    assert result.status_code == 201, result.text
    assert client.get(result.headers["Location"]).json() == result.json()
    audit = client.get(result.headers["Location"] + "/audit").json()
    assert audit["response_status"] == 304
    assert (
        audit["source_receipt_id"]
        == result.json()["protein"]["source_receipt"]["receipt_id"]
    )
    return cast(dict[str, Any], result.json())


def import_body(reference_id: str) -> dict[str, Any]:
    return {
        "reference_id": reference_id,
        "entry_id": "1SYN",
        "entity_id": "1",
        "label_asym_id": "A",
        "model_id": "2",
        "assembly_id": present("1").to_dict(),
        "operator_id": present("2").to_dict(),
        "expected_source_revision": present(REVISION).to_dict(),
    }


def import_events(pdb: Fake, raw: bytes, compressed: bool) -> None:
    pdb.events.extend(
        metadata_events()
        + [response(None, 304)] * 3
        + [
            coordinate_response(
                raw, **({"content-encoding": "gzip"} if compressed else {})
            ),
            response(None, 304),
        ]
    )


@pytest.mark.parametrize("compressed", [False, True])
def test_actual_routes_pin_import_restart_and_offline_originals(
    tmp_path: Path, compressed: bool
) -> None:
    settings, services, up, pdb = configured(tmp_path)
    raw = gzip.compress(CIF.read_bytes(), mtime=0) if compressed else CIF.read_bytes()
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        import_events(pdb, raw, compressed)
        created = client.post(
            "/v1/structures", json=import_body(reference["reference_id"])
        )
        assert created.status_code == 201, created.text
        record = created.json()
        assert client.get(created.headers["Location"]).json() == record
        assert record["descriptor"]["selection"]["auth_asym_id"]["value"] == "X"
        assert not up.events and not pdb.events
        assert record["mapping"]["rows"][2]["status"] == "unobserved"
        assert record["mapping"]["rows"][4]["auth_seq_id"]["state"] == "unavailable"
    # Fresh composition has empty provider caches; forbid every transport request.
    restarted = compose(settings)
    with (
        patch(
            "neurofold.adapters.biological.transport.HttpxTransport.request",
            side_effect=AssertionError("Offline retained reads must not refresh"),
        ),
        TestClient(
            create_app(settings=settings, service_factory=lambda: restarted)
        ) as client,
    ):
        assert (
            client.get("/v1/references/" + reference["reference_id"]).json()
            == reference
        )
        assert client.get(created.headers["Location"]).json() == record
        audit_response = client.get(created.headers["Location"] + "/audit")
        audit = StructureAuditResponse.model_validate(audit_response.json())
        assert audit.parsing["transform_applied"] is False
        assert audit.parsing["coordinate_frame"] == "original-deposited-cartesian"
        assert audit.parsing["coordinate_unit"] == "angstrom"
        assert audit.alignment["coordinate_reference_coverage"] == {
            "numerator": 4,
            "denominator": 6,
        }
        assert audit.checks[-1].response_status == 304
        assert audit.parsing["assemblies"]
        original = client.get(record["artifact_url"])
        assert original.content == raw
        assert original.headers["x-checksum-sha256"] == sha256_bytes(raw)
        assert original.headers["etag"] == '"' + sha256_bytes(raw) + '"'
        assert int(original.headers["content-length"]) == len(raw)
        assert original.headers["content-type"] == (
            "application/gzip" if compressed else "chemical/x-mmcif"
        )
        assert "content-encoding" not in original.headers
        assert "no-transform" in original.headers["cache-control"]
        assert original.headers["x-artifact-encoding"] == (
            "gzip" if compressed else "identity"
        )
        if compressed:
            assert gzip.decompress(original.content) == CIF.read_bytes()
        assert client.get(record["artifact_url"] + "-missing").status_code == 404
        assert client.get("/v1/references/unknown").status_code == 404
        assert client.get("/v1/structures/unknown").status_code == 404


@pytest.mark.parametrize(
    ("exc", "status", "code", "retryable"),
    [
        (CursorError("expired"), 400, "INVALID_CURSOR", False),
        (KeyError("private/path"), 404, "NOT_FOUND", False),
        (SourceChanged("a" * 64, "b" * 64), 409, "SOURCE_CHANGED", False),
        (StructureSourceChanged("1", "2"), 409, "SOURCE_CHANGED", False),
        (ArchiveConflict("private/path"), 409, "ARCHIVE_CONFLICT", False),
        (ArchiveIntegrityError("private/path"), 500, "ARCHIVE_INTEGRITY", False),
        (ResourceLimit("private/path"), 413, "SIZE_LIMIT", False),
        (UnsupportedIdentifier("private/path"), 422, "INVALID_SELECTION", False),
        (UnsupportedStructure("private/path"), 422, "INVALID_SELECTION", False),
        (RevisionUnavailable("private/path"), 422, "INVALID_SELECTION", False),
        (ProviderValidationError("private/path"), 502, "INVALID_UPSTREAM", False),
        (ProviderTimeout("private/path"), 504, "UPSTREAM_TIMEOUT", True),
        (ProviderError("private/path"), 503, "UPSTREAM_UNAVAILABLE", True),
        (OSError("private/path"), 503, "ARCHIVE_UNAVAILABLE", False),
        (ValueError("private/path"), 500, "INTERNAL_ERROR", False),
    ],
)
def test_typed_errors_at_production_http_boundary(
    tmp_path: Path, exc: Exception, status: int, code: str, retryable: bool
) -> None:
    settings, services, _, _ = configured(tmp_path)
    with (
        patch.object(services.proteins, "get", side_effect=exc),
        TestClient(
            create_app(settings=settings, service_factory=lambda: services)
        ) as client,
    ):
        result = client.get(
            "/v1/proteins/P00001", headers={"X-Request-ID": "untrusted"}
        )
    assert result.status_code == status
    error = result.json()["error"]
    assert error["code"] == code and error["retryable"] is retryable
    assert set(error) == {"code", "message", "retryable", "details", "request_id"}
    assert result.headers["x-request-id"] == error["request_id"] != "untrusted"
    assert "private/path" not in result.text
    if code == "INVALID_CURSOR":
        assert "Restart" in error["details"]["restart_hint"]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "gene=",
        "gene=A%20B",
        "gene=A%00B",
        "gene=SYNTH&limit=101",
        "gene=SYNTH&taxon_id=true",
        "gene=SYNTH&gene=OTHER",
        "gene=SYNTH&url=bad",
    ],
)
def test_strict_query_without_composition(query: str) -> None:
    with TestClient(
        create_app(
            service_factory=lambda: pytest.fail("Invalid request composed services")
        )
    ) as client:
        result = client.get("/v1/proteins?" + query)
    assert (
        result.status_code == 400 and result.json()["error"]["code"] == "INVALID_QUERY"
    )


def test_validation_health_openapi_and_lazy_composition() -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("health/startup performed IO"))
    ) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/health").status_code == 405
        assert client.get("/unknown").json() == {"detail": "Not Found"}
        assert client.get("/v1/unknown").json()["error"]["code"] == "NOT_FOUND"
        method = client.post("/v1/proteins")
        assert method.status_code == 405 and method.headers["Allow"] == "GET"
        assert len(client.get("/openapi.json").json()["paths"]) == 11
        assert client.get("/v1/proteins/invalid").status_code == 422
        assert client.get("/v1/proteins/P00001?extra=1").status_code == 400
        assert (
            client.post(
                "/v1/references",
                json={"accession": "P00001-2", "expected_sequence_sha256": "a" * 64},
            ).status_code
            == 422
        )
        assert (
            client.post("/v1/references", content="{").json()["error"]["code"]
            == "INVALID_INPUT"
        )
        assert client.post("/v1/references", content="x" * 16385).status_code == 413


def test_config_validation() -> None:
    assert Settings.from_environment({}).workers == 4
    for values in [
        {"NEUROFOLD_WORKERS": "0"},
        {"NEUROFOLD_WORKERS": "many"},
        {"NEUROFOLD_OPERATION_SECONDS": "nan"},
        {"NEUROFOLD_ARCHIVE_ROOT": "/unignored"},
    ]:
        with pytest.raises(ConfigurationError):
            Settings.from_environment(values)


@pytest.mark.parametrize("cancel", [False, True])
def test_bounded_execution_cancellation_and_event_loop_responsiveness(
    cancel: bool,
) -> None:
    entered, release, finished = Event(), Event(), Event()

    def work() -> int:
        entered.set()
        assert release.wait(5)
        finished.set()
        return 42

    async def scenario() -> None:
        executor = BlockingExecutor(1, 0.03)
        task = asyncio.create_task(executor.run(work))
        while not entered.is_set():
            await asyncio.sleep(0.001)
        # The event loop is free while the worker waits; admission has no queue.
        with pytest.raises(AdmissionLimit):
            await executor.run(lambda: 0)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(OperationTimeout):
                await task
        with pytest.raises(AdmissionLimit):
            await executor.run(lambda: 0)
        release.set()
        while not finished.is_set():
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.01)
        assert await executor.run(lambda: 7) == 7
        await executor.close()
        with pytest.raises(AdmissionLimit):
            await executor.run(lambda: 0)

    asyncio.run(scenario())


def test_http_health_remains_responsive_while_admitted_work_blocks(
    tmp_path: Path,
) -> None:
    settings, services, _, _ = configured(tmp_path)
    entered, release = Event(), Event()

    def blocked(_: str) -> object:
        entered.set()
        release.wait(5)
        raise ProviderError("synthetic")

    app = create_app(
        settings=replace(settings, workers=1, operation_seconds=0.04),
        service_factory=lambda: services,
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://offline"
        ) as client:
            pending = asyncio.create_task(client.get("/v1/proteins/P00001"))
            while not entered.is_set():
                await asyncio.sleep(0.001)
            assert (await client.get("/health")).json() == {"status": "ok"}
            rejected = await client.get("/v1/proteins/P00001")
            assert (
                rejected.status_code == 429 and rejected.headers["retry-after"] == "1"
            )
            assert (await pending).status_code == 504
            assert (await client.get("/v1/proteins/P00001")).status_code == 429
            release.set()
        # ASGITransport doesn't run lifespan; use the actual app lifespan to drain.
        async with app.router.lifespan_context(app):
            pass

    with patch.object(services.proteins, "get", side_effect=blocked):
        asyncio.run(scenario())


def test_upstream_timeout_is_preserved_by_transport_and_catalog(tmp_path: Path) -> None:
    settings, services, up, _ = configured(tmp_path)
    up.events.append(TransportTimeout("synthetic deadline"))
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        assert client.get("/v1/proteins/P00001").status_code == 504


def test_real_corrupt_dependency_is_not_missing_record(tmp_path: Path) -> None:
    settings, services, up, _ = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        store = FilesystemStore(settings.archive_root)
        artifact = reference["protein"]["source_receipt"]["raw_artifact"]["artifact_id"]
        store._path("artifact", artifact).unlink()
        result = client.get("/v1/references/" + reference["reference_id"])
        assert (
            result.status_code == 500
            and result.json()["error"]["code"] == "ARCHIVE_INTEGRITY"
        )
        assert client.get("/v1/artifacts/" + artifact).status_code == 404


def test_discovery_outage_preserves_reference_and_uniprot_outage_preserves_discovery(
    tmp_path: Path,
) -> None:
    settings, services, up, pdb = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        path = "/v1/references/" + reference["reference_id"]
        pdb.events.append(ProviderError("synthetic outage"))
        page = client.get(path + "/structures").json()
        assert page["availability"] == "unavailable" and page["warnings"]
        assert client.get(path).json() == reference
        up.events.append(ProviderError("synthetic outage"))
        assert client.get("/v1/proteins/P00002").status_code == 503
        pdb.events.extend([response({"total_count": 0, "result_set": []})])
        page = client.get(path + "/structures").json()
        assert page["availability"] == "complete" and page["items"] == []


def test_sequence_and_revision_conflicts_and_unknown_revision(tmp_path: Path) -> None:
    settings, services, up, pdb = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        up.events.append(response(entry(), etag='"synthetic"'))
        conflict = client.post(
            "/v1/references",
            json={"accession": "P00001", "expected_sequence_sha256": "a" * 64},
        )
        assert conflict.status_code == 409
        up.events.append(response(None, 304))
        reference = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": sequence_sha256("ACDEFG"),
            },
        ).json()
        body = import_body(reference["reference_id"])
        body["expected_source_revision"] = absent("Unknown revision").to_dict()
        assert client.post("/v1/structures", json=body).status_code == 422
        assert not pdb.calls
        body["expected_source_revision"] = present("0.0@old").to_dict()
        pdb.events.extend(metadata_events())
        assert client.post("/v1/structures", json=body).status_code == 409
        pdb.events.append(response(None, 404))
        assert client.post("/v1/structures", json=body).status_code == 404


def test_real_search_pagination_and_cursor_binding(tmp_path: Path) -> None:
    from test_uniprot import next_link

    settings, services, up, _ = configured(tmp_path)
    up.events.extend(
        [
            response({"results": [entry()]}, link=next_link(limit=1, taxon=1)),
            response({"results": [entry("P00002")]}),
        ]
    )
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        page = client.get("/v1/proteins?gene=SYNTH&taxon_id=1&limit=1").json()
        cursor = page["next_cursor"]["value"]
        assert "http" not in cursor
        mismatch = client.get(
            f"/v1/proteins?gene=OTHER&taxon_id=1&limit=1&cursor={cursor}"
        )
        assert mismatch.status_code == 400
        assert "restart_hint" in mismatch.json()["error"]["details"]
        following = client.get(
            f"/v1/proteins?gene=SYNTH&taxon_id=1&limit=1&cursor={cursor}"
        ).json()
        assert following["items"][0]["accession"] == "P00002"
        assert len(up.calls) == 2
    with TestClient(
        create_app(settings=settings, service_factory=lambda: compose(settings))
    ) as client:
        assert (
            client.get(
                f"/v1/proteins?gene=SYNTH&taxon_id=1&limit=1&cursor={cursor}"
            ).status_code
            == 400
        )


def test_partial_discovery_keeps_valid_candidates(tmp_path: Path) -> None:
    settings, services, up, pdb = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        pdb.events.extend(
            [
                response(
                    {
                        "total_count": 2,
                        "result_set": [
                            {"identifier": "1SYN.A"},
                            {"identifier": "2SYN.A"},
                        ],
                    }
                ),
                *metadata_events(),
                response(None, 404),
            ]
        )
        result = client.get(f"/v1/references/{reference['reference_id']}/structures")
        page = result.json()
        assert page["availability"] == "partial" and len(page["items"]) == 1
        assert "2SYN.A" in page["warnings"][0]
        assert "private/path" not in result.text


def test_author_chain_resolution_is_fresh_and_consistent(tmp_path: Path) -> None:
    from test_structures import instance_data

    settings, services, up, pdb = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        changed = instance_data()
        changed["rcsb_polymer_entity_instance_container_identifiers"][
            "auth_asym_id"
        ] = "Y"  # type: ignore[index]
        pdb.events.extend(
            metadata_events()
            + [response(None, 304), response(changed), response(None, 304)]
        )
        result = client.post(
            "/v1/structures", json=import_body(reference["reference_id"])
        )
        assert result.status_code == 422
        assert not list(settings.archive_root.glob("structure-*.json"))
        assert len(pdb.calls) == 6  # Download/publication did not proceed.


def test_archive_publication_failure_and_conflicting_write_at_http_boundary(
    tmp_path: Path,
) -> None:
    settings, services, up, _ = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        up.events.append(response(entry(), etag='"synthetic"'))
        with patch.object(
            services.references.repository,
            "publish",
            side_effect=OSError("private/path"),
        ):
            failed = client.post(
                "/v1/references",
                json={
                    "accession": "P00001",
                    "expected_sequence_sha256": sequence_sha256("ACDEFG"),
                },
            )
        assert failed.status_code == 503 and "private/path" not in failed.text
        assert failed.json()["error"]["details"]["publication_may_complete"] is True
        assert not list(settings.archive_root.glob("reference-*.json"))
        # A deliberate immutable ID collision is never an overwrite or retry.
        services.references.new_id = lambda: "fixed-reference"
        up.events.append(response(None, 304))
        body = {
            "accession": "P00001",
            "expected_sequence_sha256": sequence_sha256("ACDEFG"),
        }
        first = client.post("/v1/references", json=body)
        assert first.status_code == 201
        up.events.append(
            response(
                entry(entryAudit={"entryVersion": 3, "sequenceVersion": 1}),
                etag='"new"',
            )
        )
        assert client.post("/v1/references", json=body).status_code == 409
        assert client.get(first.headers["Location"]).json() == first.json()


def test_artifact_corruption_is_verified_before_success(tmp_path: Path) -> None:
    settings, services, up, _ = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        artifact = reference["protein"]["source_receipt"]["raw_artifact"]["artifact_id"]
        store = FilesystemStore(settings.archive_root)
        path = store._path("artifact", artifact)
        raw = json.loads(path.read_bytes())
        raw["raw"] = "Y29ycnVwdA=="
        path.write_text(json.dumps(raw))
        result = client.get("/v1/artifacts/" + artifact)
        assert (
            result.status_code == 500
            and result.json()["error"]["code"] == "ARCHIVE_INTEGRITY"
        )
        assert "x-checksum-sha256" not in result.headers


def test_audit_projection_does_not_expose_unreviewed_headers(tmp_path: Path) -> None:
    settings, services, up, _ = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        up.events.append(response(entry(), etag='"synthetic"'))
        client.get("/v1/proteins/P00001")
        up.events.append(
            response(
                None,
                304,
                **{
                    "set-cookie": "private-session",
                    "x-internal": "private/path",
                    "etag": '"synthetic"',
                },
            )
        )
        result = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": sequence_sha256("ACDEFG"),
            },
        )
        audit = client.get(result.headers["Location"] + "/audit")
        assert "private-session" not in audit.text and "private/path" not in audit.text
        assert audit.json()["response_headers"] == {
            "content-type": "application/json",
            "etag": '"synthetic"',
        }
        pin = services.pins.get_pin_receipt(result.json()["reference_id"])
        assert audit.json()["retained_hash"]["sha256"] == sha256_bytes(pin.to_json())
        assert pin.response_headers.to_dict()["set-cookie"] == "private-session"


def integration_schema() -> dict[str, Any]:
    from pydantic.json_schema import models_json_schema

    from neurofold.api.routes import PinAuditResponse

    _, schema = models_json_schema(
        [(PinAuditResponse, "validation"), (StructureAuditResponse, "validation")],
        title="NeuroFold NF-02 M4 HTTP audit projections",
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:neurofold:biological-integration:1",
        **schema,
    }


def test_additive_http_audit_schema() -> None:
    from jsonschema import Draft202012Validator

    path = (
        Path(__file__).resolve().parents[2]
        / "docs/schemas/neurofold-biological-integration-1.schema.json"
    )
    schema = integration_schema()
    assert json.loads(path.read_bytes()) == schema
    Draft202012Validator.check_schema(schema)


def test_mutation_timeout_discloses_uncertain_publication_and_holds_capacity(
    tmp_path: Path,
) -> None:
    settings, services, _, _ = configured(tmp_path)
    entered, release = Event(), Event()

    def blocked(*args: object) -> object:
        entered.set()
        assert release.wait(5)
        raise ProviderError("synthetic late failure")

    app = create_app(
        settings=replace(settings, workers=1, operation_seconds=0.03),
        service_factory=lambda: services,
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://offline"
        ) as client:
            result = await client.post(
                "/v1/references",
                json={"accession": "P00001", "expected_sequence_sha256": "a" * 64},
            )
            assert entered.is_set()
            assert result.status_code == 504
            assert result.json()["error"]["retryable"] is False
            assert result.json()["error"]["details"]["publication_may_complete"] is True
            assert (await client.get("/v1/references/unknown")).status_code == 429
            release.set()
        async with app.router.lifespan_context(app):
            pass

    with patch.object(services.references, "pin", side_effect=blocked):
        asyncio.run(scenario())


def test_duplicate_and_excessively_nested_json_are_rejected_before_composition() -> (
    None
):
    with TestClient(
        create_app(
            service_factory=lambda: pytest.fail("Invalid JSON composed services")
        )
    ) as client:
        for body in [
            '{"accession":"P00001","accession":"P00002"}',
            "[" * 1200 + "0" + "]" * 1200,
        ]:
            result = client.post(
                "/v1/references",
                content=body,
                headers={"content-type": "application/json"},
            )
            assert (
                result.status_code == 422
                and result.json()["error"]["code"] == "INVALID_INPUT"
            )


def test_default_startup_does_not_import_scientific_libraries() -> None:
    import subprocess
    import sys

    script = """
import socket
import pytest_socket
pytest_socket.disable_socket(allow_unix_socket=True)
def deny(*args, **kwargs):
    raise AssertionError("Startup must not resolve providers")
socket.getaddrinfo = deny
from neurofold.api.main import create_app
from fastapi.testclient import TestClient
with TestClient(create_app()) as client:
    assert client.get("/health").json() == {"status": "ok"}
import sys
assert not any(name in sys.modules for name in ("gemmi", "Bio", "numpy"))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_late_configuration_rejection_is_sanitized(tmp_path: Path) -> None:
    target = tmp_path / "data/target"
    target.mkdir(parents=True)
    link = tmp_path / "data/link"
    link.symlink_to(target, target_is_directory=True)
    settings = Settings(archive_root=link)
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/health").status_code == 200
        result = client.get("/v1/proteins/P00001")
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "CONFIGURATION_ERROR"
        assert str(tmp_path) not in result.text


def test_artifact_boundary_independently_verifies_injected_stream(
    tmp_path: Path,
) -> None:
    import io

    settings, services, up, _ = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        reference = pin(client, up)
        artifact = reference["protein"]["source_receipt"]["raw_artifact"]["artifact_id"]
        with patch.object(
            services.artifacts, "open", return_value=io.BytesIO(b"corrupt")
        ):
            result = client.get("/v1/artifacts/" + artifact)
        assert result.status_code == 500
        assert "x-checksum-sha256" not in result.headers


def test_missing_organism_and_incompatible_structure_are_domain_errors(
    tmp_path: Path,
) -> None:
    from test_structures import entity_data

    settings, services, up, pdb = configured(tmp_path)
    with TestClient(
        create_app(settings=settings, service_factory=lambda: services)
    ) as client:
        up.events.append(response(entry(organism={})))
        result = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": sequence_sha256("ACDEFG"),
            },
        )
        assert result.status_code == 422
        up.events.append(response(entry(), etag='"synthetic"'))
        pinned = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": sequence_sha256("ACDEFG"),
            },
        )
        assert pinned.status_code == 201
        reference = pinned.json()
        events = metadata_events()
        events[2] = response(
            entity_data(rcsb_entity_source_organism=[{"ncbi_taxonomy_id": 2}])
        )
        pdb.events.extend(events)
        assert (
            client.post(
                "/v1/structures", json=import_body(reference["reference_id"])
            ).status_code
            == 422
        )
