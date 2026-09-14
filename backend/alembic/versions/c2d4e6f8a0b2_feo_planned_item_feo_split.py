"""feo_planned_items.feo_quantity / feo_unit_price / feo_amount — раздельные
числа по ФЭО и по внутреннему плану (владелец, 2026-09-14).

ПРИЧИНА (дословно владелец): «здесь явно не хватает полей для ввода, надо
отдельно если я включил по ФЭО, и отдельно для Внутреннего плана, это нужно
если ФЭО и внутренний план разнятся». ДО этой правки ОБЕ галочки происхождения
(is_feo_breakdown/is_internal_plan, миграция aa1b2c3d4e5f) делили ОДИН комплект
чисел (quantity/unit_price/amount) — FeoLevel5Panel.vue рисовал его дважды под
разными подписями «по ФЭО»/«внутренний план», хотя число было одно и то же.

  feo_planned_items:
    feo_quantity    NUMERIC(15,4) NULL — количество по ФЭО (второй комплект).
    feo_unit_price  NUMERIC(15,2) NULL — цена за единицу по ФЭО.
    feo_amount      NUMERIC(15,2) NULL — сумма по ФЭО.

Существующие quantity/unit_price/amount НЕ переименованы и остаются «планом» —
их по-прежнему читают compute_feo_plan_tree (feo_plan_tree.py),
assert_tz_not_over_plan/assert_tz_batch_not_over_plan (feo_plan_tz_checks.py),
find_excess_culprit/assert_no_unapproved_excess (feo_plan_excess.py). Решение
владельца по опросу: «Суммой плана в дереве, в остатках и в контроле
превышения считается ВНУТРЕННИЙ ПЛАН» — раз имена полей не меняются, ВСЯ эта
арифметика продолжает считать «план = внутренний план» без единой правки
формул (ПРАВИЛО №6 — вторая формула дерева/контроля здесь не понадобилась).
feo_quantity/feo_unit_price/feo_amount — «число по ФЭО» ТОЛЬКО для отображения
рядом с планом «для сверки» (дословно владелец), ни в одной формуле плана или
контроля превышения не участвуют — второй блокирующий механизм сознательно не
заводится.

NULL = «не задано» (не 0, тот же смысл, что и у unit_price, см. её докстринг в
модели) — если человек ставит только одну галочку происхождения, второй
комплект чисел не вводится вовсе и остаётся NULL.

Идемпотентно (ADD COLUMN IF NOT EXISTS, под guard таблицы) — безопасно против
повторного прогона и против check_schema (migrate.py гонит upgrade head на
старте).

БЭКФИЛЛ (решение владельца: «для уже заведённых позиций существующее значение
переносится В ОБА набора полей, чтобы цифры никуда не поехали») — для ВСЕХ
строк, заведённых до этой миграции: feo_quantity=quantity, feo_unit_price=
unit_price, feo_amount=amount. Guard `feo_amount IS NULL AND feo_quantity IS
NULL AND feo_unit_price IS NULL` — идемпотентность: повторный прогон (или
запуск ПОСЛЕ того, как человек уже развёл числа руками) не затирает уже
осознанно различающиеся значения нулевым UPDATE по всем строкам подряд.

Revision ID: c2d4e6f8a0b2
Revises: 8f3db1cb5c70
Create Date: 2026-09-14 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'c2d4e6f8a0b2'
down_revision = '8f3db1cb5c70'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return

    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "feo_quantity NUMERIC(15, 4)"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "feo_unit_price NUMERIC(15, 2)"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "feo_amount NUMERIC(15, 2)"
    ))

    # ---- бэкфилл «в оба набора полей» (см. докстринг выше) ------------------
    op.execute(sa.text("""
        UPDATE feo_planned_items
        SET feo_quantity = quantity,
            feo_unit_price = unit_price,
            feo_amount = amount
        WHERE feo_amount IS NULL AND feo_quantity IS NULL AND feo_unit_price IS NULL
    """))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text("ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS feo_quantity"))
    op.execute(sa.text("ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS feo_unit_price"))
    op.execute(sa.text("ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS feo_amount"))
