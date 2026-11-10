"""Operational biological HTTP boundary; orchestration lives in services."""

import logging
from collections.abc import Callable
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request, Response
from pydantic import JsonValue

from neurofold.api import biological as dto
from neurofold.api.composition import LazyServices, Services
from neurofold.api.errors import translate
from neurofold.api.execution import BlockingExecutor
from neurofold.core.canonical import sha256_bytes
from neurofold.core.lookup import PinReceipt
from neurofold.core.provenance import ContentHash, HashEncoding, Metadata
from neurofold.core.structures import StructureCheck, StructureImport


class CheckDTO(dto.DTO):
    contract = StructureCheck
    source_receipt_id: dto.Text
    checked_at: dto.Text
    response_status: Literal[200, 304]
    response_headers: dict[str, JsonValue]
    adapter_version: dto.Text


class PinAuditResponse(dto.RequestDTO):
    schema_version: Literal["neurofold-reference-audit-http/1"]
    retained_hash: dto.HashDTO
    reference_id: dto.OpaqueID
    source_receipt_id: dto.Text
    checked_at: dto.Text
    response_status: Literal[200, 304]
    response_headers: dict[str, JsonValue]
    adapter_version: dto.Text


class StructureAuditResponse(dto.RequestDTO):
    schema_version: Literal["neurofold-structure-audit-http/1"]
    retained_hash: dto.HashDTO
    descriptor: dto.StructureDescriptorDTO
    mapping: dto.ResidueMapDTO
    reference: dto.ContentReferenceDTO
    checks: list[CheckDTO]
    parsing: dict[str, JsonValue]
    alignment: dict[str, JsonValue]


# Headers are projected deliberately for HTTP. Full original check events remain
# immutable in the archive; the retained hash identifies those original bytes.
PUBLIC_HEADERS = frozenset(
    {
        "content-type",
        "content-encoding",
        "content-length",
        "etag",
        "last-modified",
        "date",
        "x-uniprot-release",
        "x-uniprot-release-date",
        "retry-after",
    }
)


def public_headers(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if key.lower() in PUBLIC_HEADERS}


def pin_audit_response(record: PinReceipt) -> PinAuditResponse:
    value = record.to_dict()
    value["schema_version"] = "neurofold-reference-audit-http/1"
    value["retained_hash"] = ContentHash(
        sha256=sha256_bytes(record.to_json()), encoding=HashEncoding.CANONICAL_JSON
    ).to_dict()
    value["response_headers"] = public_headers(record.response_headers.to_dict())
    return PinAuditResponse.model_validate(value)


def structure_audit_response(record: StructureImport) -> StructureAuditResponse:
    value = record.to_dict()
    value["schema_version"] = "neurofold-structure-audit-http/1"
    value["retained_hash"] = ContentHash(
        sha256=sha256_bytes(record.to_json()), encoding=HashEncoding.CANONICAL_JSON
    ).to_dict()
    value["checks"] = [
        {
            **check.to_dict(),
            "response_headers": public_headers(check.response_headers.to_dict()),
        }
        for check in record.checks
    ]
    return StructureAuditResponse.model_validate(value)


def json_response(
    value: dto.DTO | dto.StructureResponse | PinAuditResponse | StructureAuditResponse,
    *,
    location: str | None = None,
) -> Response:
    # Validation and JSON serialization run inside the admitted blocking worker.
    return Response(
        value.model_dump_json(),
        status_code=201 if location else 200,
        media_type="application/json",
        headers={"Location": location} if location else {},
    )


def structure_response(record: StructureImport, *, created: bool = False) -> Response:
    descriptor = record.descriptor
    value = dto.StructureResponse(
        descriptor=dto.StructureDescriptorDTO.from_core(descriptor),
        mapping=dto.ResidueMapDTO.from_core(record.mapping),
        artifact_url=f"/v1/artifacts/{descriptor.raw_artifact.artifact_id}",
    )
    return json_response(
        value, location=f"/v1/structures/{descriptor.structure_id}" if created else None
    )


def biological_router(services: LazyServices, executor: BlockingExecutor) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        responses={
            status: {"model": dto.ErrorResponse}
            for status in (400, 404, 405, 409, 413, 422, 429, 500, 502, 503, 504)
        },
    )

    async def invoke(
        request: Request, operation: Callable[[Services], Response]
    ) -> Response:
        request_id = getattr(request.state, "request_id", uuid4().hex)
        mutating = request.method == "POST"

        def execute() -> Response:
            try:
                response = operation(services.get())
            except Exception as exc:
                if mutating:
                    logging.getLogger("uvicorn.error").error(
                        "publication failed request_id=%s kind=%s",
                        request_id,
                        type(exc).__name__,
                    )
                raise
            if mutating:
                logging.getLogger("uvicorn.error").info(
                    "publication completed request_id=%s location=%s",
                    request_id,
                    response.headers.get("Location", "unavailable"),
                )
            return response

        try:
            return await executor.run(execute)
        except Exception as exc:
            return translate(exc, request_id, mutating=mutating)

    @router.get("/proteins", response_model=dto.ProteinPageResponse)
    async def proteins(
        request: Request, query: Annotated[dto.ProteinQuery, Query()]
    ) -> Response:
        return await invoke(
            request,
            lambda s: json_response(
                dto.ProteinPageResponse.from_core(
                    s.biological.search(**query.model_dump())
                )
            ),
        )

    @router.get("/proteins/{accession}", response_model=dto.ProteinResponse)
    async def protein(request: Request, accession: dto.Accession) -> Response:
        return await invoke(
            request,
            lambda s: json_response(
                dto.ProteinResponse.from_core(s.biological.protein(accession))
            ),
        )

    @router.post("/references", status_code=201, response_model=dto.ReferenceResponse)
    async def pin(request: Request, body: dto.ReferenceRequest) -> Response:
        def operation(s: Services) -> Response:
            record = s.references.pin(body.accession, body.expected_sequence_sha256)
            return json_response(
                dto.ReferenceResponse.from_core(record),
                location=f"/v1/references/{record.reference_id}",
            )

        return await invoke(request, operation)

    @router.get("/references/{reference_id}", response_model=dto.ReferenceResponse)
    async def reference(request: Request, reference_id: dto.OpaqueID) -> Response:
        return await invoke(
            request,
            lambda s: json_response(
                dto.ReferenceResponse.from_core(s.references.get(reference_id))
            ),
        )

    @router.get("/references/{reference_id}/audit", response_model=PinAuditResponse)
    async def reference_audit(request: Request, reference_id: dto.OpaqueID) -> Response:
        def operation(s: Services) -> Response:
            s.references.get(reference_id)  # Verify the complete retained graph first.
            return json_response(
                pin_audit_response(s.pins.get_pin_receipt(reference_id))
            )

        return await invoke(request, operation)

    @router.get(
        "/references/{reference_id}/structures",
        response_model=dto.StructurePageResponse,
    )
    async def discover(
        request: Request,
        reference_id: dto.OpaqueID,
        query: Annotated[dto.PageQuery, Query()],
    ) -> Response:
        return await invoke(
            request,
            lambda s: json_response(
                dto.StructurePageResponse.from_core(
                    s.biological.discover(reference_id, **query.model_dump())
                )
            ),
        )

    @router.post("/structures", status_code=201, response_model=dto.StructureResponse)
    async def import_structure(
        request: Request, body: dto.StructureRequest
    ) -> Response:
        def operation(s: Services) -> Response:
            record = s.structures.import_request(
                body.reference_id,
                body.entry_id,
                entity_id=body.entity_id,
                label_asym_id=body.label_asym_id,
                model_id=body.model_id,
                assembly_id=Metadata.from_dict(body.assembly_id.model_dump()),
                operator_id=Metadata.from_dict(body.operator_id.model_dump()),
                expected_source_revision=Metadata.from_dict(
                    body.expected_source_revision.model_dump()
                ),
            )
            return structure_response(record, created=True)

        return await invoke(request, operation)

    @router.get("/structures/{structure_id}", response_model=dto.StructureResponse)
    async def structure(request: Request, structure_id: dto.OpaqueID) -> Response:
        return await invoke(
            request, lambda s: structure_response(s.structures.get(structure_id))
        )

    @router.get(
        "/structures/{structure_id}/audit", response_model=StructureAuditResponse
    )
    async def structure_audit(request: Request, structure_id: dto.OpaqueID) -> Response:
        return await invoke(
            request,
            lambda s: json_response(
                structure_audit_response(s.structures.get(structure_id))
            ),
        )

    @router.get(
        "/artifacts/{artifact_id}",
        response_class=Response,
        responses={
            200: {
                "content": {
                    "application/octet-stream": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                }
            }
        },
    )
    async def artifact(request: Request, artifact_id: dto.OpaqueID) -> Response:
        def operation(s: Services) -> Response:
            descriptor, raw = s.biological.artifact(artifact_id)
            compressed = descriptor.media_type == "application/gzip"
            extension = (
                ".gz"
                if compressed
                else ".cif"
                if descriptor.media_type == "chemical/x-mmcif"
                else ".json"
            )
            return Response(
                raw,
                media_type=descriptor.media_type,
                headers={
                    "Content-Length": str(len(raw)),
                    "X-Checksum-SHA256": descriptor.content_hash.sha256,
                    "ETag": '"' + descriptor.content_hash.sha256 + '"',
                    "Content-Disposition": (
                        f'attachment; filename="{artifact_id}{extension}"'
                    ),
                    "X-Artifact-Encoding": "gzip" if compressed else "identity",
                    "Cache-Control": "private, no-transform",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        return await invoke(request, operation)

    return router
