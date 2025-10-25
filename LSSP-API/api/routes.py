"""Endpoint for executing user‑submitted Python code."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

import contextlib
import io
import textwrap

from app.exceptions import ScriptExecutionError

execute_router = APIRouter(tags=["execute"])


class ExecuteRequest(BaseModel):
    """Request body for `/execute` endpoint."""

    script: str = Field(..., description="A Python script to execute.")


@execute_router.post("/execute")
async def execute_script(request: ExecuteRequest) -> dict[str, str]:
    """Execute the supplied Python script and return the captured output.

    The code is executed in an isolated namespace. All output printed to standard
    output is captured and returned as a string. Exceptions are propagated as
    ScriptExecutionError.
    """

    script = textwrap.dedent(request.script)
    local_vars: dict[str, object] = {}
    stdout_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buffer):
            # Using exec is inherently unsafe; this demonstration does not sandbox user code.
            exec(script, {}, local_vars)
    except Exception as exc:  # noqa: BLE001
        raise ScriptExecutionError(f"Error executing script: {exc}") from exc
    output = stdout_buffer.getvalue()
    return {"output": output}