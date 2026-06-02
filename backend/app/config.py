from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise if it is unset."""
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class ComparisonConfig:
    """Comparison threshold configuration."""

    match_threshold: float = 0.95
    warning_threshold: float = 0.85
    abv_tolerance: float = 0.5
    # TODO Phase 2: source defaults from constants.py


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    azure_vision_endpoint: str
    azure_vision_key: str
    openai_api_key: str
    database_url: str = "sqlite:///./verification.db"
    log_level: str = "info"
    max_batch_size: int = 50
    max_file_size_bytes: int = 10 * 1024 * 1024
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
        match_threshold=float(os.getenv("MATCH_THRESHOLD", "0.95")),
        warning_threshold=float(os.getenv("WARNING_THRESHOLD", "0.85")),
    )

    config = AppConfig(
        azure_vision_endpoint=azure_vision_endpoint,
        azure_vision_key=azure_vision_key,
        openai_api_key=openai_api_key,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./verification.db"),
        log_level=os.getenv("LOG_LEVEL", "info"),
        max_batch_size=int(os.getenv("MAX_BATCH_SIZE", "50")),
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
