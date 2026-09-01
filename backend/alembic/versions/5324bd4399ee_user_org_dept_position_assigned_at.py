"""user_organizations: dept_assigned_at/position_assigned_at + orphan NULL-dept cleanup

БАГ (владелец, 2026-09-01): перенёс Маркодееву (user_id=10) в отдел
«Администрация», но в карточке продолжает висеть строка «Без отдела».
Причина — в данных, не в отображении.

`user_organizations` уникальна по (user_id, org_id, COALESCE(dept_id, 0)).
`POST /api/departments/{dept_id}/members` (backend/app/routers/departments.py)
при назначении в отдел СОЗДАЁТ новую строку с dept_id=<отдел>, а прежняя
строка с dept_id IS NULL («сотрудник в организации, отдел ещё не назначен»)
остаётся жить — она и видна в карточке как «Без отдела». Заодно новая строка
получала hired_at = now() — то есть дата трудоустройства подменялась датой
назначения в отдел.

Multi-dept (один человек в нескольких отделах ОДНОЙ орг одновременно, напр.
Цыганов) — легитимный и намеренный кейс, ломать нельзя: строка с dept_id
NOT NULL никогда не удаляется этой миграцией, каждая такая строка — отдельное
реальное членство в отделе. Удаляется ТОЛЬКО строка-«заглушка» с dept_id IS
NULL, когда для той же пары (user_id, org_id) уже есть хотя бы одна строка с
реальным отделом — она больше не несёт смысла «отдел ещё не назначен».

Владелец разделяет смысл дат:
  - hired_at            — дата трудоустройства, ОБЩАЯ на пару (user_id, org_id);
  - dept_assigned_at    — дата назначения В ОТДЕЛ (новое поле, per-row);
  - position_assigned_at— дата назначения НА ДОЛЖНОСТЬ (новое поле, per-row).

ЧТО ДЕЛАЕТ МИГРАЦИЯ (идемпотентно, безопасно для повторного прогона):
  1. Добавляет колонки dept_assigned_at, position_assigned_at (DATE, nullable) —
     ADD COLUMN IF NOT EXISTS.
  2. Для строк с реальным отделом, у которых есть NULL-dept «сестра» по той же
     паре (user_id, org_id) и hired_at позже, чем у сестры — это и есть дата,
     которую раньше ошибочно писали в hired_at при назначении в отдел.
     Переносим её в dept_assigned_at (только если dept_assigned_at ещё NULL —
     guard от повторного прогона).
  3. Переносит из NULL-dept строки в строки с отделом (для той же пары)
     position/salary_amount/employment_percent — только там, где в целевой
     строке они пусты.
  4. Выравнивает hired_at внутри КАЖДОЙ пары (user_id, org_id) с 2+ строками
     (не только там, где была NULL-dept строка — общее правило "hired_at один
     на пару") к самому раннему значению в группе.
  5. Удаляет NULL-dept строку, если для той же пары есть строка(и) с реальным
     отделом. Строки с 2+ РЕАЛЬНЫМИ отделами (multi-dept) не трогает.

Все шаги печатают счётчики (print, видно в логах деплоя).

Revision ID: 5324bd4399ee
Revises: v4w5x6y7z8a9
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '5324bd4399ee'
down_revision = 'v4w5x6y7z8a9'
branch_labels = None
depends_on = None

_TAG = "[5324bd4399ee]"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_organizations" not in inspector.get_table_names():
        return

    # --- 1. Новые колонки (idempotent) ---
    op.execute(sa.text(
        "ALTER TABLE user_organizations ADD COLUMN IF NOT EXISTS dept_assigned_at DATE"
    ))
    op.execute(sa.text(
        "ALTER TABLE user_organizations ADD COLUMN IF NOT EXISTS position_assigned_at DATE"
    ))

    # --- Диагностика ДО очистки ---
    orphan_pairs_before = bind.execute(sa.text(
        """
        SELECT count(*) FROM (
            SELECT null_row.id
            FROM user_organizations null_row
            WHERE null_row.dept_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM user_organizations dept_row
                  WHERE dept_row.dept_id IS NOT NULL
                    AND dept_row.user_id = null_row.user_id
                    AND dept_row.org_id = null_row.org_id
              )
        ) t
        """
    )).scalar()
    print(f"{_TAG} строк-заглушек (dept_id IS NULL) с реальным отделом-сестрой ДО очистки = {orphan_pairs_before}")

    # --- 2. dept_assigned_at: перенос из hired_at строки-с-отделом, если она позже сестры-заглушки ---
    result = bind.execute(sa.text(
        """
        UPDATE user_organizations dept_row
        SET dept_assigned_at = dept_row.hired_at::date
        FROM user_organizations null_row
        WHERE null_row.user_id = dept_row.user_id
          AND null_row.org_id = dept_row.org_id
          AND null_row.dept_id IS NULL
          AND dept_row.dept_id IS NOT NULL
          AND dept_row.dept_assigned_at IS NULL
          AND dept_row.hired_at IS NOT NULL
          AND null_row.hired_at IS NOT NULL
          AND dept_row.hired_at > null_row.hired_at
        """
    ))
    print(f"{_TAG} dept_assigned_at проставлена строкам = {result.rowcount}")

    # --- 3. Перенос position/salary_amount/employment_percent из заглушки в строку с отделом, только где пусто ---
    result = bind.execute(sa.text(
        """
        UPDATE user_organizations dept_row
        SET position = COALESCE(dept_row.position, null_row.position),
            salary_amount = COALESCE(dept_row.salary_amount, null_row.salary_amount),
            employment_percent = COALESCE(dept_row.employment_percent, null_row.employment_percent)
        FROM user_organizations null_row
        WHERE null_row.user_id = dept_row.user_id
          AND null_row.org_id = dept_row.org_id
          AND null_row.dept_id IS NULL
          AND dept_row.dept_id IS NOT NULL
          AND (
              dept_row.position IS NULL
              OR dept_row.salary_amount IS NULL
              OR dept_row.employment_percent IS NULL
          )
        """
    ))
    print(f"{_TAG} position/salary/percent подтянуты в строк = {result.rowcount}")

    # --- 4. Выравнивание hired_at внутри пары (user_id, org_id) к самому раннему значению ---
    result = bind.execute(sa.text(
        """
        WITH earliest AS (
            SELECT user_id, org_id, MIN(hired_at) AS min_hired
            FROM user_organizations
            GROUP BY user_id, org_id
            HAVING COUNT(*) > 1
        )
        UPDATE user_organizations uo
        SET hired_at = earliest.min_hired
        FROM earliest
        WHERE uo.user_id = earliest.user_id
          AND uo.org_id = earliest.org_id
          AND uo.hired_at IS DISTINCT FROM earliest.min_hired
        """
    ))
    print(f"{_TAG} hired_at выровнен (к самому раннему в паре) в строк = {result.rowcount}")

    # --- 5. Удаление NULL-dept строки-заглушки, когда для пары уже есть реальный отдел ---
    result = bind.execute(sa.text(
        """
        DELETE FROM user_organizations null_row
        USING user_organizations dept_row
        WHERE null_row.dept_id IS NULL
          AND dept_row.dept_id IS NOT NULL
          AND dept_row.user_id = null_row.user_id
          AND dept_row.org_id = null_row.org_id
        """
    ))
    print(f"{_TAG} удалено строк-заглушек (dept_id IS NULL) = {result.rowcount}")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_organizations" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_organizations")}
    if "position_assigned_at" in cols:
        op.drop_column("user_organizations", "position_assigned_at")
    if "dept_assigned_at" in cols:
        op.drop_column("user_organizations", "dept_assigned_at")
    # Удалённые в шаге 5 upgrade() строки-заглушки НЕ восстанавливаются —
    # это разрушающая, но осознанная чистка данных; откат схемы не откатывает данные.
