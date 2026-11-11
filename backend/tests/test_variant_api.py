"""NF-03 production HTTP routes over temporary real archives, under offline guards."""

import asyncio
import os
from pathlib import Path
from threading import Barrier, Event
from typing import Any, cast
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response as ClientResponse
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_variant_storage import REFERENCE_HASH, VARIANT_ID, retain
from test_variants import snapshot

from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.api.composition import Services, compose
from neurofold.api.configuration import Settings
from neurofold.api.execution import BlockingExecutor
from neurofold.api.main import create_app
from neurofold.api.variants import EXAMPLE_REQUEST, EXAMPLE_RESPONSE, VariantResponse
from neurofold.core.variants import (
    VariantDefinition,
    define_variant,
    parse_substitution,
)

URL = "/v1/variants/" + VARIANT_ID
BODY = dict(EXAMPLE_REQUEST)


@pytest.fixture
def captured_executors(monkeypatch: pytest.MonkeyPatch) -> list[BlockingExecutor]:
    """Keep the timeout trigger separate from later capacity/result verification."""
    captured: list[BlockingExecutor] = []

    def create(workers: int, seconds: float) -> BlockingExecutor:
        executor = BlockingExecutor(workers, seconds)
        captured.append(executor)
        return executor

    monkeypatch.setattr("neurofold.api.main.BlockingExecutor", create)
    return captured


def setup(
    tmp_path: Path, sequence: str = "MACAG", *, workers: int = 4, seconds: float = 5
) -> tuple[Settings, Services, FilesystemStore]:
    settings = Settings(
        archive_root=tmp_path / "data/archive",
        workers=workers,
        operation_seconds=seconds,
    )
    store = FilesystemStore(settings.archive_root)
    retain(store, snapshot(sequence))
    return settings, compose(settings), store


def app_for(settings: Settings, services: Services) -> FastAPI:
    return create_app(settings=settings, service_factory=lambda: services)


def error(
    response: httpx.Response | ClientResponse, status: int, code: str
) -> dict[str, Any]:
    assert response.status_code == status, response.text
    value = cast(dict[str, Any], response.json()["error"])
    assert set(value) == {"code", "message", "retryable", "details", "request_id"}
    assert value["code"] == code
    assert value["request_id"] == response.headers["x-request-id"]
    for unsafe in ("secret", "/private/", "MACAG", "MACVG", "Traceback"):
        assert unsafe not in response.text
    return value


def test_winner_duplicate_get_fresh_offline_composition_and_preserved_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, services, store = setup(tmp_path)
    before = {path.name: path.read_bytes() for path in store.root.iterdir()}
    monkeypatch.setattr(
        "neurofold.adapters.biological.transport.HttpxTransport.request",
        lambda *args, **kwargs: pytest.fail("Variant routes must never call providers"),
    )
    with TestClient(app_for(settings, services)) as client:
        first = client.post("/v1/variants", json=BODY)
        assert first.status_code == 201, first.text
        assert first.json() == EXAMPLE_RESPONSE
        assert first.headers["Location"] == URL
        duplicate = client.post("/v1/variants", json=BODY)
        assert duplicate.status_code == 200
        assert duplicate.json() == first.json()
        assert duplicate.headers["Location"] == URL
        for url in (URL, first.headers["Location"], duplicate.headers["Location"]):
            loaded = client.get(url)
            assert loaded.status_code == 200
            assert loaded.json() == EXAMPLE_RESPONSE
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/v1/references/" + BODY["reference_id"]).json() == (
            snapshot().to_dict()
        )
    # New app, service and repository graph; unrelated configured catalogs forbidden.
    with TestClient(create_app(settings=settings)) as client:
        assert client.get(URL).json() == EXAMPLE_RESPONSE
        assert client.post("/v1/variants", json=BODY).status_code == 200
    assert VariantResponse.model_validate(first.json()).to_core() == (
        define_variant(snapshot(), parse_substitution("A4V"))
    )
    assert store.get(snapshot().reference_id) == snapshot()
    for name, raw in before.items():
        assert (store.root / name).read_bytes() == raw


WRONG_TYPES: list[object] = [None, True, 4, 4.0, [], {}]
INVALID_BODIES: list[object] = [
    {},
    [],
    None,
    "A4V",
    True,
    1,
    *[
        {key: value for key, value in BODY.items() if key != missing}
        for missing in BODY
    ],
    {**BODY, "extra": "secret"},
    *[{**BODY, field: value} for field in BODY for value in WRONG_TYPES],
    *[
        {**BODY, "reference_id": value}
        for value in ("", " ref", "ref\n", "../ref", "r" * 129, "réf")
    ],
    *[
        {**BODY, "expected_reference_sha256": value}
        for value in ("", "a" * 63, "A" * 64, "g" * 64, REFERENCE_HASH + "\n")
    ],
]


@pytest.mark.parametrize("body", INVALID_BODIES)
def test_strict_http_validation_precedes_composition(body: object) -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("Composed"))
    ) as client:
        error(client.post("/v1/variants", json=body), 422, "INVALID_INPUT")


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"\xff",
        b'{"notation":"A4V","notation":"C3W"}',
        b"[" * 1200 + b"0" + b"]" * 1200,
    ],
)
def test_invalid_json_precedes_composition(raw: bytes) -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("Composed"))
    ) as client:
        error(
            client.post(
                "/v1/variants",
                content=raw,
                headers={"content-type": "application/json"},
            ),
            422,
            "INVALID_INPUT",
        )


@pytest.mark.parametrize(
    "notation",
    ["", "a4v", "A04V", " A4V", "A4V\n", "A0V", "A٤V", "A" + "9" * 5000 + "V"],
)
def test_reached_notation_errors_are_domain_failures(
    tmp_path: Path, notation: str
) -> None:
    settings, services, store = setup(tmp_path)
    with TestClient(app_for(settings, services)) as client:
        result = client.post(
            "/v1/variants",
            json={
                **BODY,
                "reference_id": "absent",
                "expected_reference_sha256": "0" * 64,
                "notation": notation,
            },
        )
        assert error(result, 422, "INVALID_NOTATION")["details"] == {}
    assert not list(store.root.glob("variant-*"))


@pytest.mark.parametrize(
    ("sequence", "notation", "code", "details"),
    [
        (
            "MACAG",
            "A6V",
            "POSITION_OUT_OF_RANGE",
            {"position": 6, "reference_length": 5},
        ),
        (
            "MACAG",
            "C4C",
            "REFERENCE_MISMATCH",
            {"position": 4, "requested_reference_aa": "C", "actual_reference_aa": "A"},
        ),
        (
            "MACAG",
            "A4A",
            "NO_OP_SUBSTITUTION",
            {"position": 4, "reference_aa": "A", "alternate_aa": "A"},
        ),
        (
            "MXC?G",
            "A6V",
            "UNSUPPORTED_REFERENCE_ALPHABET",
            {
                "affected_residues": [
                    {"position": 2, "symbol": "X"},
                    {"position": 4, "symbol": "?"},
                ]
            },
        ),
    ],
)
def test_biological_error_codes_details_and_precedence(
    tmp_path: Path, sequence: str, notation: str, code: str, details: dict[str, Any]
) -> None:
    settings, services, store = setup(tmp_path, sequence)
    body = {
        **BODY,
        "notation": notation,
        "expected_reference_sha256": snapshot(sequence).protein.sequence_hash.sha256,
    }
    with TestClient(app_for(settings, services)) as client:
        assert (
            error(client.post("/v1/variants", json=body), 422, code)["details"]
            == details
        )
    assert not list(store.root.glob("variant-*"))


def test_missing_reference_hash_mismatch_and_unknown_variant(tmp_path: Path) -> None:
    settings, services, store = setup(tmp_path)
    with TestClient(app_for(settings, services)) as client:
        assert error(
            client.post("/v1/variants", json={**BODY, "reference_id": "missing"}),
            404,
            "REFERENCE_NOT_FOUND",
        )["details"] == {"reference_id": "missing"}
        assert error(
            client.post(
                "/v1/variants",
                json={**BODY, "expected_reference_sha256": "0" * 64, "notation": "A6V"},
            ),
            409,
            "REFERENCE_HASH_MISMATCH",
        )["details"] == {
            "expected_reference_sha256": "0" * 64,
            "actual_reference_sha256": REFERENCE_HASH,
        }
        error(client.get(URL), 404, "NOT_FOUND")
    assert not list(store.root.glob("variant-*"))


@pytest.mark.parametrize(
    "dependency", ["variant", "reference", "pin", "receipt", "artifact"]
)
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_absent_variant_versus_retained_dependency_damage(
    tmp_path: Path, dependency: str, damage: str
) -> None:
    settings, services, store = setup(tmp_path)
    with TestClient(app_for(settings, services)) as client:
        assert client.post("/v1/variants", json=BODY).status_code == 201
        receipt = snapshot().protein.source_receipt
        identity = {
            "variant": VARIANT_ID,
            "reference": BODY["reference_id"],
            "pin": BODY["reference_id"],
            "receipt": receipt.receipt_id,
            "artifact": receipt.raw_artifact.artifact_id,
        }[dependency]
        path = store._path(dependency, identity)
        if damage == "missing":
            path.unlink()
        else:
            path.write_bytes(b'{"secret":')
        missing_variant = dependency == "variant" and damage == "missing"
        error(
            client.get(URL),
            404 if missing_variant else 500,
            "NOT_FOUND" if missing_variant else "ARCHIVE_INTEGRITY",
        )
        if not missing_variant:
            missing_reference = dependency == "reference" and damage == "missing"
            error(
                client.post("/v1/variants", json=BODY),
                404 if missing_reference else 500,
                "REFERENCE_NOT_FOUND" if missing_reference else "ARCHIVE_INTEGRITY",
            )
            assert (
                (not path.exists())
                if damage == "missing"
                else path.read_bytes() == b'{"secret":'
            )


def test_valid_immutable_collision_returns_conflict_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, services, store = setup(tmp_path)
    monkeypatch.setattr("neurofold.core.variants.sha256_bytes", lambda _: "0" * 64)
    with TestClient(app_for(settings, services)) as client:
        winner = client.post("/v1/variants", json=BODY)
        assert winner.status_code == 201
        path = store._path("variant", winner.json()["variant_id"])
        before = path.read_bytes()
        error(
            client.post("/v1/variants", json={**BODY, "notation": "A4W"}),
            409,
            "ARCHIVE_CONFLICT",
        )
        assert path.read_bytes() == before
        assert client.get(winner.headers["Location"]).json() == winner.json()


@pytest.mark.parametrize("after_link", [False, True])
def test_publication_io_uncertainty_and_verified_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_link: bool
) -> None:
    settings, services, store = setup(tmp_path)
    original_link = os.link

    def fail_link(*args: Any, **kwargs: Any) -> None:
        if after_link:
            original_link(*args, **kwargs)
        raise OSError("secret /private/archive MACAG")

    with TestClient(app_for(settings, services)) as client:
        with monkeypatch.context() as patch:
            patch.setattr(os, "link", fail_link)
            result = client.post("/v1/variants", json=BODY)
        failure = error(result, 503, "ARCHIVE_PUBLICATION_FAILED")
        assert failure["retryable"] is False
        details = failure["details"]
        assert details["publication_may_complete"] is True
        assert details["automatic_retry"] is False
        assert details["variant_id"] == VARIANT_ID
        assert details["resource_url"] == URL
        assert details["recovery"]
        recovered = client.get(details["resource_url"])
        if after_link:
            assert recovered.status_code == 200
            assert recovered.json() == EXAMPLE_RESPONSE
        else:
            error(recovered, 404, "NOT_FOUND")
            assert not list(store.root.glob("variant-*"))
        repeated = client.post("/v1/variants", json=BODY)
        assert repeated.status_code == (200 if after_link else 201)
        assert repeated.json() == EXAMPLE_RESPONSE


def test_concurrent_http_contenders_overlap_at_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, services, store = setup(tmp_path, workers=4, seconds=30)
    contenders = Barrier(4)
    original_link = os.link

    def concurrent_link(*args: Any, **kwargs: Any) -> None:
        contenders.wait(timeout=30)
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", concurrent_link)
    app = app_for(settings, services)

    async def scenario() -> None:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://offline"
            ) as client,
        ):
            results = await asyncio.gather(
                *(client.post("/v1/variants", json=BODY) for _ in range(4))
            )
            assert sorted(result.status_code for result in results) == [
                200,
                200,
                200,
                201,
            ]
            assert all(result.json() == EXAMPLE_RESPONSE for result in results)
            assert all(result.headers["Location"] == URL for result in results)
            assert (await client.get(URL)).json() == EXAMPLE_RESPONSE

    asyncio.run(scenario())
    assert len(list(store.root.glob("variant-*"))) == 1


@pytest.mark.parametrize("outcome", ["success", "timeout", "cancel"])
def test_http_worker_accounting_late_publication_and_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: str,
    captured_executors: list[BlockingExecutor],
) -> None:
    settings, services, _ = setup(
        tmp_path, workers=1, seconds=0.1 if outcome == "timeout" else 30
    )
    entered, release = Event(), Event()
    original_link = os.link
    app = app_for(settings, services)

    def blocked_link(*args: Any, **kwargs: Any) -> None:
        entered.set()
        assert release.wait(30)
        original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", blocked_link)

    async def scenario() -> None:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://offline"
            ) as client,
        ):
            task = asyncio.create_task(client.post("/v1/variants", json=BODY))
            try:
                assert await asyncio.to_thread(entered.wait, 30)
                assert (await client.get("/health")).json() == {"status": "ok"}
                if outcome == "timeout":
                    failure = error(await task, 504, "OPERATION_TIMEOUT")
                    assert failure["retryable"] is False
                    assert failure["details"]["publication_may_complete"] is True
                    assert failure["details"]["automatic_retry"] is False
                    assert "variant_id" not in failure["details"]
                    assert "resource_url" not in failure["details"]
                elif outcome == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                # The 100 ms budget deliberately expires only the held mutation.
                # Successful recovery reads are not latency benchmarks.
                captured_executors[0].seconds = 30
                rejected = error(await client.get(URL), 429, "ADMISSION_LIMIT")
                assert rejected["retryable"] is True
                release.set()
                if outcome == "success":
                    assert (await task).status_code == 201
                # Poll the actual admission boundary, bounded; success proves capacity
                # recovery after completion; events synchronize the race.
                async with asyncio.timeout(30):
                    while True:
                        recovered = await client.get(URL)
                        if recovered.status_code != 429:
                            break
                        await asyncio.sleep(0)
                assert recovered.status_code == 200
                assert recovered.json() == EXAMPLE_RESPONSE
                assert (await client.post("/v1/variants", json=BODY)).status_code == 200
            finally:
                release.set()
                if not task.done():
                    await task

    with caplog.at_level("INFO", logger="uvicorn.error"):
        asyncio.run(scenario())
    completed = [
        record for record in caplog.records if "publication completed" in record.message
    ]
    assert len(completed) == 2
    assert all(
        "request_id=" in record.message and URL in record.message
        for record in completed
    )
    assert all(
        "MACAG" not in record.message and "MACVG" not in record.message
        for record in caplog.records
    )


@pytest.mark.parametrize("method", ["PATCH", "PUT", "DELETE", "POST"])
def test_unsupported_methods(tmp_path: Path, method: str) -> None:
    settings, services, _ = setup(tmp_path)
    with TestClient(app_for(settings, services)) as client:
        result = client.request(method, URL)
        error(result, 405, "HTTP_ERROR")
        assert "GET" in result.headers["Allow"]


@pytest.mark.parametrize(
    "variant_id",
    ["bad", "variant-" + "A" * 64, "variant-" + "a" * 63, "variant-" + "a" * 64 + "\n"],
)
def test_invalid_path_representations(variant_id: str) -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("Composed"))
    ) as client:
        error(client.get("/v1/variants/" + quote(variant_id)), 422, "INVALID_INPUT")


def test_boundary_queries_size_and_lazy_health() -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("Composed"))
    ) as client:
        assert client.get("/health").json() == {"status": "ok"}
        for url in (URL + "?limit=1", "/v1/variants?x=1", URL + "?x=1&x=2"):
            error(client.get(url), 400, "INVALID_QUERY")
        error(client.post("/v1/variants", content=b"x" * 16385), 413, "SIZE_LIMIT")


def test_outgoing_response_validation_runs_inside_production_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, services, _ = setup(tmp_path)
    original = VariantDefinition.to_dict

    def invalid(self: VariantDefinition) -> dict[str, object]:
        value = original(self)
        del value["interpretation_kind"]
        return value

    # GET repository verification still uses the actual record; only the final
    # DTO projection receives damaged output. Never return unchecked dictionaries.
    definition = define_variant(snapshot(), parse_substitution("A4V"))
    monkeypatch.setattr(services.variants, "get", lambda _: definition)
    monkeypatch.setattr(VariantDefinition, "to_dict", invalid)
    with TestClient(app_for(settings, services)) as client:
        error(client.get(URL), 500, "INTERNAL_ERROR")


@pytest.mark.parametrize("field", list(EXAMPLE_RESPONSE))
def test_all_outgoing_fields_are_required(field: str) -> None:
    value = dict(EXAMPLE_RESPONSE)
    del value[field]
    with pytest.raises(ValidationError):
        VariantResponse.model_validate(value)


def test_openapi_success_errors_strict_schemas_and_exact_examples() -> None:
    with TestClient(
        create_app(service_factory=lambda: pytest.fail("Composed"))
    ) as client:
        schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    post = paths["/v1/variants"]["post"]
    get = paths["/v1/variants/{variant_id}"]["get"]
    for operation in (post, get):
        for status in (400, 404, 405, 409, 413, 422, 429, 500, 503, 504):
            response = operation["responses"][str(status)]
            assert response["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
            assert response["content"]["application/json"]["examples"]
    for status in (200, 201):
        response = post["responses"][str(status)]
        assert "Location" in response["headers"]
        assert response["content"]["application/json"]["example"] == EXAMPLE_RESPONSE
    assert (
        post["requestBody"]["content"]["application/json"]["examples"]["synthetic"][
            "value"
        ]
        == BODY
    )
    for name in (
        "VariantRequest",
        "VariantResponse",
        "SubstitutionDTO",
        "DifferenceDTO",
    ):
        model = schema["components"]["schemas"][name]
        assert model["additionalProperties"] is False
        assert set(model["required"]) == set(model["properties"])
    # Validate real examples against generated OpenAPI schemas as well as codecs.
    for name, value in (
        ("VariantResponse", EXAMPLE_RESPONSE),
        ("VariantRequest", BODY),
    ):
        Draft202012Validator(
            {"$ref": "#/components/schemas/" + name, "components": schema["components"]}
        ).validate(value)
    assert VariantResponse.model_validate(EXAMPLE_RESPONSE).to_core() == define_variant(
        snapshot(), parse_substitution("A4V")
    )


@pytest.mark.parametrize("phase", ["stage", "file_fsync", "directory_fsync"])
def test_real_publication_io_phases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    settings, services, store = setup(tmp_path)
    fsync = os.fsync
    calls = 0

    def fail_stage(*args: Any, **kwargs: Any) -> Any:
        raise OSError("secret /private/archive MACAG")

    def fail_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == (2 if phase == "directory_fsync" else 1):
            raise OSError("secret /private/archive MACAG")
        fsync(fd)

    with TestClient(app_for(settings, services)) as client:
        with monkeypatch.context() as patch:
            if phase == "stage":
                patch.setattr("tempfile.NamedTemporaryFile", fail_stage)
            else:
                patch.setattr(os, "fsync", fail_fsync)
            failure = error(
                client.post("/v1/variants", json=BODY),
                503,
                "ARCHIVE_PUBLICATION_FAILED",
            )
        assert failure["details"]["resource_url"] == URL
        if phase == "directory_fsync":
            assert client.get(URL).json() == EXAMPLE_RESPONSE
            assert client.post("/v1/variants", json=BODY).status_code == 200
        else:
            error(client.get(URL), 404, "NOT_FOUND")
            assert not list(store.root.glob("variant-*"))
        assert not list(store.root.glob("tmp*"))


def test_get_verification_conversion_and_serialization_are_admitted_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import current_thread

    settings, services, _ = setup(tmp_path, workers=1)
    definition = services.variants.create(**BODY).definition
    entered, release = Event(), Event()
    original_get = services.variants.get
    original_dump = VariantResponse.model_dump_json

    def get(variant_id: str) -> VariantDefinition:
        assert current_thread().name.startswith("neurofold")
        return original_get(variant_id)

    def serialize(self: VariantResponse, **kwargs: Any) -> str:
        assert current_thread().name.startswith("neurofold")
        assert self.to_core() == definition
        entered.set()
        assert release.wait(5)
        return original_dump(self, **kwargs)

    monkeypatch.setattr(services.variants, "get", get)
    monkeypatch.setattr(VariantResponse, "model_dump_json", serialize)
    app = app_for(settings, services)

    async def scenario() -> None:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://offline"
            ) as client,
        ):
            task = asyncio.create_task(client.get(URL))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                assert (await client.get("/health")).status_code == 200
                rejected = await client.get(URL)
                error(rejected, 429, "ADMISSION_LIMIT")
                assert rejected.headers["Retry-After"] == "1"
                release.set()
                assert (await task).json() == EXAMPLE_RESPONSE
            finally:
                release.set()
                await task

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_late_failure_is_observed_logged_and_shutdown_drains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    cancel: bool,
) -> None:
    settings, services, _ = setup(tmp_path, workers=1, seconds=30 if cancel else 0.1)
    entered, release, finished = Event(), Event(), Event()

    def failure(*args: Any, **kwargs: Any) -> None:
        entered.set()
        assert release.wait(30)
        try:
            raise OSError("secret /private/archive MACAG")
        finally:
            finished.set()

    monkeypatch.setattr(os, "link", failure)
    app = app_for(settings, services)

    async def scenario() -> None:
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://offline"
        ) as client:
            task = asyncio.create_task(client.post("/v1/variants", json=BODY))
            try:
                assert await asyncio.to_thread(entered.wait, 30)
                if cancel:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    error(await task, 504, "OPERATION_TIMEOUT")
                error(await client.get(URL), 429, "ADMISSION_LIMIT")
                closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await asyncio.sleep(0)
                assert not closing.done()
                assert not finished.is_set()
                assert (await client.get("/health")).status_code == 200
                release.set()
                await closing
                assert finished.is_set()
            finally:
                release.set()
                if not task.done():
                    await task
        # Reopen after draining late failure: no variant was linked.
        with TestClient(create_app(settings=settings)) as restarted:
            error(restarted.get(URL), 404, "NOT_FOUND")

    with caplog.at_level("INFO", logger="uvicorn.error"):
        asyncio.run(scenario())
    failures = [
        record.message
        for record in caplog.records
        if "publication failed" in record.message
    ]
    assert len(failures) == 1
    assert "request_id=" in failures[0] and "VariantPublicationFailure" in failures[0]
    assert all(
        "secret" not in record.message and "MACAG" not in record.message
        for record in caplog.records
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "substitution",
            {
                "reference_aa": "A",
                "position": True,
                "alternate_aa": "V",
                "notation_version": "nf-substitution/1",
            },
        ),
        (
            "substitution",
            {
                "reference_aa": "A",
                "position": "4",
                "alternate_aa": "V",
                "notation_version": "nf-substitution/1",
            },
        ),
        ("substitution", {"reference_aa": "A", "position": 4, "alternate_aa": "V"}),
        (
            "substitution",
            {
                "reference_aa": "A",
                "position": 4,
                "alternate_aa": "V",
                "notation_version": "nf-substitution/2",
            },
        ),
        ("sequence_length", True),
        ("sequence_length", "5"),
        ("sequence", "VACVG"),
        ("interpretation_kind", "predicted"),
        ("differences", []),
        ("extra", "secret"),
    ],
)
def test_outgoing_strict_types_versions_and_invariants(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        VariantResponse.model_validate({**EXAMPLE_RESPONSE, field: value})
