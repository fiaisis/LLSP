"""Tests for the celery_app module and custom ReportingTask."""

import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

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


def test_exec_script_non_utf8_output() -> None:
    """Test exec_script safely replaces invalid UTF-8 bytes without raising UnicodeDecodeError."""
    script = "import sys; sys.stdout.buffer.write(b'valid\\xff\\xfeinvalid'); sys.stderr.buffer.write(b'err\\x80')"
    result = exec_script(script, job_id=1)

    assert result["exit_code"] == 0
    assert "valid" in result["stdout"]
    assert "\ufffd" in result["stdout"]
    assert "\ufffd" in result["stderr"]
    # Verify the resulting dictionary is valid JSON
    serialized = json.dumps(result)
    assert json.loads(serialized) == result


def test_reporting_task_non_json_serializable_retval(mock_env: None) -> None:
    """Test reporting task serializes non-standard objects via default=str fallback."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        retval = {"exit_code": 0, "path": Path("/outputs/output.nxs"), "tags": {"a"}}
        task.after_return(
            status="SUCCESS",
            retval=retval,
            task_id="task-123",
            args=(),
            kwargs={"job_id": 42},
            einfo=None,
        )

        mock_patch.assert_called_once()
        sent_payload = mock_patch.call_args.kwargs["json"]
        assert sent_payload["state"] == "SUCCESSFUL"
        parsed_outputs = json.loads(sent_payload["outputs"])
        assert parsed_outputs["path"] == "/outputs/output.nxs"
        assert parsed_outputs["tags"] == "{'a'}"


def test_reporting_task_success(mock_env: None) -> None:
    """Test reporting task sends correct payload on success, including start and end timestamps."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        # Configure the mock response
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        retval = {"exit_code": 0, "stdout": "ok", "stderr": ""}
        task.before_start(task_id="task-123", args=(), kwargs={"job_id": 42})
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
                "start": ANY,
                "end": ANY,
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )
        sent_payload = mock_patch.call_args.kwargs["json"]
        assert isinstance(sent_payload["start"], str)
        assert isinstance(sent_payload["end"], str)
        assert sent_payload["start"] <= sent_payload["end"]
        mock_response.raise_for_status.assert_called_once()


def test_reporting_task_nonzero_exit_code(mock_env: None) -> None:
    """Test reporting task sends UNSUCCESSFUL state when script exits with non-zero code."""
    task = ReportingTask()

    with patch("requests.patch") as mock_patch:
        mock_response = MagicMock()
        mock_patch.return_value = mock_response

        retval = {"exit_code": 1, "stdout": "", "stderr": "NameError: name 'x' is not defined\n"}
        task.before_start(task_id="task-123", args=(), kwargs={"job_id": 42})
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
                "start": ANY,
                "end": ANY,
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )
        sent_payload = mock_patch.call_args.kwargs["json"]
        assert isinstance(sent_payload["start"], str)
        assert isinstance(sent_payload["end"], str)
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
                "start": ANY,
                "end": ANY,
            },
            headers={"Authorization": "Bearer fake-token"},
            timeout=10.0,
        )
        sent_payload = mock_patch.call_args.kwargs["json"]
        assert isinstance(sent_payload["start"], str)
        assert isinstance(sent_payload["end"], str)


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
