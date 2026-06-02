"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import load_and_validate_config
from app.routers import batch, history, verify
from app.services.comparator import Comparator
from app.services.exceptions import InvalidImageError, OCRExtractionError, ParserError
from app.services.ocr import OCRService
from app.services.parser import GPTParser
from app.services.pipeline import VerificationPipeline


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize application-wide services."""
    config = load_and_validate_config()

    ocr = OCRService(
        endpoint=config.azure_vision_endpoint,
        key=config.azure_vision_key,
        timeout_seconds=config.ocr_timeout_seconds,
    )
    parser = GPTParser(
        api_key=config.openai_api_key,
        timeout_seconds=config.gpt_timeout_seconds,
    )
    comparator = Comparator(config.comparison_config)

    app.state.config = config
    app.state.ocr_service = ocr
    app.state.parser_service = parser
    app.state.comparator = comparator
    app.state.pipeline = VerificationPipeline(
        ocr=ocr,
        parser=parser,
        comparator=comparator,
    )

    try:
        yield
    finally:
        await ocr.close()
        await parser.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    api = FastAPI(title="TTB Label Verification", lifespan=lifespan)

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    api.include_router(verify.router, prefix="/api")
    api.include_router(batch.router, prefix="/api")
    api.include_router(history.router, prefix="/api")

    @api.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @api.exception_handler(InvalidImageError)
    async def invalid_image_handler(
        request: Request,
        exc: InvalidImageError,
    ) -> JSONResponse:
        _ = request
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_image", "detail": str(exc)},
        )

    @api.exception_handler(OCRExtractionError)
    async def ocr_error_handler(
        request: Request,
        exc: OCRExtractionError,
    ) -> JSONResponse:
        _ = request
        return JSONResponse(
            status_code=502,
            content={"error": "ocr_extraction_failed", "detail": str(exc)},
        )

    @api.exception_handler(ParserError)
    async def parser_error_handler(
        request: Request,
        exc: ParserError,
    ) -> JSONResponse:
        _ = request
        return JSONResponse(
            status_code=502,
            content={"error": "parser_failed", "detail": str(exc)},
        )

    @api.exception_handler(Exception)
    async def generic_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        _ = request
        _ = exc
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "An unexpected error occurred",
            },
        )

    return api


app = create_app()
