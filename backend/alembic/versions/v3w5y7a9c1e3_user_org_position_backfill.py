"""user_organizations.position backfill из users.position (Правило №6, волна D2)

Revision ID: v3w5y7a9c1e3
Revises: t2v4x6z8b0d2
Create Date: 2026-09-07 00:00:00.000000

Контекст: должность сотрудника хранилась дважды — `users.position` (легаси,
общий на человека) и `user_organizations.position` (по конкретной
организации). Были два писателя с противоречащими комментариями «источник
истины» (routers/users.py копировал users.position → UO; routers/departments.py
и services/dept_role_sync.py писали UO напрямую) и два читателя с разным
fallback (services/documents/contexts.py предпочитал UO, routers/hierarchy.py —
карту UO, иначе users.position). Решение волны: единственный источник —
`user_organizations.position` (по организации); `users.position` — только
fallback для человека без единого членства. Резолвер/писатель теперь один —
`app.services.user_position`.

Что делает миграция (идемпотентно, каждый шаг — отдельный op.execute,
т.к. asyncpg не умеет несколько команд в одном prepared statement):

1. Для user_organizations с пустым `position` и непустым `users.position` у
   того же пользователя — ЗАПОЛНИТЬ пробел значением из users.position
   (идемпотентно: при повторном прогоне position уже не пуст, условие не
   сработает повторно), с RAISE NOTICE построчно:
   'user_org_position_backfill uo_id=<id> user_id=<id> full_name=<фио> org_id=<id> value=<значение>'
2. Для строк, где ОБА поля непустые и РАЗЛИЧАЮТСЯ (реальный конфликт — шаг 1
   сюда не полез) — ничего не перезаписывать, только отчёт:
   'user_org_position_diff uo_id=<id> user_id=<id> full_name=<фио> org_id=<id> uo_position=<знач> user_position=<знач>'
   — видно в выводе `alembic upgrade` / логах контейнера при деплое.

users.position НЕ удаляется и не очищается — остаётся deprecated legacy-полем
(fallback для пользователей без единого членства), см. app/services/user_position.py.

downgrade — no-op: копирование пустых полей необратимо без снапшота (тот же
паттерн, что и в t2v4x6z8b0d2_org_contractor_requisites_backfill.py).
"""
from alembic import op

revision = 'v3w5y7a9c1e3'
down_revision = 't2v4x6z8b0d2'
branch_labels = None
depends_on = None


_BACKFILL_EMPTY_UO_POSITION = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT uo.id AS uo_id, uo.user_id, uo.org_id, u.full_name, u.username, u.position AS user_position
    FROM user_organizations uo
    JOIN users u ON u.id = uo.user_id
    WHERE btrim(COALESCE(uo.position, '')) = ''
      AND btrim(COALESCE(u.position, '')) <> ''
  LOOP
    UPDATE user_organizations SET position = r.user_position WHERE id = r.uo_id;
    RAISE NOTICE 'user_org_position_backfill uo_id=% user_id=% full_name=% org_id=% value=%',
      r.uo_id, r.user_id, COALESCE(r.full_name, r.username), r.org_id, r.user_position;
  END LOOP;
END $$;
"""

_REPORT_DIVERGENCES = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT uo.id AS uo_id, uo.user_id, uo.org_id, uo.position AS uo_position,
           u.full_name, u.username, u.position AS user_position
    FROM user_organizations uo
    JOIN users u ON u.id = uo.user_id
    WHERE btrim(COALESCE(uo.position, '')) <> ''
      AND btrim(COALESCE(u.position, '')) <> ''
      AND uo.position IS DISTINCT FROM u.position
  LOOP
    RAISE NOTICE 'user_org_position_diff uo_id=% user_id=% full_name=% org_id=% uo_position=% user_position=%',
      r.uo_id, r.user_id, COALESCE(r.full_name, r.username), r.org_id, r.uo_position, r.user_position;
  END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_BACKFILL_EMPTY_UO_POSITION)
    op.execute(_REPORT_DIVERGENCES)


def downgrade() -> None:
    pass
