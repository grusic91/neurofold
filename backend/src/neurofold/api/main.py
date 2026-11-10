"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from neurofold.api.health import router as health_router


def create_app() -> FastAPI:
    """Create the API without initializing models or scientific dependencies."""
    application = FastAPI(title="NeuroFold", version="0.1.0")
    application.include_router(health_router)
    return application


app = create_app()
