"""Test utility functions for the LLSP-API."""

import sys
from pathlib import Path

from celery import states

# Add LLSP-API to python path since it's not a standard package
sys.path.append(str(Path(__file__).resolve().parent.parent / "LLSP-API"))

from model import TaskState
from utils import map_state


def test_map_state_pending():
    """Test that PENDING state maps to pending."""
    assert map_state(states.PENDING, None) == TaskState.pending


def test_map_state_running():
    """Test that STARTED, RETRY, and RECEIVED states map to running."""
    for state in [states.STARTED, states.RETRY, states.RECEIVED]:
        assert map_state(state, None) == TaskState.running


def test_map_state_success_zero_exit():
    """Test that SUCCESS state with exit_code 0 maps to success."""
    assert map_state(states.SUCCESS, {"exit_code": 0}) == TaskState.success


def test_map_state_success_default_exit():
    """Test that SUCCESS state without exit_code maps to success (defaults to 0)."""
    # If exit_code is missing, defaults to 0
    assert map_state(states.SUCCESS, {}) == TaskState.success


def test_map_state_success_nonzero_exit():
    """Test that SUCCESS state with non-zero exit_code maps to error."""
    assert map_state(states.SUCCESS, {"exit_code": 1}) == TaskState.error
    assert map_state(states.SUCCESS, {"exit_code": -1}) == TaskState.error


def test_map_state_failure():
    """Test that FAILURE state maps to error."""
    assert map_state(states.FAILURE, None) == TaskState.error


def test_map_state_unknown():
    """Test that unknown states map to error."""
    assert map_state("UNKNOWN_STATE", None) == TaskState.error
