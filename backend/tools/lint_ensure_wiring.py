"""
lint_ensure_wiring.py — CI lint for runtime-DDL wiring in VSKS CRM backend.

This project uses a "runtime-DDL" pattern: schema migrations are applied at
startup by async `_ensure_*` functions defined in `backend/check_schema.py`.
A function only runs if it is CALLED from either:
  1. `backend/app/__init__.py`  (the FastAPI lifespan)
  2. `main()` inside `backend/check_schema.py` itself

Adding a new `_ensure_*` function without wiring it into either place means
the migration silently never runs, causing 502 errors on fresh DBs.

This script detects that class of bug.

Usage:
    python backend/tools/lint_ensure_wiring.py

Exit codes:
    0 — all _ensure_* functions are wired (or no orphans found)
    1 — one or more orphaned _ensure_* functions detected

Implementation note on helper chains:
    A function is considered "wired" if its name appears anywhere in the
    call-name set of EITHER file (check_schema.py or app/__init__.py).
    This means calls from one _ensure_* to another also count as wired,
    even if the parent chain is not yet verified to be rooted at main()
    or __init__.py. This is a known simplification that avoids false
    positives for helper chains; it may miss orphaned sub-helpers whose
    only caller is another orphan. For practical purposes in this codebase
    this trade-off is acceptable.
"""

import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths: script lives at backend/tools/, so:
#   check_schema.py  → ../check_schema.py
#   app/__init__.py  → ../app/__init__.py
# ---------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TOOLS_DIR.parent
CHECK_SCHEMA_PATH = BACKEND_DIR / "check_schema.py"
APP_INIT_PATH = BACKEND_DIR / "app" / "__init__.py"


def _parse_file(path: Path) -> ast.Module:
    """Parse a Python source file and return its AST."""
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    return ast.parse(source, filename=str(path))


def collect_ensure_definitions(tree: ast.Module) -> list[str]:
    """
    Walk AST and collect names of every function (sync or async) whose
    name starts with '_ensure_', at any nesting depth.
    Uses ast — not regex — so definitions in strings/comments are ignored.
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_ensure_"):
                names.append(node.name)
    return names


def collect_call_names(tree: ast.Module) -> set[str]:
    """
    Walk AST and collect every name used as the callable in a Call expression.
    Handles:
      - bare calls:           _ensure_foo(conn)          → func is Name
      - attribute calls:      obj._ensure_foo(conn)      → func is Attribute
      - names in list/tuple literals that are function references (not calls)
        are NOT captured here — only actual Call nodes.

    Additionally, capture Name nodes that appear in list/tuple/set displays
    when they look like _ensure_* references (used for list-of-coros patterns
    like `fns = [_ensure_a, _ensure_b]`).
    """
    call_names: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.append(node.func.attr)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            # Capture bare name references (used when functions are stored
            # in a list/tuple then iterated — e.g., `fns = [_ensure_a, _ensure_b]`)
            if node.id.startswith("_ensure_"):
                call_names.append(node.id)
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute):
            # Capture attribute references like module._ensure_foo
            if node.attr.startswith("_ensure_"):
                call_names.append(node.attr)
            self.generic_visit(node)

    Visitor().visit(tree)
    return set(call_names)


def main() -> None:
    # 1. Parse both files
    check_schema_tree = _parse_file(CHECK_SCHEMA_PATH)
    app_init_tree = _parse_file(APP_INIT_PATH)

    # 2. Collect all _ensure_* definitions (from check_schema.py only)
    definitions = collect_ensure_definitions(check_schema_tree)
    total = len(definitions)

    if total == 0:
        print("OK: no _ensure_* functions found — nothing to check.")
        sys.exit(0)

    # 3. Collect all call/reference names from BOTH files
    call_names_check = collect_call_names(check_schema_tree)
    call_names_init = collect_call_names(app_init_tree)
    all_call_names = call_names_check | call_names_init

    # 4. Determine wired vs orphaned
    wired: list[str] = []
    orphaned: list[str] = []
    for name in sorted(definitions):
        if name in all_call_names:
            wired.append(name)
        else:
            orphaned.append(name)

    # 5. Report
    print(f"\n{'='*60}")
    print(f"  lint_ensure_wiring — VSKS CRM backend")
    print(f"  check_schema.py : {CHECK_SCHEMA_PATH}")
    print(f"  app/__init__.py : {APP_INIT_PATH}")
    print(f"{'='*60}")
    print(f"\n  Total _ensure_* definitions : {total}")
    print(f"  Wired                       : {len(wired)}")
    print(f"  ORPHANED (never called)     : {len(orphaned)}")

    if orphaned:
        print(f"\n  ORPHANED FUNCTIONS — must be called from main() or app/__init__.py lifespan:\n")
        for name in orphaned:
            print(f"    ✗  {name}")
        print(
            f"\n  ACTION REQUIRED: add each orphaned function to the call list in\n"
            f"  backend/app/__init__.py (lifespan) AND/OR backend/check_schema.py main().\n"
        )
        sys.exit(1)
    else:
        print(f"\n  OK: all {total} _ensure_* functions are wired.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
