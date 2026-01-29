"""
LLSP-API Application Module.

This module defines the FastAPI application for the LLSP service, handling
script submission and status tracking.
"""
import os
from enum import Enum
from typing import Any

from celery import Celery, states
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Configuration
BROKER = os.getenv("CELERY_BROKER_URL", "amqp://user:pass@rabbitmq:5672/vhost")
# BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")
TASK_NAME = os.getenv("EXEC_TASK_NAME", "celery_app.exec_script")

# Celery Client
celery = Celery(broker=BROKER)
celery.conf.task_track_started = True

app = FastAPI(title="Exec API")


class ExecIn(BaseModel):
    """
    Input model for script execution.

    :param script: The Python script to be executed.
    """

    script: str = Field(..., description="Python script text")


class TaskState(str, Enum):
    """
    Enumeration of possible task states.

    :cvar pending: Task is waiting to be processed.
    :cvar running: Task is currently executing.
    :cvar success: Task completed successfully (exit code 0).
    :cvar error: Task failed or finished with non-zero exit code.
    """

    pending = "pending"
    running = "running"
    success = "success"
    error = "error"

class Task(BaseModel):
    """
    Model representing a task's status and result.

    :param task_id: Unique identifier for the task.
    :param state: Current state of the task.
    :param result: Result payload (output or error details).
    """

    task_id: str
    state: TaskState
    result: Any


def map_state(celery_state: str, result_body: Any) -> TaskState:
    """
    Translate Celery state into the public API surface.

    :param celery_state: The raw state string from Celery.
    :param result_body: The result body (if available) to check for exit codes.
    :return: The mapped `TaskState` enum.
    """
    if celery_state == states.PENDING:
        return TaskState.pending
    if celery_state in {states.STARTED, states.RETRY, states.RECEIVED}:
        return TaskState.running
    if celery_state == states.SUCCESS:
        # Treat non-zero exit codes as an error even though Celery succeeded.
        if isinstance(result_body, dict) and result_body.get("exit_code", 0) != 0:
            return TaskState.error
        return TaskState.success
    return TaskState.error


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
    output_path: str | None = None
    try:
        # If ready, we can get the result (which might be the dict returned by worker)
        # Note: propagate=False prevents raising an exception if the task failed.
        if res.ready():
            body = res.get(propagate=False)
            if isinstance(body, dict):
                output_path = body.get("output_path")
    except Exception as exc:
        body = {"error": str(exc)}

    state = map_state(res.state, body)
    
    return Task(
        task_id=task_id,
        state=state,
        result=body,
    )


@app.get("/healthz")
def healthz():
    """
    Liveness probe endpoint.

    :return: A dict indicating the service is alive.
    """
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """
    Readiness probe endpoint.

    :return: A dict indicating the service is ready.
    """
    return {"status": "ready"}
