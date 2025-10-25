import os

from celery import Celery
from fastapi import FastAPI
from pydantic import BaseModel

BROKER = os.getenv("CELERY_BROKER_URL")

celery = Celery(broker=BROKER)
app = FastAPI(title="Long Lived Script Processor API")


class ScriptRequest(BaseModel):
    """Request body for `/execute` endpoint."""

    script: str


class ExecuteResponse(BaseModel):
    """Response body for `/execute` endpoint."""

    task_id: str


@app.post("/execute")
async def execute_script(request: ScriptRequest):
    """Execute the supplied Python script and return the task ID."""
    task = celery.send_task("mytasks.tasks.exec_script", args=[request.script])
    return ExecuteResponse(task_id=task.id)
