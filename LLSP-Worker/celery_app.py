"""
LLSP-Worker App Module.

This module defines the Celery worker application and tasks for executing Python scripts.
"""

import logging
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any
import json
from urllib.parse import quote

import requests
from celery import Celery, Task  # type: ignore

logger = logging.getLogger(__name__)

BROKER_HOST = os.getenv("CELERY_BROKER_HOST")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "foo")
RABBITMQ_PASS = os.environ.get("RABBITMQ_PASS", "bar")
BROKER = f"amqp://{RABBITMQ_USER}:{quote(RABBITMQ_PASS)}@{BROKER_HOST}/llspvhost"
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
app = Celery("celery_app", broker=BROKER, backend=BACKEND)
app.conf.update(
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=True,
)


class ReportingTask(Task):  # type: ignore
    """
    Custom Celery Task base class for reporting task outcomes.

    This class overrides the `after_return` method to serve as the single source
    of truth for API updates. It sends a PATCH request to the configured API endpoint
    with the task's status, result, or traceback.
    """

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Handler called after the task returns.

        :param status: Current task state.
        :param retval: Task return value/exception.
        :param task_id: Unique id of the task.
        :param args: Original arguments for the task.
        :param kwargs: Original keyword arguments for the task.
        :param einfo: Exception info, if any.
        """
        job_id = kwargs.get("job_id")
        if job_id is None:
            logger.warning("No job_id provided in task kwargs; skipping reporting.")
            return

        api_base_url = os.getenv("API_BASE_URL")
        if not api_base_url:
            logger.warning("API_BASE_URL not configured; skipping reporting.")
            return

        api_auth_token = os.getenv("API_AUTH_TOKEN", "")

        url = f"{api_base_url.rstrip('/')}/job/{job_id}"
        headers = {}
        if api_auth_token:
            headers["Authorization"] = f"Bearer {api_auth_token}"

        payload: dict[str, Any] = {
            "state": status,
        }
        if status == "SUCCESS":
            payload["outputs"] = json.dumps(retval) if retval else None
        elif status == "FAILURE":
            payload["status_message"] = str(retval) if retval else None
            payload["stacktrace"] = str(einfo) if einfo else None

        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to report task outcome to API: {exc}")



@app.task(base=ReportingTask, max_retries=0)  # type: ignore # the source decorator is untyped
def exec_script(script: str, *, job_id: int) -> dict[str, Any]:
    """
    Execute a Python script in a subprocess.

    :param script: The Python script code to execute.
    :param job_id: The unique identifier of the job, used for reporting.
    :return: A dictionary containing 'exit_code', 'stdout', and 'stderr'.
    """
    with TemporaryDirectory() as tmp:
        proc = subprocess.run(  # noqa: PLW1510, S603
            [sys.executable, "-c", script], cwd=tmp, capture_output=True, text=True
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
