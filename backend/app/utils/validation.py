"""Upload validation helpers."""

from fastapi import UploadFile

from app.services.exceptions import InvalidImageError
from app.utils.constants import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE_BYTES


async def validate_upload(file: UploadFile) -> bytes:
    """Validate an uploaded image/PDF and return its bytes."""
    _validate_filename(file.filename)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidImageError("Unsupported file type")

    content = await file.read()

    if not content:
        raise InvalidImageError("Uploaded file is empty")

    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise InvalidImageError("Uploaded file exceeds maximum size")

    if not _validate_magic_bytes(content, file.content_type):
        raise InvalidImageError("File contents do not match declared file type")

    return content


def _validate_filename(filename: str | None) -> None:
    """Reject missing names and path traversal patterns."""
    if not filename:
        raise InvalidImageError("Uploaded file must have a filename")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise InvalidImageError("Invalid filename")


def _validate_magic_bytes(content: bytes, content_type: str | None) -> bool:
    """Return whether file bytes match the declared content type."""
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG")
    if content_type == "application/pdf":
        return content.startswith(b"%PDF")
    return False
