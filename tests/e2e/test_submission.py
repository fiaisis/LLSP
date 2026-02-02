"""
End-to-end tests for the LLSP submission workflow.

This module tests the full lifecycle of a script submission, execution, and result retrieval.
"""

import os
import time

import requests
from tenacity import retry, stop_after_attempt, wait_fixed

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
def wait_for_api():
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


def test_workflow():
    """
    Test the full script submission and execution workflow.

    Steps:
    1. Submit a script that prints to stdout/stderr.
    2. Poll the status endpoint until completion.
    3. Verify the final state and output content.
    """
    wait_for_api()

    # 1. Submit a script
    script = """
import sys
print('Hello from stdout')
print('Hello from stderr', file=sys.stderr)
"""
    response = requests.post(f"{API_URL}/execute", json={"script": script}, timeout=10)
    response.raise_for_status()
    data = response.json()
    assert "task_id" in data
    task_id = data["task_id"]

    # 2. Poll for Status
    for _ in range(30):
        response = requests.get(f"{API_URL}/status/{task_id}", timeout=10)
        response.raise_for_status()
        state = response.json()
        if state["state"] in ["success", "error"]:
            break
        time.sleep(1)
    else:
        raise AssertionError("Task timed out")

    # 3. Validation
    assert state["state"] == "success"
    result = state["result"]
    assert result["exit_code"] == 0
    assert "Hello from stdout" in result["stdout"]
    assert "Hello from stderr" in result["stderr"]


if __name__ == "__main__":
    test_workflow()
