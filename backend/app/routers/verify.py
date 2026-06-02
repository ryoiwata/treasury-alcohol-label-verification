"""Single-label verification routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.schemas import ApplicationData, VerificationResult
from app.services.dependencies import get_pipeline
from app.services.pipeline import VerificationPipeline
from app.utils.validation import validate_upload

router = APIRouter(tags=["verify"])


@router.post("/verify", response_model=VerificationResult)
async def verify_label(
    file: Annotated[UploadFile, File(...)],
    application_data: Annotated[str, Form(...)],
    pipeline: Annotated[VerificationPipeline, Depends(get_pipeline)],
) -> VerificationResult:
    """Verify one uploaded label against submitted application data."""
    image_bytes = await validate_upload(file)

    try:
        parsed_application_data = ApplicationData.model_validate_json(application_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    result = await pipeline.verify(
        image_bytes=image_bytes,
        content_type=file.content_type or "",
        application_data=parsed_application_data,
    )

    # Phase 9: save verification result to SQLite.
    return result
