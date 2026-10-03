"""AST statement count of a Python file; docstrings and comments don't move it."""

from __future__ import annotations

import ast
import sys


def statement_count(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        # bare string Expr = docstring
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        count += 1
    return count


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "gurps_bot/mechanics/magic.py"
    print(statement_count(target))
