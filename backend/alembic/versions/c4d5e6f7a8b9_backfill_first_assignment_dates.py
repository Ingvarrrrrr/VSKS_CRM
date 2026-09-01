"""user_organizations: бэкфилл первой даты назначения = дате приёма (hired_at)

Владелец (2026-09-01), дословно:
  «Первая дата назначения на должность должна равняться дате принятия на
  работу. А далее уже можно менять. По умолчанию пусть меняется при
  перетягивании человека из отдела в отдел дата назначения, чтобы удобно
  было изменения вносить, а не перебивать каждый раз руками. И
  соответственно можно корректировать руками.»

Поля dept_assigned_at/position_assigned_at появились в 5324bd4399ee и с тех
пор проставляются кодом (см. app/services/org_assignment_dates.py) для
НОВЫХ строк. Но для строк, назначенных ДО появления полей (должность/отдел
уже были, а дата назначения осталась NULL) нужен разовый бэкфилл: по
правилу «первая дата назначения = дате приёма» подставляем hired_at.

ЧТО ДЕЛАЕТ (идемпотентно — трогает только NULL, безопасно для повторного
прогона):
  1. position_assigned_at = hired_at::date там, где position IS NOT NULL
     и position_assigned_at IS NULL.
  2. dept_assigned_at = hired_at::date там, где dept_id IS NOT NULL
     и dept_assigned_at IS NULL.
  Если у строки нет hired_at (не должно происходить — колонка NOT NULL по
  server_default, но на всякий случай) — ставим текущую дату (CURRENT_DATE),
  чтобы не оставлять NULL там, где поле фактически заполнено.

Счётчики печатаются (видно в логах деплоя). downgrade() — no-op: откат
бэкфилла данных не имеет смысла (поля создавались в 5324bd4399ee, их удаление
делает downgrade той миграции).

Revision ID: c4d5e6f7a8b9
Revises: 2b00d0245ba5
Create Date: 2026-09-01 00:00:00.000000

Примечание (2026-09-01, ребейз #1): изначально планировался поверх af3caa6082ed
(на тот момент — единственная закоммиченная голова), но пока эта миграция
писалась, параллельная сессия закоммитила f25e7fa19cbc (products_unit) поверх
той же af3caa6082ed. Чтобы не оставлять в git две головы, down_revision был
перенесён на f25e7fa19cbc.

Примечание (2026-09-01, ребейз #2): пока эта цепочка (c4d5e6f7a8b9 →
z9a8b7c6d5e4 → h8j2k4m6n8p0) ещё не была закоммичена, параллельная сессия
закоммитила 2b00d0245ba5 (subsidy_draft_status_and_members) поверх той же
f25e7fa19cbc — снова две головы. down_revision перенесён на 2b00d0245ba5 —
актуальную единственную голову на момент завершения этой цепочки (см.
git ls-files + траверс down_revision). Merge-миграция сознательно не
делается (см. инцидент с merge на неотслеживаемую ревизию).
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = '2b00d0245ba5'
branch_labels = None
depends_on = None

_TAG = "[c4d5e6f7a8b9]"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_organizations" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_organizations")}
    if "dept_assigned_at" not in cols or "position_assigned_at" not in cols:
        # 5324bd4399ee ещё не применена (не должно случиться при линейной
        # истории head, но не падаем на дефектной среде).
        print(f"{_TAG} колонки dept_assigned_at/position_assigned_at отсутствуют — пропуск")
        return

    result = bind.execute(sa.text(
        """
        UPDATE user_organizations
        SET position_assigned_at = COALESCE(hired_at::date, CURRENT_DATE)
        WHERE position IS NOT NULL
          AND position_assigned_at IS NULL
        """
    ))
    print(f"{_TAG} position_assigned_at проставлена (бэкфилл) в строк = {result.rowcount}")

    result = bind.execute(sa.text(
        """
        UPDATE user_organizations
        SET dept_assigned_at = COALESCE(hired_at::date, CURRENT_DATE)
        WHERE dept_id IS NOT NULL
          AND dept_assigned_at IS NULL
        """
    ))
    print(f"{_TAG} dept_assigned_at проставлена (бэкфилл) в строк = {result.rowcount}")


def downgrade() -> None:
    # Бэкфилл данных, откат схемы не откатывает данные — намеренный no-op.
    pass
