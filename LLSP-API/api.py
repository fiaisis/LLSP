"""
LLSP-API Application Module.

This module defines the FastAPI application for the LLSP service, handling
script submission and status tracking.
"""

import logging
import os
import sys
from typing import Any, Annotated

from celery import Celery  # type: ignore
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from model import ExecIn, Task, TaskState
from utils import map_state

# Configuration
BROKER = os.getenv("CELERY_BROKER_URL", "amqp://user:pass@rabbitmq:5672/vhost")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
TASK_NAME = os.getenv("EXEC_TASK_NAME", "celery_app.exec_script")

logger = logging.getLogger(__name__)

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

security = HTTPBearer()

def verify_api_key(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> None:
    """
    Validate the API key from the request credentials.

    :param credentials: The HTTP authorization credentials from the request.
    :return: True if the API key matches the environment variable, False otherwise.
    """
    if credentials.credentials != os.environ.get("LLSP_API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.post("/execute")
def execute(payload: ExecIn, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> Task:
    """
    Submit a script for execution.

    :param payload: The script submission payload.
    :return: A `Task` object containing the task ID and initial status.
    """
    verify_api_key(credentials)
    async_result = celery.send_task(
        TASK_NAME,
        args=[payload.script],
    )
    return Task(task_id=async_result.id, state=TaskState.pending, result=None)


@app.get("/status/{task_id}")
def status(task_id: str, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> Task:
    """
    Check the status of a submitted task.

    :param task_id: The ID of the task to check.
    :return: A `Task` object with the current state and result (if ready).
    """
    verify_api_key(credentials)
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
    api_key = os.environ.get("LLSP_API_KEY", None)
    if api_key is None:
        logger.critical("The LLSP_API_KEY environment variable is not set.")
        sys.exit(1)
    return {"status": "ready"}
