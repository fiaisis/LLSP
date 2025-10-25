"""Custom exception classes for execute_api."""


class ScriptExecutionError(Exception):
    """Raised when execution of the submitted script fails."""


class ScriptCompilationError(Exception):
    """Raised when compilation of the submitted script fails."""