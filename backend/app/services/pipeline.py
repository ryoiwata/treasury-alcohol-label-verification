"""End-to-end verification pipeline."""

import time
from uuid import uuid4

from app.models.schemas import ApplicationData, ImageQuality, VerificationResult
from app.services.comparator import Comparator, derive_overall_status
from app.services.ocr import OCRService
from app.services.parser import GPTParser


class VerificationPipeline:
    """Run OCR, parsing, comparison, and result assembly."""

    def __init__(
        self,
        ocr: OCRService,
        parser: GPTParser,
        comparator: Comparator,
    ) -> None:
        self.ocr = ocr
        self.parser = parser
        self.comparator = comparator

    async def verify(
        self,
        image_bytes: bytes,
        content_type: str,
        application_data: ApplicationData,
    ) -> VerificationResult:
        """Verify one label image against submitted application data."""
        start = time.monotonic()

        ocr_result = await self.ocr.extract_text(image_bytes, content_type)
        extracted_fields = await self.parser.extract_fields(ocr_result.text)
        field_results = self.comparator.compare_all(
            extracted_fields,
            application_data,
        )
        overall_status = derive_overall_status(field_results)
        processing_time_ms = int((time.monotonic() - start) * 1000)

        return VerificationResult(
            id=f"ver_{uuid4().hex[:12]}",
            status=overall_status,
            processing_time_ms=processing_time_ms,
            fields=field_results,
            image_quality=ImageQuality(
                readable=bool(ocr_result.text.strip()),
                issues=ocr_result.image_quality_issues,
            ),
        )
