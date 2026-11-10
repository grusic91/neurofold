"""Explicit application factory and ASGI entry point, with lazy service IO."""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from neurofold.api.composition import LazyServices, Services, compose
from neurofold.api.configuration import Settings
from neurofold.api.errors import error_response, http_error, invalid_request
from neurofold.api.execution import BlockingExecutor
from neurofold.api.health import router as health_router
from neurofold.api.routes import biological_router


def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


class Boundary:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/v1/"):
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        request = Request(scope)
        keys = list(request.query_params.keys())
        allowed = (
            {"gene", "taxon_id", "cursor", "limit"}
            if scope["path"] == "/v1/proteins"
            else {"cursor", "limit"}
            if scope["path"].startswith("/v1/references/")
            and scope["path"].endswith("/structures")
            else set()
        )
        if any(
            len(request.query_params.getlist(key)) != 1 or key not in allowed
            for key in keys
        ) or any(
            ord(character) < 32 or ord(character) == 127
            for value in request.query_params.values()
            for character in value
        ):
            await error_response(
                request_id,
                400,
                "INVALID_QUERY",
                "Unknown or duplicate query parameter.",
            )(scope, receive, send)
            return
        body = bytearray()
        if scope["method"] == "POST":
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > 16384:
                    await error_response(
                        request_id, 413, "SIZE_LIMIT", "Request body exceeds 16 KiB."
                    )(scope, receive, send)
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            try:
                if body:
                    json.loads(body, object_pairs_hook=unique_fields)
            except (ValueError, RecursionError):
                await error_response(
                    request_id, 422, "INVALID_INPUT", "Invalid JSON body."
                )(scope, receive, send)
                return

        async def replay() -> Message:
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        async def identified(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() != b"x-request-id"]
                message["headers"] = headers + [
                    (b"x-request-id", request_id.encode("ascii"))
                ]
            await send(message)

        await self.app(
            scope, replay if scope["method"] == "POST" else receive, identified
        )


def create_app(
    *,
    settings: Settings | None = None,
    service_factory: Callable[[], Services] | None = None,
) -> FastAPI:
    config = settings or Settings.from_environment()
    executor = BlockingExecutor(config.workers, config.operation_seconds)
    services = LazyServices(service_factory or (lambda: compose(config)))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await executor.close()

    application = FastAPI(title="NeuroFold", version="0.1.0", lifespan=lifespan)
    application.add_middleware(Boundary)
    application.add_exception_handler(RequestValidationError, invalid_request)  # type: ignore[arg-type]
    application.add_exception_handler(HTTPException, http_error)  # type: ignore[arg-type]
    application.include_router(health_router)
    application.include_router(biological_router(services, executor))
    return application


app = create_app()
