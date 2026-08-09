"""Validation for untrusted worker drafts before the NOOA sandbox sees them.

This policy is defence in depth only. Docker remains the execution boundary.
"""

import ast


class CodePolicyError(ValueError):
    """A draft violates the narrow Phase 1 code policy."""


_FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.With, ast.Try, ast.ClassDef)
_FORBIDDEN_NAMES = {
    "__builtins__",
    "compile",
    "eval",
    "exec",
    "globals",
    "locals",
    "open",
    "__import__",
}
_FORBIDDEN_ATTRIBUTES = {
    "system",
    "popen",
    "run",
    "remove",
    "unlink",
    "write_text",
    "write_bytes",
}


def validate_code_draft(code: str) -> None:
    """Require syntactically valid, small Python without I/O or imports."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise CodePolicyError("code draft is not valid Python") from exc
    if len(tree.body) > 30:
        raise CodePolicyError("code draft exceeds the statement limit")
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise CodePolicyError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise CodePolicyError(f"disallowed name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRIBUTES:
            raise CodePolicyError(f"disallowed attribute: {node.attr}")
