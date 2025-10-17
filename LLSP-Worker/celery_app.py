import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

from celery import Celery

BROKER = os.getenv("CELERY_BROKER_URL")
app = Celery("celery_app", broker=BROKER)
app.conf.update(
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=True,
)


@app.task(max_retries=0)
def exec_script(script: str) -> dict[str, Any]:
    try:
        with TemporaryDirectory() as tmp:
            print("Here is where we would write to the database via api")
            proc = subprocess.run(
                [sys.executable, "-c", script], cwd=tmp, capture_output=True, text=True
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
    finally:
        print("Here is where we would write to the databse via api")
