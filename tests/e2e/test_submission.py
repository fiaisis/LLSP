"""
End-to-end tests for the LLSP submission workflow.

This module tests the full lifecycle of a script submission, execution, and result retrieval.
"""

import json
import os
import threading
import time
from collections.abc import Generator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
import requests  # type: ignore[import-untyped]

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("LLSP_API_KEY", "secret-token")
FIA_API_TOKEN = os.getenv("FIA_API_AUTH_TOKEN", "fia-api-test-token")
CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "8080"))
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

VALID_FIA_STATES = {"SUCCESSFUL", "UNSUCCESSFUL", "ERROR", "NOT_STARTED"}
VALID_FIA_FIELDS = {"state", "status_message", "outputs", "start", "stacktrace", "end"}

received_callbacks: dict[str, dict[str, Any]] = {}


class MockFIAAPICallbackHandler(BaseHTTPRequestHandler):
    """Lightweight HTTP handler simulating fia-api's PATCH /job/{job_id} endpoint."""

    def do_PATCH(self) -> None:
        """Handle incoming PATCH callback requests and validate against fia-api's contract."""
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body) if raw_body else {}

        # Validate schema matches fia-api PartialJobUpdateRequest & State enum
        unknown_fields = set(payload.keys()) - VALID_FIA_FIELDS
        state = payload.get("state")
        if unknown_fields or (state is not None and state not in VALID_FIA_STATES):
            self.send_response(HTTPStatus.UNPROCESSABLE_ENTITY)
            self.end_headers()
            return

        received_callbacks[self.path] = {
            "headers": dict(self.headers),
            "json": payload,
        }
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence default stdout HTTP server logging during tests."""


@pytest.fixture(scope="module", autouse=True)
def callback_server() -> Generator[None, None, None]:
    """Start a background HTTP server to receive worker callbacks during E2E tests."""
    server = HTTPServer(("0.0.0.0", CALLBACK_PORT), MockFIAAPICallbackHandler)  # noqa: S104
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield
    server.shutdown()
    server.server_close()


def wait_for_api() -> None:
    """
    Wait for the API to become responsive.

    Retries up to 5 times with a 2-second delay.
    :raises Exception: If the API is not ready after retries.
    """
    try:
        response = requests.get(f"{API_URL}/healthz")  # noqa: S113
        response.raise_for_status()
    except Exception:
        raise Exception("API not ready")  # noqa: B904


def test_workflow() -> None:
    """
    Test the full script submission, execution, and fia-api callback workflow.

    Steps:
    1. Submit a script that prints to stdout/stderr with a job_id.
    2. Poll the status endpoint until completion.
    3. Verify the final state and output content from LLSP-API.
    4. Verify the worker sent a valid PATCH callback to the mock fia-api receiver.
    """
    wait_for_api()
    received_callbacks.clear()
    job_id = 42

    # 1. Submit a script
    script = """
import sys
print('Hello from stdout')
print('Hello from stderr', file=sys.stderr)
"""
    response = requests.post(
        f"{API_URL}/execute",
        json={"script": script, "job_id": job_id},
        headers=HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    assert "task_id" in data
    task_id = data["task_id"]

    # 2. Poll for Status
    for _ in range(30):
        response = requests.get(
            f"{API_URL}/status/{task_id}",
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        state = response.json()
        if state["state"] in ["success", "error"]:
            break
        time.sleep(1)
    else:
        raise AssertionError("Task timed out")

    # 3. Validation of LLSP-API status
    assert state["state"] == "success"
    result = state["result"]
    assert result["exit_code"] == 0
    assert "Hello from stdout" in result["stdout"]
    assert "Hello from stderr" in result["stderr"]

    # 4. Validation of Worker Callback to fia-api
    callback_path = f"/job/{job_id}"
    for _ in range(10):
        if callback_path in received_callbacks:
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f"Did not receive callback at {callback_path}")

    callback = received_callbacks[callback_path]
    assert callback["headers"].get("Authorization") == f"Bearer {FIA_API_TOKEN}"
    callback_payload = callback["json"]
    assert callback_payload["state"] == "SUCCESSFUL"
    callback_outputs = json.loads(callback_payload["outputs"])
    assert callback_outputs["exit_code"] == 0
    assert "Hello from stdout" in callback_outputs["stdout"]
    assert "Hello from stderr" in callback_outputs["stderr"]


def test_unauthorized_access() -> None:
    """Verify that requests without a valid API key are rejected."""
    wait_for_api()

    # Case 1: No Authorization header
    response = requests.post(
        f"{API_URL}/execute",
        json={"script": "print('fail')", "job_id": 1},
        timeout=10,
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, f"Expected 403, got {response.status_code}"

    # Case 2: Invalid API key
    response = requests.post(
        f"{API_URL}/execute",
        json={"script": "print('fail')", "job_id": 1},
        headers={"Authorization": "Bearer invalid-token"},
        timeout=10,
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED, f"Expected 401, got {response.status_code}"
