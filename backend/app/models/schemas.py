"""Pydantic request and response schemas for label verification."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationData(BaseModel):
    """Data from the COLA application that the label must match."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brand name as submitted in application",
    )
    class_type: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Class/type designation (e.g., Kentucky Straight Bourbon Whiskey)",
    )
    abv: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Alcohol content as a number or percentage (e.g., '45' or '45%')",
    )
    net_contents: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Net contents with unit (e.g., '750 mL')",
    )
    warning_statement: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Full government warning statement text",
    )
    producer: str | None = Field(
        None,
        max_length=500,
        description="Name and address of bottler/producer",
    )
    origin: str | None = Field(
        None,
        max_length=200,
        description="Country of origin (for imports)",
    )


class ExtractedFields(BaseModel):
    """Fields extracted from the label image by the AI pipeline."""

    brand_name: str | None = None
    class_type: str | None = None
    abv: str | None = None
    net_contents: str | None = None
    warning_statement: str | None = None
    producer: str | None = None
    origin: str | None = None
    raw_ocr_text: str | None = Field(None, description="Full OCR text for debugging")


class FieldComparison(BaseModel):
    """Result of comparing one extracted field against the application data."""

    field: str = Field(..., description="Field name (brand_name, abv, etc.)")
    status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"]
    extracted: str | None = Field(None, description="Value extracted from label image")
    expected: str = Field(..., description="Value from application data")
    confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="OCR confidence for this field",
    )
    method: Literal[
        "exact_match",
        "fuzzy_match",
        "numeric_match",
        "normalized_match",
    ]
    similarity: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Similarity score (for fuzzy matches)",
    )
    note: str | None = Field(
        None,
        description="Human-readable explanation of the comparison result",
    )


class ImageQuality(BaseModel):
    """Assessment of the uploaded image quality."""

    readable: bool = Field(
        ...,
        description="Whether the image text was readable enough to extract",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Detected issues (glare, angle, blur, low_resolution)",
    )


class VerificationResult(BaseModel):
    """Complete verification result for a single label."""

    id: str = Field(..., description="Unique verification ID (ver_<uuid>)")
    status: Literal["PASS", "REVIEW_NEEDED", "FAIL"]
    processing_time_ms: int = Field(
        ...,
        description="Total processing time in milliseconds",
    )
    fields: list[FieldComparison] = Field(
        ...,
        description="Per-field comparison results",
    )
    image_quality: ImageQuality
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BatchStatus(BaseModel):
    """Status of a batch verification job."""

    batch_id: str
    status: Literal["processing", "complete", "failed"]
    total: int = Field(..., description="Total labels in batch")
    completed: int = Field(..., description="Labels processed so far")
    results: list[VerificationResult] | None = Field(
        None,
        description="Results when complete",
    )


class HistoryResponse(BaseModel):
    """Paginated history query response."""

    total: int
    limit: int
    offset: int
    results: list[VerificationResult]


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
