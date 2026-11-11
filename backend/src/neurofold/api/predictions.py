"""Strict prediction HTTP boundary; storage and supervision remain services."""

import logging
import re
from collections.abc import Callable
from threading import Lock
from typing import Annotated, ClassVar, Literal, Self

from fastapi import APIRouter, Request, Response
from pydantic import Field, JsonValue, RootModel, model_validator

from neurofold.api.biological import ErrorResponse, OpaqueID, RequestDTO
from neurofold.api.errors import translate
from neurofold.api.execution import BlockingExecutor
from neurofold.application.predictions import PredictionService
from neurofold.core.canonical import sha256_bytes
from neurofold.core.orchestration import FailureReason, OrchestrationError
from neurofold.core.prediction_base import PredictionRecord
from neurofold.core.prediction_failure import OperationalFailure
from neurofold.core.prediction_inputs import AdapterCapability, capabilities
from neurofold.core.prediction_jobs import TERMINAL, PredictionJob
from neurofold.core.prediction_outputs import (
    PredictionResult,
    SuccessfulPredictionProvenance,
)

PredictionID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")]


class ScientificDTO(RootModel[dict[str, JsonValue]]):
    """M1 projection checked by the exact strict codec and versioned JSON schema."""

    contract: ClassVar[type[PredictionRecord]]

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        self.contract.from_dict(self.root)
        return self


class JobDTO(ScientificDTO):
    contract = PredictionJob


class CapabilityDTO(ScientificDTO):
    contract = AdapterCapability


class ResultDTO(ScientificDTO):
    contract = PredictionResult


class ManifestDTO(ScientificDTO):
    contract = SuccessfulPredictionProvenance


class FailureDTO(ScientificDTO):
    contract = OperationalFailure


class JobStatus(RequestDTO):
    schema_version: Literal["neurofold-prediction-status/1"]
    job: JobDTO
    operational_failure: FailureReason | None


class Submission(RequestDTO):
    reference_id: OpaqueID
    variant_id: OpaqueID | None
    adapter_profile_id: PredictionID
    parameters: dict[str, int | bool | str]
    seed: Annotated[int, Field(ge=0, le=9007199254740991)]
    msa_artifact_id: PredictionID | None
    retry_of_job_id: PredictionID | None


class Empty(RequestDTO):
    pass


def prediction_router(
    factory: Callable[[], PredictionService], executor: BlockingExecutor
) -> APIRouter:
    router = APIRouter(
        prefix="/v1",
        responses={
            code: {"model": ErrorResponse}
            for code in (400, 404, 405, 409, 413, 422, 429, 500, 503, 504)
        },
    )
    lock = Lock()
    service: PredictionService | None = None

    def get_service() -> PredictionService:
        nonlocal service
        with lock:
            if service is None:
                service = factory()
            return service

    async def invoke(
        request: Request, operation: Callable[[PredictionService], Response]
    ) -> Response:
        def execute() -> Response:
            try:
                response = operation(get_service())
            except Exception as exc:
                logging.getLogger("uvicorn.error").error(
                    "prediction operation failed request_id=%s kind=%s",
                    request.state.request_id,
                    type(exc).__name__,
                )
                raise
            if request.method == "POST":
                logging.getLogger("uvicorn.error").info(
                    "prediction operation completed request_id=%s location=%s",
                    request.state.request_id,
                    response.headers.get("Location", "unavailable"),
                )
            return response

        try:
            return await executor.run(execute)
        except Exception as exc:
            return translate(
                exc, request.state.request_id, mutating=request.method == "POST"
            )

    def status(
        service: PredictionService, job: PredictionJob | str, *, code: int = 200
    ) -> Response:
        job, reason = service.snapshot(job if isinstance(job, str) else job.job_id)
        value = JobStatus(
            schema_version="neurofold-prediction-status/1",
            job=JobDTO.model_validate(job.to_dict()),
            operational_failure=reason,
        )
        return Response(
            value.model_dump_json(),
            status_code=code,
            media_type="application/json",
            headers={
                "Location": f"/v1/prediction-jobs/{job.job_id}",
                **(
                    {"Retry-After": "1"}
                    if job.state not in TERMINAL or code == 202
                    else {}
                ),
            },
        )

    @router.get("/prediction-capabilities", response_model=list[CapabilityDTO])
    async def inspect_capabilities(request: Request) -> Response:
        return Response(
            "[" + ",".join(c.to_json().decode() for c in capabilities()) + "]",
            media_type="application/json",
        )

    @router.post(
        "/prediction-jobs",
        status_code=202,
        response_model=JobStatus,
        openapi_extra={
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,128}$"},
                }
            ]
        },
        responses={
            202: {
                "headers": {
                    "Location": {"schema": {"type": "string"}},
                    "Retry-After": {"schema": {"type": "string"}},
                    "X-Request-ID": {"schema": {"type": "string"}},
                }
            }
        },
    )
    async def submit(request: Request, body: Submission) -> Response:
        keys = request.headers.getlist("idempotency-key")
        if len(keys) != 1 or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", keys[0]) is None:
            return translate(
                OrchestrationError("INVALID_IDEMPOTENCY_KEY"), request.state.request_id
            )
        return await invoke(
            request,
            lambda service: status(
                service, service.submit(key=keys[0], **body.model_dump()), code=202
            ),
        )

    @router.get("/prediction-jobs/{job_id}", response_model=JobStatus)
    async def get(request: Request, job_id: PredictionID) -> Response:
        return await invoke(request, lambda service: status(service, job_id))

    @router.post(
        "/prediction-jobs/{job_id}/cancel",
        response_model=JobStatus,
        responses={202: {"model": JobStatus}},
    )
    async def cancel(request: Request, job_id: PredictionID, body: Empty) -> Response:
        def execute(service: PredictionService) -> Response:
            job = service.cancel(job_id)
            return status(service, job, code=200 if job.state == "cancelled" else 202)

        return await invoke(request, execute)

    @router.get("/prediction-jobs/{job_id}/failure", response_model=FailureDTO)
    async def failure(request: Request, job_id: PredictionID) -> Response:
        return await invoke(
            request,
            lambda service: Response(
                service.jobs.failure(job_id).to_json(), media_type="application/json"
            ),
        )

    @router.get("/prediction-jobs/{job_id}/result", response_model=ResultDTO)
    async def result(request: Request, job_id: PredictionID) -> Response:
        return await invoke(
            request,
            lambda service: Response(
                service.records(job_id)[0].to_json(), media_type="application/json"
            ),
        )

    @router.get("/prediction-jobs/{job_id}/manifest", response_model=ManifestDTO)
    async def manifest(request: Request, job_id: PredictionID) -> Response:
        return await invoke(
            request,
            lambda service: Response(
                service.records(job_id)[1].to_json(), media_type="application/json"
            ),
        )

    @router.get(
        "/prediction-jobs/{job_id}/artifacts/{artifact_id}",
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
    async def artifact(
        request: Request, job_id: PredictionID, artifact_id: PredictionID
    ) -> Response:
        def execute(service: PredictionService) -> Response:
            job = service.get(job_id)
            if job.state != "succeeded":
                raise OrchestrationError("JOB_CONFLICT")
            data, media = service.archive.artifact(job, artifact_id)
            return Response(
                data,
                media_type=media,
                headers={
                    "Content-Disposition": "attachment",
                    "X-Content-Type-Options": "nosniff",
                    "ETag": '"' + sha256_bytes(data) + '"',
                    "X-Checksum-SHA256": sha256_bytes(data),
                    "Cache-Control": "private, no-store",
                },
            )

        return await invoke(request, execute)

    return router
