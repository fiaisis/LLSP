from types import CodeType

import pytest

from exceptions import ScriptCompilationError
from execution import compile_script


def test_compile_good_script_returns_code():
    assert isinstance(compile_script("print('hello world')"), CodeType)
    assert isinstance(compile_script("print('hello world')\n1 + 1"), CodeType)

def test_compile_bad_script_raises_exception():
    with pytest.raises(ScriptCompilationError):
        compile_script(" print('hello world")