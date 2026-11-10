"""Exercise the public HTTP contract without model packages or external services."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from neurofold.api.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_returns_liveness_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_health_is_documented_in_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    response_schema = schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/HealthResponse"}
    assert (
        schema["components"]["schemas"]["HealthResponse"]["properties"]["status"][
            "const"
        ]
        == "ok"
    )


def test_health_rejects_mutating_requests(client: TestClient) -> None:
    assert client.post("/health").status_code == 405


def test_unknown_endpoint_returns_not_found(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
