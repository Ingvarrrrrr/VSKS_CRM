#!/usr/bin/env python3
"""CI guard: ровно одна alembic head в backend/alembic/versions/.

Проблема (см. Lessons/CLAUDE.md — "Alembic: проверять multiple heads перед
миграцией"): новый файл миграции со `down_revision`, скопированным со
старого HEAD вместо реального (или два параллельных PR, каждый ссылается на
один и тот же down_revision), создаёт ВТОРУЮ головку графа ревизий.
`alembic upgrade head` в этом случае падает уже НА ДЕПЛОЕ (502 на проде),
потому что "head" неоднозначен. Этот скрипт ловит расхождение статически —
парсит только Python AST файлов миграций, без подключения к БД и без
импорта alembic/sqlalchemy, поэтому пригоден для CI-джобы без Postgres.

Правила разбора:
- revision/down_revision читаются как значения простых module-level
  присваиваний (`revision = "..."`), через `ast.parse` — не regex, чтобы не
  зацепить упоминания слова "down_revision" в докстринге/комментарии.
- down_revision может быть None (первая ревизия), строкой (обычная цепочка)
  или tuple из строк (merge-миграция, alembic допускает несколько
  родителей у одной ревизии).
- "head" = ревизия, на которую никто не ссылается как на своего родителя.
  Голов должно быть ровно 1. 0 голов (цикл/пустой каталог) и >1 (развилка)
  — обе считаются ошибкой.

Exit code: 0 — ровно одна голова; 1 — ошибка (список причин в stdout).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _literal(node: ast.expr | None):
    """Best-effort literal value of a revision/down_revision RHS node."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def parse_revision_file(path: Path) -> tuple[str | None, object]:
    """Return (revision, down_revision) for one alembic version file.

    down_revision is None, a str, or a tuple[str, ...] (merge migration).
    Missing/unparsable assignments come back as None so the caller can
    report a clear per-file error instead of silently skipping the file.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = None
    down_revision = None
    down_revision_seen = False
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "revision":
                revision = _literal(node.value)
            elif target.id == "down_revision":
                down_revision = _literal(node.value)
                down_revision_seen = True
    if not down_revision_seen:
        # down_revision = None is valid (root revision) — сигнал ошибки
        # только "переменной не было вовсе", различаем через флаг выше.
        return revision, "__missing__"
    return revision, down_revision


def main() -> int:
    if not VERSIONS_DIR.is_dir():
        print(f"ERROR: versions dir not found: {VERSIONS_DIR}")
        return 1

    files = sorted(VERSIONS_DIR.glob("*.py"))
    files = [f for f in files if f.name != "__init__.py"]
    if not files:
        print(f"ERROR: no migration files found in {VERSIONS_DIR}")
        return 1

    revisions: dict[str, Path] = {}
    parents: dict[str, object] = {}
    errors: list[str] = []

    for f in files:
        try:
            revision, down_revision = parse_revision_file(f)
        except SyntaxError as exc:
            errors.append(f"{f.name}: could not parse file ({exc})")
            continue

        if revision is None:
            errors.append(f"{f.name}: missing/unparsable `revision =` assignment")
            continue
        if down_revision == "__missing__":
            errors.append(f"{f.name}: missing `down_revision =` assignment")
            continue

        if revision in revisions:
            errors.append(
                f"duplicate revision id '{revision}': {revisions[revision].name} and {f.name}"
            )
        revisions[revision] = f
        parents[revision] = down_revision

    # Referenced parents (a revision id counts as "referenced" if some other
    # revision names it in down_revision — including inside a merge tuple).
    referenced: set[str] = set()
    for down_revision in parents.values():
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            referenced.update(down_revision)
        else:
            referenced.add(down_revision)

    # Dangling parent references (down_revision points at a revision id that
    # doesn't exist in versions/) are a real graph break — report them too.
    known = set(revisions)
    for revision, down_revision in parents.items():
        parents_list = down_revision if isinstance(down_revision, tuple) else [down_revision]
        for p in parents_list:
            if p is not None and p not in known:
                errors.append(
                    f"revision '{revision}' ({revisions[revision].name}) "
                    f"references unknown down_revision '{p}'"
                )

    heads = sorted(r for r in revisions if r not in referenced)

    if errors:
        print("Alembic migration graph errors:")
        for e in errors:
            print(f"  - {e}")

    if len(heads) != 1:
        print(f"ERROR: expected exactly 1 alembic head, found {len(heads)}:")
        for h in heads:
            print(f"  - {h} ({revisions[h].name})")
        return 1

    if errors:
        return 1

    print(f"OK: single alembic head '{heads[0]}' ({revisions[heads[0]].name}), {len(files)} revisions checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
