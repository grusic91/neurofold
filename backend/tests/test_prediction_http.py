"""Actual prediction service/SQLite/archive contracts through ASGI, offline."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient
from orchestration_examples import ManualClock, bundle_for, service_for, submit
from prediction_examples import ENDED

from neurofold.api.configuration import Settings
from neurofold.api.main import create_app
from neurofold.api.predictions import JobDTO, JobStatus, ManifestDTO, ResultDTO

BODY: dict[str, Any] = {
    "reference_id": "synthetic-variant-reference",
    "variant_id": None,
    "adapter_profile_id": "contract-monomer",
    "parameters": {},
    "seed": 0,
    "msa_artifact_id": None,
    "retry_of_job_id": None,
}


def test_submission_retrieval_cancel_retry_and_reopen(tmp_path: Path) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        first = client.post(
            "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "one"}
        )
        assert first.status_code == 202, first.text
        assert first.headers["Retry-After"] == "1"
        value = JobStatus.model_validate(first.json())
        assert value.operational_failure is None
        assert client.get(first.headers["Location"]).json() == first.json()
        assert (
            client.post(
                "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "one"}
            ).json()
            == first.json()
        )
        assert (
            client.post(
                "/v1/prediction-jobs",
                json=BODY | {"seed": 1},
                headers={"Idempotency-Key": "one"},
            ).status_code
            == 409
        )
        assert client.get(first.headers["Location"] + "/result").status_code == 409
        assert (
            client.post(first.headers["Location"] + "/cancel", json={}).status_code
            == 200
        )
        assert (
            client.post(first.headers["Location"] + "/cancel", json={}).status_code
            == 200
        )
        retry = client.post(
            "/v1/prediction-jobs",
            json=BODY | {"retry_of_job_id": first.json()["job"]["job_id"]},
            headers={"Idempotency-Key": "retry"},
        )
        assert retry.status_code == 202
    with TestClient(
        create_app(prediction_factory=lambda: service_for(tmp_path, clock))
    ) as client:
        assert (
            client.get(first.headers["Location"]).json()["job"]["state"] == "cancelled"
        )
        assert client.get(retry.headers["Location"]).json() == retry.json()


@pytest.mark.parametrize(
    "change",
    [
        {"seed": True},
        {"seed": "0"},
        {"seed": 1.0},
        {"unknown": 1},
        {"parameters": {"samples": 1.0}},
        {"variant_id": 3},
    ],
)
def test_strict_submission_schema(tmp_path: Path, change: dict[str, object]) -> None:
    with TestClient(
        create_app(prediction_factory=lambda: service_for(tmp_path, ManualClock()))
    ) as client:
        response = client.post(
            "/v1/prediction-jobs",
            json=BODY | change,
            headers={"Idempotency-Key": "one"},
        )
        assert response.status_code == 422
        assert (
            response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        )


def test_required_nulls_header_duplicates_unknown_paths_and_errors(
    tmp_path: Path,
) -> None:
    service = service_for(tmp_path, ManualClock())
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        for key in BODY:
            body = dict(BODY)
            del body[key]
            assert (
                client.post(
                    "/v1/prediction-jobs", json=body, headers={"Idempotency-Key": "one"}
                ).status_code
                == 422
            )
        for headers in (
            {},
            {"Idempotency-Key": "bad key"},
            [("Idempotency-Key", "a"), ("Idempotency-Key", "a")],
        ):
            response = client.post("/v1/prediction-jobs", json=BODY, headers=headers)
            assert response.status_code == 422
        assert client.get("/v1/prediction-jobs/absent").status_code == 404
        assert client.get("/v1/prediction-jobs/absent?poll=1").status_code == 400
        assert (
            client.post(
                "/v1/prediction-jobs", content=b'{"seed":0,"seed":1}'
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/prediction-jobs",
                json=BODY | {"parameters": {"bad": 1}},
                headers={"Idempotency-Key": "a"},
            ).json()["error"]["code"]
            == "UNSUPPORTED_PARAMETER"
        )
        service.worker_available = lambda: False
        assert (
            client.post(
                "/v1/prediction-jobs", json=BODY, headers={"Idempotency-Key": "a"}
            ).status_code
            == 503
        )


def test_success_reads_exact_records_artifacts_and_known_corruption(
    tmp_path: Path,
) -> None:
    clock = ManualClock()
    service = service_for(tmp_path, clock)
    queued = submit(service)
    job = service.jobs.claim("worker-1", 60)
    assert job
    clock.now = ENDED
    succeeded = service.publish(job, bundle_for(job), job)
    assert service.get(queued.job_id) == succeeded
    path = "/v1/prediction-jobs/" + queued.job_id
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        result = client.get(path + "/result")
        manifest = client.get(path + "/manifest")
        assert result.status_code == manifest.status_code == 200
        ResultDTO.model_validate(result.json())
        ManifestDTO.model_validate(manifest.json())
        assert client.post(path + "/cancel", json={}).status_code == 409
        assert (
            client.get(
                path
                + "/artifacts/"
                + result.json()["samples"][0]["structure"]["record_id"]
            ).content
            == b"authored synthetic structure placeholder\n"
        )
        artifact = client.get(
            path + "/artifacts/" + result.json()["samples"][0]["structure"]["record_id"]
        )
        from neurofold.core.canonical import sha256_bytes

        assert artifact.headers["Content-Disposition"] == "attachment"
        assert artifact.headers["Cache-Control"] == "private, no-store"
        assert artifact.headers["X-Content-Type-Options"] == "nosniff"
        assert artifact.headers["X-Checksum-SHA256"] == sha256_bytes(artifact.content)
        assert artifact.headers["ETag"] == '"' + sha256_bytes(artifact.content) + '"'
        assert (
            "application/octet-stream"
            in client.get("/openapi.json").json()["paths"][
                "/v1/prediction-jobs/{job_id}/artifacts/{artifact_id}"
            ]["get"]["responses"]["200"]["content"]
        )
        assert client.get(path + "/artifacts/absent").status_code == 404
        from neurofold.adapters.prediction_archive import PredictionArchive

        assert isinstance(service.archive, PredictionArchive)
        service.archive.store._path(
            "artifact", result.json()["samples"][0]["structure"]["record_id"]
        ).unlink()
        damaged = client.get(path)
        assert damaged.status_code == 500
        assert damaged.json()["error"]["code"] == "ARCHIVE_INTEGRITY"
        assert client.get(path + "/result").status_code == 500


def test_startup_health_capabilities_independent_of_io_and_model(
    tmp_path: Path,
) -> None:
    def forbidden() -> Any:
        raise AssertionError("No readiness work allowed")

    with TestClient(
        create_app(
            settings=Settings(archive_root=tmp_path / "data"),
            service_factory=forbidden,
            prediction_factory=forbidden,
        )
    ) as client:
        assert client.get("/health").json() == {"status": "ok"}
        capabilities = client.get("/v1/prediction-capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()[0]["availability"] == "contract_only"
        assert capabilities.json()[1]["availability"] == "unavailable"
        assert not (tmp_path / "data").exists()
        schema = client.get("/openapi.json").json()
        assert "/v1/prediction-jobs" in schema["paths"]


def test_prediction_io_admission_timeout_health_and_drain(tmp_path: Path) -> None:
    started, release = Event(), Event()
    service = service_for(tmp_path, ManualClock())
    original = service.submit

    def blocked(**kwargs: Any) -> Any:
        started.set()
        assert release.wait(10)
        return original(**kwargs)

    service.submit = blocked  # type: ignore[method-assign]
    app = create_app(
        settings=Settings(workers=1, operation_seconds=0.02),
        prediction_factory=lambda: service,
    )
    with TestClient(app) as client:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(
                client.post,
                "/v1/prediction-jobs",
                json=BODY,
                headers={"Idempotency-Key": "a"},
            )
            assert started.wait(5)
            response = future.result(timeout=5)
            assert response.status_code == 504
            assert response.json()["error"]["details"]["publication_may_complete"]
            assert client.get("/v1/prediction-jobs/absent").status_code == 429
            assert client.get("/health").status_code == 200
            release.set()
    assert submit(service, "a").state == "queued"


def test_outgoing_records_cannot_hide_unknown_fields_or_bad_types() -> None:
    from prediction_examples import queued

    with pytest.raises(ValueError):
        JobDTO.model_validate(queued().to_dict() | {"extra": 1})
    with pytest.raises(ValueError):
        JobDTO.model_validate(queued().to_dict() | {"version": True})


def test_concurrent_http_submissions_share_one_durable_job(tmp_path: Path) -> None:
    from threading import Barrier

    service = service_for(tmp_path, ManualClock())
    barrier = Barrier(4)
    original = service.submit

    def synchronized(**kwargs: Any) -> Any:
        barrier.wait(timeout=5)
        return original(**kwargs)

    service.submit = synchronized  # type: ignore[method-assign]
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        with ThreadPoolExecutor(4) as pool:
            futures = [
                pool.submit(
                    client.post,
                    "/v1/prediction-jobs",
                    json=BODY,
                    headers={"Idempotency-Key": "concurrent"},
                )
                for _ in range(4)
            ]
            replies = [future.result(timeout=10) for future in futures]
    assert all(reply.status_code == 202 for reply in replies)
    assert len({reply.json()["job"]["job_id"] for reply in replies}) == 1


def test_m2_additive_schemas_reproducible_and_openapi_matches_records() -> None:
    import json

    from jsonschema import Draft202012Validator
    from prediction_examples import queued

    root = Path(__file__).resolve().parents[2]
    from scripts.prediction_m2_schema import schemas

    documents = schemas()
    for family, schema in documents.items():
        retained = json.loads(
            (root / f"docs/schemas/neurofold-{family}-1.schema.json").read_bytes()
        )
        assert retained == schema
        Draft202012Validator.check_schema(schema)
    value = JobStatus(
        schema_version="neurofold-prediction-status/1",
        job=JobDTO.model_validate(queued().to_dict()),
        operational_failure=None,
    )
    Draft202012Validator(documents["prediction-status"]).validate(
        value.model_dump(mode="json")
    )
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    definitions = schema["components"]["schemas"]
    job = definitions["NF04PredictionJob"]
    assert not job["additionalProperties"]
    assert set(job["required"]) == set(queued().to_dict())
    assert schema["paths"]["/v1/prediction-jobs"]["post"]["parameters"][0]["required"]


def test_prediction_paths_accept_full_m1_identifier_bounds(tmp_path: Path) -> None:
    service = service_for(tmp_path, ManualClock())
    with TestClient(create_app(prediction_factory=lambda: service)) as client:
        assert client.get("/v1/prediction-jobs/" + "x" * 160).status_code == 404
        assert client.get("/v1/prediction-jobs/" + "x" * 161).status_code == 422
