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
from urllib.parse import quote

from celery import Celery  # type: ignore

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


@app.task(max_retries=0)  # type: ignore # the source decorator is untyped
def exec_script(script: str) -> dict[str, Any]:
    """
    Execute a Python script in a subprocess.

    :param script: The Python script code to execute.
    :return: A dictionary containing 'exit_code', 'stdout', and 'stderr'.
    """
    try:
        with TemporaryDirectory() as tmp:
            print("Here is where we would write to the database via api")  # noqa: T201 # Will be removed in fia integration
            proc = subprocess.run(  # noqa: PLW1510, S603
                [sys.executable, "-c", script], cwd=tmp, capture_output=True, text=True
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
    finally:
        print("Here is where we would write to the databse via api")  # noqa: T201 # Will be removed in fia integration
