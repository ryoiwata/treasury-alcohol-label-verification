"""Tests for FastAPI endpoints."""

import json
from typing import Any

from fastapi.testclient import TestClient


def test_health(test_client: TestClient) -> None:
    response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_happy_path(
    test_client: TestClient,
    valid_png_bytes: bytes,
    application_data_json: str,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("label.png", valid_png_bytes, "image/png")},
        data={"application_data": application_data_json},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("ver_")
    assert body["status"] in {"PASS", "REVIEW_NEEDED", "FAIL"}
    assert body["status"] == "PASS"
    assert body["processing_time_ms"] >= 0
    assert body["fields"]
    assert body["image_quality"]["readable"] is True


def test_verify_invalid_file_type(
    test_client: TestClient,
    application_data_json: str,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("label.txt", b"hello", "text/plain")},
        data={"application_data": application_data_json},
    )

    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert "detail" in body


def test_verify_magic_bytes_mismatch(
    test_client: TestClient,
    application_data_json: str,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("label.png", b"not a png", "image/png")},
        data={"application_data": application_data_json},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_image"


def test_verify_missing_application_data(
    test_client: TestClient,
    valid_png_bytes: bytes,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("label.png", valid_png_bytes, "image/png")},
    )

    assert response.status_code == 422


def test_verify_malformed_application_json(
    test_client: TestClient,
    valid_png_bytes: bytes,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("label.png", valid_png_bytes, "image/png")},
        data={"application_data": "not json"},
    )

    assert response.status_code == 422


def test_verify_rejects_path_traversal_filename(
    test_client: TestClient,
    valid_png_bytes: bytes,
    application_data_json: str,
) -> None:
    response = test_client.post(
        "/api/verify",
        files={"file": ("../../etc/passwd", valid_png_bytes, "image/png")},
        data={"application_data": application_data_json},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_image"


def test_create_batch_and_get_status(
    test_client: TestClient,
    valid_png_bytes: bytes,
    application_data_payload: dict[str, Any],
) -> None:
    files = [
        ("files", ("label1.png", valid_png_bytes, "image/png")),
        ("files", ("label2.png", valid_png_bytes, "image/png")),
        ("files", ("label3.png", valid_png_bytes, "image/png")),
    ]
    data = {
        "application_data": json.dumps(
            [
                application_data_payload,
                application_data_payload,
                application_data_payload,
            ]
        )
    }

    create_response = test_client.post("/api/batch", files=files, data=data)

    assert create_response.status_code == 202
    created = create_response.json()
    assert created["batch_id"].startswith("bat_")
    assert created["status"] == "complete"
    assert created["total"] == 3
    assert created["completed"] == 3
    assert len(created["results"]) == 3

    get_response = test_client.get(f"/api/batch/{created['batch_id']}")

    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["batch_id"] == created["batch_id"]


def test_get_unknown_batch_returns_404(test_client: TestClient) -> None:
    response = test_client.get("/api/batch/bat_unknown")

    assert response.status_code == 404


def test_batch_file_data_count_mismatch(
    test_client: TestClient,
    valid_png_bytes: bytes,
    application_data_payload: dict[str, Any],
) -> None:
    files = [
        ("files", ("label1.png", valid_png_bytes, "image/png")),
        ("files", ("label2.png", valid_png_bytes, "image/png")),
    ]
    data = {"application_data": json.dumps([application_data_payload])}

    response = test_client.post("/api/batch", files=files, data=data)

    assert response.status_code == 400


def test_history_stub(test_client: TestClient) -> None:
    response = test_client.get("/api/history")

    assert response.status_code == 200
    body = response.json()
    assert body == {"total": 0, "limit": 20, "offset": 0, "results": []}


def test_history_limit_validation(test_client: TestClient) -> None:
    response = test_client.get("/api/history?limit=101")

    assert response.status_code == 422
