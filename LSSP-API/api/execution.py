from types import CodeType

from app.exceptions import ScriptExecutionError, ScriptCompilationError


def compile_script(script: str) -> CodeType:
    try:
        return compile(script, "<string>", "exec")
    except Exception as exc:
        raise ScriptCompilationError(f"Error compiling script: {exc}") from exc

