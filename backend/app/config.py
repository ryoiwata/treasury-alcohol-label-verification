from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from app.services.comparator import ComparisonConfig
from app.utils.constants import (
    DEFAULT_ABV_TOLERANCE,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    MAX_BATCH_SIZE,
    MAX_IMAGE_SIZE_BYTES,
)

logger = logging.getLogger(__name__)


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise if it is unset."""
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    azure_vision_endpoint: str
    azure_vision_key: str
    openai_api_key: str
    database_url: str = "sqlite:///./verification.db"
    log_level: str = "info"
    max_batch_size: int = MAX_BATCH_SIZE
    max_file_size_bytes: int = MAX_IMAGE_SIZE_BYTES
    ocr_timeout_seconds: float = 30.0
    gpt_timeout_seconds: float = 60.0
    ocr_concurrency_limit: int = 5
    gpt_concurrency_limit: int = 3
    comparison_config: ComparisonConfig = field(default_factory=ComparisonConfig)


def load_and_validate_config() -> AppConfig:
    """Load environment configuration and fail fast on missing secrets."""
    load_dotenv()

    azure_vision_endpoint = get_required_env("AZURE_VISION_ENDPOINT")
    azure_vision_key = get_required_env("AZURE_VISION_KEY")
    openai_api_key = get_required_env("OPENAI_API_KEY")

    comparison_config = ComparisonConfig(
        match_threshold=float(
            os.getenv("MATCH_THRESHOLD", str(DEFAULT_MATCH_THRESHOLD))
        ),
        warning_threshold=float(
            os.getenv("WARNING_THRESHOLD", str(DEFAULT_WARNING_THRESHOLD))
        ),
        abv_tolerance=float(os.getenv("ABV_TOLERANCE", str(DEFAULT_ABV_TOLERANCE))),
    )

    config = AppConfig(
        azure_vision_endpoint=azure_vision_endpoint,
        azure_vision_key=azure_vision_key,
        openai_api_key=openai_api_key,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./verification.db"),
        log_level=os.getenv("LOG_LEVEL", "info"),
        max_batch_size=int(os.getenv("MAX_BATCH_SIZE", str(MAX_BATCH_SIZE))),
        max_file_size_bytes=MAX_IMAGE_SIZE_BYTES,
        comparison_config=comparison_config,
    )

    logger.info(
        "Config loaded",
        extra={
            "azure_vision_key_set": bool(config.azure_vision_key),
            "openai_api_key_set": bool(config.openai_api_key),
        },
    )
    return config
