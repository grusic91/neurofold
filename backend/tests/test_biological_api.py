"""HTTP contract harness, deliberately separate from the health-only application.

Fixed synthetic responses establish wire/OpenAPI shape, not lookup/import logic.
M2-M4 must test real orchestration, upstream failure translation and storage.
"""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from neurofold.api import biological as dto
from neurofold.api.main import create_app

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((Path(__file__).parent / "fixtures/biological-v1.json").read_bytes())
RAW = b"synthetic mmCIF placeholder; no coordinates\n"
MODELS: list[type[BaseModel]] = [
    dto.ProteinQuery,
    dto.PageQuery,
    dto.ReferenceRequest,
    dto.StructureRequest,
    dto.ProteinResponse,
    dto.ReferenceResponse,
    dto.ProteinPageResponse,
    dto.StructurePageResponse,
    dto.StructureResponse,
    dto.ErrorResponse,
]


def contract_schema() -> dict[str, Any]:
    _, schema = models_json_schema(
        [(model, "validation") for model in MODELS],
        title="NeuroFold NF-02 M1 HTTP contracts (not operational routes)",
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:neurofold:biological-http:1",
        **schema,
    }


def error(code: str, *, retryable: bool = False) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": "Synthetic contract failure.",
            "retryable": retryable,
            "details": {},
            "request_id": "synthetic-request",
        }
    }


def contract_app() -> FastAPI:
    app = FastAPI(title="NF-02 contract test harness")

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Routing/translation is test-only. No production error handler is shipped.
        status = 400 if request.method == "GET" else 422
        return JSONResponse(
            error("INVALID_QUERY" if status == 400 else "INVALID_INPUT"),
            status_code=status,
        )

    @app.get("/v1/proteins", response_model=dto.ProteinPageResponse)
    def proteins(query: Annotated[dto.ProteinQuery, Query()]) -> object:
        return DATA["protein_page"]

    @app.get("/v1/proteins/{accession}", response_model=dto.ProteinResponse)
    def protein(accession: dto.Accession) -> object:
        return DATA["reference"]["protein"]

    @app.post("/v1/references", status_code=201, response_model=dto.ReferenceResponse)
    def pin(body: dto.ReferenceRequest, response: Response) -> object:
        response.headers["Location"] = "/v1/references/synthetic-reference"
        return DATA["reference"]

    @app.get("/v1/references/{reference_id}", response_model=dto.ReferenceResponse)
    def reference(reference_id: dto.OpaqueID) -> object:
        return DATA["reference"]

    @app.get(
        "/v1/references/{reference_id}/structures",
        response_model=dto.StructurePageResponse,
    )
    def structures(
        reference_id: dto.OpaqueID, query: Annotated[dto.PageQuery, Query()]
    ) -> object:
        return DATA["structure_page"]

    @app.post("/v1/structures", status_code=201, response_model=dto.StructureResponse)
    def import_structure(body: dto.StructureRequest, response: Response) -> object:
        response.headers["Location"] = "/v1/structures/synthetic-structure"
        return DATA["structure"]

    @app.get("/v1/structures/{structure_id}", response_model=dto.StructureResponse)
    def structure(structure_id: dto.OpaqueID) -> object:
        return DATA["structure"]

    @app.get(
        "/v1/artifacts/{artifact_id}",
        response_class=Response,
        responses={
            200: {
                "content": {
                    "chemical/x-mmcif": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                }
            }
        },
    )
    def artifact(artifact_id: dto.OpaqueID) -> Response:
        return Response(
            RAW,
            media_type="chemical/x-mmcif",
            headers={
                "ETag": '"' + hashlib.sha256(RAW).hexdigest() + '"',
                "X-Checksum-SHA256": hashlib.sha256(RAW).hexdigest(),
            },
        )

    return app


def structure_request() -> dict[str, Any]:
    selection = DATA["structure"]["descriptor"]["selection"]
    return {
        "reference_id": "synthetic-reference",
        "entry_id": "0SYN",
        "entity_id": selection["entity_id"],
        "label_asym_id": selection["label_asym_id"],
        "model_id": selection["model_id"],
        "assembly_id": selection["assembly_id"],
        "operator_id": selection["operator_id"],
        "expected_source_revision": DATA["structure"]["descriptor"]["source"][
            "source_revision"
        ],
    }


def test_contract_harness_all_route_shapes_and_headers() -> None:
    with TestClient(contract_app()) as client:
        assert (
            client.get("/v1/proteins?gene=SYNTH&taxon_id=1&limit=20").json()
            == DATA["protein_page"]
        )
        assert client.get("/v1/proteins/P00001").json() == DATA["reference"]["protein"]
        reference = client.post(
            "/v1/references",
            json={
                "accession": "P00001",
                "expected_sequence_sha256": DATA["reference"]["protein"][
                    "sequence_hash"
                ]["sha256"],
            },
        )
        assert reference.status_code == 201
        assert reference.headers["Location"] == "/v1/references/synthetic-reference"
        assert (
            reference.json()
            == client.get(reference.headers["Location"]).json()
            == DATA["reference"]
        )
        assert (
            client.get("/v1/references/synthetic-reference/structures?limit=100").json()
            == DATA["structure_page"]
        )
        structure = client.post("/v1/structures", json=structure_request())
        assert structure.status_code == 201
        assert structure.headers["Location"] == "/v1/structures/synthetic-structure"
        assert (
            structure.json()
            == client.get(structure.headers["Location"]).json()
            == DATA["structure"]
        )
        raw = client.get(structure.json()["artifact_url"])
        assert raw.status_code == 200 and raw.content == RAW
        assert raw.headers["content-type"] == "chemical/x-mmcif"
        assert int(raw.headers["content-length"]) == len(RAW)
        assert raw.headers["x-checksum-sha256"] == hashlib.sha256(RAW).hexdigest()
        assert raw.headers["etag"] == '"' + hashlib.sha256(RAW).hexdigest() + '"'
        assert DATA["structure"]["descriptor"]["raw_artifact"]["byte_size"] == len(RAW)
        assert (
            DATA["structure"]["descriptor"]["raw_artifact"]["content_hash"]["sha256"]
            == hashlib.sha256(RAW).hexdigest()
        )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "gene=",
        "gene=A%20B",
        "gene=SYNTH&limit=0",
        "gene=SYNTH&limit=101",
        "gene=SYNTH&limit=1.0",
        "gene=SYNTH&taxon_id=0",
        "gene=SYNTH&taxon_id=true",
        "gene=SYNTH&cursor=",
        "gene=SYNTH&cursor=" + "a" * 2049,
        "gene=SYNTH&unknown=1",
    ],
)
def test_bad_query_envelope(query: str) -> None:
    with TestClient(contract_app()) as client:
        response = client.get("/v1/proteins?" + query)
    assert response.status_code == 400
    assert (
        dto.ErrorResponse.model_validate(response.json()).error.code == "INVALID_QUERY"
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"accession": "P00001-2", "expected_sequence_sha256": "a" * 64},
        {"accession": "p00001", "expected_sequence_sha256": "a" * 64},
        {"accession": "P00001", "expected_sequence_sha256": "A" * 64},
        {
            "accession": "P00001",
            "expected_sequence_sha256": "a" * 64,
            "url": "https://example.invalid",
        },
    ],
)
def test_bad_reference_body_envelope(body: dict[str, Any]) -> None:
    with TestClient(contract_app()) as client:
        response = client.post("/v1/references", json=body)
    assert response.status_code == 422
    assert dto.ErrorResponse.model_validate(response.json()).error.retryable is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator_id", {"state": "unavailable", "value": None, "reason": "Absent."}),
        ("expected_source_revision", {"state": "present", "value": 1, "reason": None}),
        ("reference_id", "../private"),
        ("url", "https://example.invalid"),
    ],
)
def test_bad_structure_selection(field: str, value: object) -> None:
    body = structure_request()
    body[field] = value
    with TestClient(contract_app()) as client:
        response = client.post("/v1/structures", json=body)
    assert response.status_code == 422
    dto.ErrorResponse.model_validate(response.json())


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "INVALID_CURSOR", False),
        (404, "NOT_FOUND", False),
        (409, "SOURCE_CHANGED", False),
        (413, "SIZE_LIMIT", False),
        (422, "UNSUPPORTED_ISOFORM", False),
        (429, "ADMISSION_LIMIT", True),
        (502, "INVALID_UPSTREAM", False),
        (503, "UPSTREAM_UNAVAILABLE", True),
        (504, "UPSTREAM_TIMEOUT", True),
    ],
)
def test_declared_error_envelope(status: int, code: str, retryable: bool) -> None:
    app = FastAPI()

    @app.get("/v1/example", response_model=dto.ErrorResponse, status_code=status)
    def failure() -> object:
        return error(code, retryable=retryable)

    with TestClient(app) as client:
        response = client.get("/v1/example")
    assert response.status_code == status
    assert dto.ErrorResponse.model_validate(response.json()).error.code == code
    assert response.json()["error"]["retryable"] is retryable


def test_response_validation_is_enforced() -> None:
    app = FastAPI()

    @app.get("/v1/example", response_model=dto.ReferenceResponse)
    def malformed() -> object:
        return {"reference_id": "missing-everything-else"}

    with TestClient(app) as client, pytest.raises(ResponseValidationError):
        client.get("/v1/example")


def test_openapi_contract_and_production_scope() -> None:
    with TestClient(contract_app()) as client:
        schema = client.get("/openapi.json").json()
    assert len(schema["paths"]) == 8  # eight proposed operations, harness only
    assert schema["paths"]["/v1/references"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ReferenceResponse"}
    query = schema["paths"]["/v1/proteins"]["get"]["parameters"]
    limit = next(param for param in query if param["name"] == "limit")
    assert limit["schema"]["default"] == 20
    assert limit["schema"]["maximum"] == 100
    with TestClient(create_app()) as client:
        paths = client.get("/openapi.json").json()["paths"]
        # M4 intentionally replaces the historical health-only route assertion;
        # the fixed harness and frozen schema above remain compatibility evidence.
        assert "/health" in paths and "/v1/proteins" in paths
        assert len(paths) == 13


def test_frozen_http_schema_matches_models_and_fixtures() -> None:
    schema = contract_schema()
    assert (
        json.loads(
            (ROOT / "docs/schemas/neurofold-biological-http-1.schema.json").read_bytes()
        )
        == schema
    )
    Draft202012Validator.check_schema(schema)
    examples: list[tuple[type[BaseModel], object]] = [
        (dto.ProteinPageResponse, DATA["protein_page"]),
        (dto.ProteinResponse, DATA["reference"]["protein"]),
        (dto.ReferenceResponse, DATA["reference"]),
        (dto.StructurePageResponse, DATA["structure_page"]),
        (dto.StructureResponse, DATA["structure"]),
        (dto.StructureRequest, structure_request()),
        (dto.ErrorResponse, error("NOT_FOUND")),
    ]
    for model, example in examples:
        selected = {**schema, "$ref": "#/$defs/" + model.__name__}
        Draft202012Validator(selected).validate(example)
        model.model_validate(example)


def test_query_defaults_and_strict_types() -> None:
    assert dto.ProteinQuery(gene="SYNTH").limit == 20
    assert dto.ProteinQuery.model_validate({"gene": "SYNTH", "limit": "2"}).limit == 2
    for value in [True, 1.0, " 2", "2.0", "-2"]:
        with pytest.raises(ValueError):
            dto.PageQuery.model_validate({"limit": value})
    body = structure_request()
    body["expected_source_revision"] = {
        "state": "unavailable",
        "value": None,
        "reason": "Source did not publish a revision; pinning policy is deferred.",
    }
    dto.StructureRequest.model_validate(body)
