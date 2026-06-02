"""FastAPI dependency providers."""

from collections.abc import Generator

from fastapi import Request

from app.services.pipeline import VerificationPipeline


def get_pipeline(request: Request) -> VerificationPipeline:
    """Return the application-wide verification pipeline."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise RuntimeError("Verification pipeline is not initialized")
    return pipeline


def get_db() -> Generator[None, None, None]:
    """Placeholder database dependency.

    Phase 9 replaces this with a real SQLAlchemy session provider.
    """
    yield None
