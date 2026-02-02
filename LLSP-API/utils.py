"""Utility functions for the LLSP-API."""

from typing import Any

from celery import states  # type: ignore
from model import TaskState


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
