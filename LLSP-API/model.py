"""Models for the LLSP-API."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
