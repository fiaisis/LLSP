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
    script: str = Field(..., description="Python script text")
    output_uri: str | None = Field(None, description="Optional output URI or path")
    timeout: int = Field(7200, ge=1, le=21600, description="Task timeout in seconds")


class TaskState(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    error = "error"

class Task(BaseModel):
    task_id: str
    state: TaskState
    result: Any
    output_path: str | None

def map_state(celery_state: str, result_body: Any) -> TaskState:
    """Translate Celery state into the public API surface."""
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
    """Submit a script for execution."""
    async_result = celery.send_task(
        TASK_NAME,
        args=[payload.script],
        kwargs={"output_uri": payload.output_uri, "timeout": payload.timeout},
    )
    return Task(task_id=async_result.id, state=TaskState.pending, result=None, output_path=None)


@app.get("/status/{task_id}")
def status(task_id: str) -> Task:
    """Check the status of a submitted task."""
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
        output_path=output_path
    )
