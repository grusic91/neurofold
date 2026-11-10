"""API liveness endpoint independent of prediction runtimes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Liveness status; does not assert model or GPU readiness."""

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report that the API can serve requests."""
    return HealthResponse()
