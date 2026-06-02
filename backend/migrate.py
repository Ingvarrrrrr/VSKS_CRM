#!/usr/bin/env python3
"""Safe Alembic bootstrap for container startup.

Runs before the app. Decides, based on DB state, whether to *adopt* the
baseline (stamp) or *apply* pending migrations (upgrade):

  - no alembic_version table, but schema already exists  → existing runtime-DDL
    database (local/prod built the old way): `alembic stamp head` to adopt the
    baseline without re-running it, then `upgrade head` (no-op until new
    migrations land).
  - no alembic_version table, no schema                  → truly fresh DB:
    `upgrade head` runs the baseline, which builds the full schema.
  - alembic_version present                              → `upgrade head`
    applies any pending migrations.

This makes prod adoption automatic on the next deploy (no manual SSH stamp) and
keeps future schema changes flowing through normal migrations.
"""
import asyncio
import subprocess
import sys

from sqlalchemy import text

from app.database import engine


async def _probe() -> tuple[bool, bool]:
    async with engine.connect() as conn:
        has_alembic = (
            await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
        ).scalar() is not None
        has_schema = (
            await conn.execute(text("SELECT to_regclass('public.organizations')"))
        ).scalar() is not None
    await engine.dispose()
    return has_alembic, has_schema


def _alembic(*args: str) -> None:
    print(f"[migrate] alembic {' '.join(args)}", flush=True)
    result = subprocess.run(["alembic", *args], cwd="/app")
    if result.returncode != 0:
        print(f"[migrate] alembic {' '.join(args)} FAILED ({result.returncode})", flush=True)
        sys.exit(result.returncode)


def main() -> None:
    has_alembic, has_schema = asyncio.run(_probe())
    if not has_alembic and has_schema:
        print("[migrate] existing runtime-DDL database detected -> adopting baseline", flush=True)
        _alembic("stamp", "head")
    _alembic("upgrade", "head")
    print("[migrate] done", flush=True)


if __name__ == "__main__":
    main()
