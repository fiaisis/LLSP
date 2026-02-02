"""
LLSP-API Application Module.

This module defines the FastAPI application for the LLSP service, handling
script submission and status tracking.
"""

import logging
import os
from typing import Any

from celery import Celery  # type: ignore
from fastapi import FastAPI
from model import ExecIn, Task, TaskState
from utils import map_state

# Configuration
BROKER = os.getenv("CELERY_BROKER_URL", "amqp://user:pass@rabbitmq:5672/vhost")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
TASK_NAME = os.getenv("EXEC_TASK_NAME", "celery_app.exec_script")


class EndpointFilter(logging.Filter):
    """Filter out log messages containing /healthz or /ready."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out log messages containing /healthz or /ready."""
        return record.getMessage().find("/healthz") == -1 and record.getMessage().find("/ready") == -1

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# Celery Client
celery = Celery(broker=BROKER, backend=BACKEND)
celery.conf.task_track_started = True

app = FastAPI(title="Exec API")


@app.post("/execute")
def execute(payload: ExecIn) -> Task:
    """
    Submit a script for execution.

    :param payload: The script submission payload.
    :return: A `Task` object containing the task ID and initial status.
    """
    async_result = celery.send_task(
        TASK_NAME,
        args=[payload.script],
    )
    return Task(task_id=async_result.id, state=TaskState.pending, result=None)


@app.get("/status/{task_id}")
def status(task_id: str) -> Task:
    """
    Check the status of a submitted task.

    :param task_id: The ID of the task to check.
    :return: A `Task` object with the current state and result (if ready).
    """
    res = celery.AsyncResult(task_id)
    body: Any = None
    try:
        # If ready, we can get the result (which might be the dict returned by worker)
        # Note: propagate=False prevents raising an exception if the task failed.
        if res.ready():
            body = res.get(propagate=False)
    except Exception as exc:
        body = {"error": str(exc)}

    state = map_state(res.state, body)

    return Task(
        task_id=task_id,
        state=state,
        result=body,
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """
    Liveness probe endpoint.

    :return: A dict indicating the service is alive.
    """
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """
    Readiness probe endpoint.

    :return: A dict indicating the service is ready.
    """
    return {"status": "ready"}
