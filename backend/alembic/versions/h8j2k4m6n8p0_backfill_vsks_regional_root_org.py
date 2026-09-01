"""Backfill root_org_id для региональных отделений ВСКС

Владелец 2026-09-01: у флага users.all_orgs_access («доступ ко всем
организациям аккаунта») на проде из пяти организаций аккаунта ВСКС
root_org_id был заполнен только у одной (АНО «ЦЕНТРПОИСК», root_org_id=1).
Три региональных отделения — ХРО ВСКС, Донецкое РО ВСКС, ЛУГРО ВСКС —
были заведены суперадмином как «standalone»-организации (root_org_id NULL),
хотя по факту это подразделения того же аккаунта ВСКС (id=1): это видно
по user_org_access — одни и те же сотрудники (напр. Дрелих, Кристи295)
имеют полномочия и в org 1, и в этих региональных орг одновременно.

root_org_id-дерево — канонический расчёт «контура аккаунта»
(app/auth/visibility.compute_account_contour_org_ids), поэтому без этой
связи all_orgs_access не мог показать «все организации аккаунта»: три
региональные орг были не видны сотруднику с включённым флагом, хотя они
и остальные орг ВСКС — один аккаунт.

Матчим по имени (не по id — id специфичны для конкретной БД), идемпотентно
(только если root_org_id ещё NULL, чтобы не затирать ручную правку).
downgrade — no-op: откатывать данные назад в «сломанное» состояние незачем.

Revision ID: h8j2k4m6n8p0
Revises: z9a8b7c6d5e4
Create Date: 2026-09-01 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'h8j2k4m6n8p0'
down_revision = 'z9a8b7c6d5e4'
branch_labels = None
depends_on = None

# Регионы, которые по факту — подразделения аккаунта «ВСКС» (root org).
_REGIONAL_NAMES = (
    'ХРО ВСКС',
    'ДОНЕЦКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ '
    'ОРГАНИЗАЦИИ "ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ"',
    'ЛУГРО ВСКС',
)
_ROOT_NAME = 'ВСКС'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'organizations' not in inspector.get_table_names():
        return

    root_id = bind.execute(
        sa.text("SELECT id FROM organizations WHERE name = :name LIMIT 1"),
        {"name": _ROOT_NAME},
    ).scalar()
    if not root_id:
        return  # окружение без «ВСКС» (напр. чистая тестовая БД) — нечего чинить

    bind.execute(
        sa.text(
            "UPDATE organizations SET root_org_id = :root_id "
            "WHERE name = ANY(:names) AND root_org_id IS NULL AND id != :root_id"
        ),
        {"root_id": root_id, "names": list(_REGIONAL_NAMES)},
    )


def downgrade() -> None:
    # no-op: возврат к «региональные орг вне контура аккаунта» — не нужен,
    # это было единственно неверным состоянием, которое чинит эта миграция.
    pass
