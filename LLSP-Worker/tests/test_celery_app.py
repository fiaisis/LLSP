"""Tests for the celery_app module and custom ReportingTask."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests  # type: ignore[import-untyped]
from celery_app import ReportingTask, exec_script


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture to mock environment variables for API reporting."""
    monkeypatch.setenv("API_BASE_URL", "http://fake-api.local")
    monkeypatch.setenv("API_AUTH_TOKEN", "fake-token")


def test_exec_script() -> None:
    """Test the exec_script task executes a script and returns correct output."""
    script = "print('Hello World!')"
    result = exec_script(script, job_id=1)

    assert result["exit_code"] == 0
    assert result["stdout"] == "Hello World!\n"
    assert result["stderr"] == ""


def test_reporting_task_success(mock_env: None) -> None:
    """Test reporting task sends correct payload on success."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        # Configure the mock response
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        retval = {"exit_code": 0, "stdout": "ok", "stderr": ""}
        task.after_return(
            status="SUCCESS",
            retval=retval,
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo=None,
        )

        mock_patch.assert_called_once_with(
            "http://fake-api.local/job/42",
            json={
                "state": "SUCCESSFUL",
                "outputs": json.dumps(retval),
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )
        mock_response.raise_for_status.assert_called_once()


def test_reporting_task_nonzero_exit_code(mock_env: None) -> None:
    """Test reporting task sends UNSUCCESSFUL state when script exits with non-zero code."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        retval = {"exit_code": 1, "stdout": "", "stderr": "NameError: name 'x' is not defined\n"}
        task.after_return(
            status="SUCCESS",
            retval=retval,
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo=None,
        )

        mock_patch.assert_called_once_with(
            "http://fake-api.local/job/42",
            json={
                "state": "UNSUCCESSFUL",
                "outputs": json.dumps(retval),
                "status_message": "Script exited with code 1",
                "stacktrace": "NameError: name 'x' is not defined\n",
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )
        mock_response.raise_for_status.assert_called_once()


def test_reporting_task_failure(mock_env: None) -> None:
    """Test reporting task sends correct payload on failure with einfo."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        error = RuntimeError("Something broke")
        task.after_return(
            status="FAILURE",
            retval=error,
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo="Traceback here...",
        )

        mock_patch.assert_called_once_with(
            "http://fake-api.local/job/42",
            json={
                "state": "ERROR",
                "status_message": str(error),
                "stacktrace": "Traceback here...",
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )


def test_reporting_task_missing_job_id(caplog: pytest.LogCaptureFixture) -> None:
    """Test reporting is skipped if job_id is missing."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        task.after_return(
            status="SUCCESS",
            retval={},
            task_id="task-123",
            args=(),
            kwargs={},  # Missing job_id
            einfo=None,
        )

        mock_patch.assert_not_called()
        assert "No job_id provided" in caplog.text


def test_reporting_task_missing_api_url(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reporting is skipped if API_BASE_URL is missing."""
    monkeypatch.delenv("API_BASE_URL", raising=False)
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        task.after_return(
            status="SUCCESS",
            retval={},
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo=None,
        )

        mock_patch.assert_not_called()
        assert "API_BASE_URL not configured" in caplog.text


def test_reporting_task_request_error(mock_env: None, caplog: pytest.LogCaptureFixture) -> None:
    """Test worker does not crash if the API is unreachable."""
    task = ReportingTask()

    with patch("requests.patch", side_effect=requests.exceptions.RequestException("Connection failed")):
        task.after_return(
            status="SUCCESS",
            retval={},
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo=None,
        )

        assert "Failed to report task outcome to API" in caplog.text
