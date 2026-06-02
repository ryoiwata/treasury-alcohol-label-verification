import pytest

from app.config import AppConfig, get_required_env, load_and_validate_config

REQUIRED_ENV_VARS = (
    "AZURE_VISION_ENDPOINT",
    "AZURE_VISION_KEY",
    "OPENAI_API_KEY",
)

OPTIONAL_ENV_VARS = (
    "DATABASE_URL",
    "LOG_LEVEL",
    "MAX_BATCH_SIZE",
    "MATCH_THRESHOLD",
    "WARNING_THRESHOLD",
)


def clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear config environment variables for deterministic tests."""
    for name in (*REQUIRED_ENV_VARS, *OPTIONAL_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


def set_required_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required config environment variables to test values."""
    monkeypatch.setenv(
        "AZURE_VISION_ENDPOINT",
        "https://example.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_VISION_KEY", "test-azure-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")


def test_get_required_env_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REQUIRED_ENV", "present")

    assert get_required_env("TEST_REQUIRED_ENV") == "present"


def test_get_required_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_REQUIRED_ENV", raising=False)

    with pytest.raises(RuntimeError, match="TEST_REQUIRED_ENV"):
        get_required_env("TEST_REQUIRED_ENV")


def test_get_required_env_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REQUIRED_ENV", "")

    with pytest.raises(RuntimeError):
        get_required_env("TEST_REQUIRED_ENV")


def test_load_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_config_env(monkeypatch)
    set_required_config_env(monkeypatch)

    config = load_and_validate_config()

    assert isinstance(config, AppConfig)
    assert config.azure_vision_endpoint == "https://example.cognitiveservices.azure.com"
    assert config.azure_vision_key == "test-azure-key"
    assert config.openai_api_key == "test-openai-key"
    assert config.database_url == "sqlite:///./verification.db"
    assert config.log_level == "info"
    assert config.max_batch_size == 50
    assert config.max_file_size_bytes == 10 * 1024 * 1024
    assert config.ocr_timeout_seconds == 30.0
    assert config.gpt_timeout_seconds == 60.0
    assert config.ocr_concurrency_limit == 5
    assert config.gpt_concurrency_limit == 3


def test_load_config_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_config_env(monkeypatch)
    monkeypatch.setenv(
        "AZURE_VISION_ENDPOINT",
        "https://example.cognitiveservices.azure.com",
    )
    monkeypatch.setenv("AZURE_VISION_KEY", "test-azure-key")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_and_validate_config()


def test_load_config_custom_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_config_env(monkeypatch)
    set_required_config_env(monkeypatch)
    monkeypatch.setenv("MATCH_THRESHOLD", "0.90")
    monkeypatch.setenv("WARNING_THRESHOLD", "0.80")

    config = load_and_validate_config()

    assert config.comparison_config.match_threshold == 0.90
    assert config.comparison_config.warning_threshold == 0.80
