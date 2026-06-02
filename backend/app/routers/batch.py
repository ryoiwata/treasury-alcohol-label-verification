"""Batch verification routes.

Phase 6 uses an in-memory synchronous implementation. Phase 10 replaces this
with async background processing and concurrency limits.
"""

import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.schemas import ApplicationData, BatchStatus
from app.services.dependencies import get_pipeline
from app.services.pipeline import VerificationPipeline
from app.utils.constants import MAX_BATCH_SIZE
from app.utils.validation import validate_upload

router = APIRouter(tags=["batch"])

_BATCHES: dict[str, BatchStatus] = {}


@router.post("/batch", response_model=BatchStatus, status_code=202)
async def create_batch(
    files: Annotated[list[UploadFile], File(...)],
    application_data: Annotated[str, Form(...)],
    pipeline: Annotated[VerificationPipeline, Depends(get_pipeline)],
) -> BatchStatus:
    """Verify a small batch of labels synchronously for Phase 6."""
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BATCH_SIZE} labels per batch.",
        )

    try:
        raw_application_data = json.loads(application_data)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail="application_data must be a JSON array",
        ) from exc

    if not isinstance(raw_application_data, list):
        raise HTTPException(
            status_code=422,
            detail="application_data must be a JSON array",
        )

    if len(raw_application_data) != len(files):
        raise HTTPException(
            status_code=400,
            detail="Number of application data entries must match number of files.",
        )

    parsed_application_data: list[ApplicationData] = []
    for item in raw_application_data:
        try:
            parsed_application_data.append(ApplicationData.model_validate(item))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

    results = []
    for file, app_data in zip(files, parsed_application_data, strict=True):
        image_bytes = await validate_upload(file)
        results.append(
            await pipeline.verify(
                image_bytes=image_bytes,
                content_type=file.content_type or "",
                application_data=app_data,
            )
        )

    batch_id = f"bat_{uuid4().hex[:8]}"
    status = BatchStatus(
        batch_id=batch_id,
        status="complete",
        total=len(files),
        completed=len(results),
        results=results,
    )
    _BATCHES[batch_id] = status
    return status


@router.get("/batch/{batch_id}", response_model=BatchStatus)
async def get_batch(batch_id: str) -> BatchStatus:
    """Return stored batch status."""
    batch = _BATCHES.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch
