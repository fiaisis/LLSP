"""Main module for the execute API."""

import logging
import sys

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# Configure basic logging similar to the FIA‑API project【331024848537717†L269-L335】.
stdout_handler = logging.StreamHandler(stream=sys.stdout)
logging.basicConfig(
    handlers=[stdout_handler],
    format="[%(asctime)s]-%(name)s-%(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(title="Execute API")

# Configure CORS – allow all origins for demonstration purposes
ALLOWED_ORIGINS = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the execute router
app.include_router(execute_router)


@app.exception_handler(ScriptExecutionError)
async def script_execution_error_handler(_: Request, exc: ScriptExecutionError) -> JSONResponse:
    """Return a 400 response with the error message when a script fails."""
    return JSONResponse(status_code=400, content={"message": str(exc)})