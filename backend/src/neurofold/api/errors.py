"""Sanitized, typed HTTP error translation; never classify exception text."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from neurofold.api.configuration import ConfigurationError
from neurofold.api.execution import AdmissionLimit, OperationTimeout
from neurofold.core.errors import ArchiveConflict, ArchiveIntegrityError, ResourceLimit
from neurofold.core.lookup import (
    CursorError,
    ProviderError,
    ProviderSelectionError,
    ProviderTimeout,
    ProviderValidationError,
    SourceChanged,
    UnsupportedIdentifier,
)
from neurofold.core.structures import (
    RevisionUnavailable,
    StructureSourceChanged,
    UnsupportedStructure,
)


def error_response(
    request_id: str,
    status: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": details or {},
                "request_id": request_id,
            }
        },
        status_code=status,
        headers={
            "X-Request-ID": request_id,
            **({"Retry-After": "1"} if status == 429 else {}),
        },
    )


def translate(
    exc: Exception, request_id: str, *, mutating: bool = False
) -> JSONResponse:
    if isinstance(exc, CursorError):
        return error_response(
            request_id,
            400,
            "INVALID_CURSOR",
            "Cursor is invalid, expired or mismatched.",
            details={"restart_hint": exc.restart_hint},
        )
    if isinstance(exc, KeyError):
        return error_response(
            request_id, 404, "NOT_FOUND", "Requested record or artifact was not found."
        )
    if isinstance(exc, (SourceChanged, StructureSourceChanged)):
        return error_response(
            request_id,
            409,
            "SOURCE_CHANGED",
            "Source changed. Inspect and select again.",
            details={"expected": exc.expected, "actual": exc.actual},
        )
    if isinstance(exc, ArchiveConflict):
        return error_response(
            request_id,
            409,
            "ARCHIVE_CONFLICT",
            "Immutable publication conflicts with an existing record.",
        )
    if isinstance(exc, ArchiveIntegrityError):
        return error_response(
            request_id,
            500,
            "ARCHIVE_INTEGRITY",
            "Retained data failed integrity verification. Contact the local operator.",
        )
    if isinstance(exc, ResourceLimit):
        return error_response(
            request_id,
            413,
            "SIZE_LIMIT",
            "Input exceeds the supported resource profile.",
        )
    if isinstance(
        exc,
        (
            UnsupportedIdentifier,
            UnsupportedStructure,
            RevisionUnavailable,
            ProviderSelectionError,
        ),
    ):
        return error_response(
            request_id,
            422,
            "INVALID_SELECTION",
            "Unsupported selection or unavailable revision. "
            "Inspect and select explicitly.",
        )
    if isinstance(exc, AdmissionLimit):
        return error_response(
            request_id,
            429,
            "ADMISSION_LIMIT",
            "All blocking workers are busy. Retry later.",
            retryable=True,
        )
    if isinstance(exc, OperationTimeout):
        return error_response(
            request_id,
            504,
            "OPERATION_TIMEOUT",
            "Response budget expired. Work may still finish.",
            retryable=not mutating,
            details={"publication_may_complete": mutating, "automatic_retry": False},
        )
    if isinstance(exc, ProviderTimeout):
        return error_response(
            request_id,
            504,
            "UPSTREAM_TIMEOUT",
            "Upstream operation timed out. Retry after reinspection.",
            retryable=True,
        )
    if isinstance(exc, ProviderValidationError):
        return error_response(
            request_id,
            502,
            "INVALID_UPSTREAM",
            "Upstream content is invalid or inconsistent.",
        )
    if isinstance(exc, ProviderError):
        return error_response(
            request_id,
            503,
            "UPSTREAM_UNAVAILABLE",
            "Upstream service is unavailable. Retained records remain readable.",
            retryable=True,
        )
    if isinstance(exc, ConfigurationError):
        return error_response(
            request_id,
            503,
            "CONFIGURATION_ERROR",
            "Archive configuration is unsupported. Contact the local operator.",
        )
    if isinstance(exc, OSError):
        return error_response(
            request_id,
            503,
            "ARCHIVE_UNAVAILABLE",
            "Archive IO is unavailable. Contact the local operator.",
            details={"publication_may_complete": True} if mutating else {},
        )
    return error_response(
        request_id,
        500,
        "INTERNAL_ERROR",
        "The operation could not be completed.",
        details={"publication_may_complete": True} if mutating else {},
    )


async def invalid_request(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    query = any(issue["loc"][0] == "query" for issue in exc.errors())
    return error_response(
        request.state.request_id,
        400 if query else 422,
        "INVALID_QUERY" if query else "INVALID_INPUT",
        "Request validation failed. Check field types, identifiers and selection.",
    )


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if request.url.path.startswith("/v1/"):
        response = error_response(
            request.state.request_id,
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Requested operation is unavailable.",
        )
        if exc.status_code == 405 and exc.headers and "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
    )
