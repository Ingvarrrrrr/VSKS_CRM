"""Плановая позиция: отдельная цена ЗА ЕДИНИЦУ (feo_planned_items.unit_price)

Владелец (2026-09-02), заводя плановую позицию «Логистические услуги»: «Я на
самом деле не хочу здесь указывать количество услуг, я её знаю примерно. Я
знаю сумму, которая у меня на это есть, это 200 000, я хочу ввести, что это
примерно 20 услуг. При этом тогда не надо автоматически делить сумму на
количество и препятствовать дальнейшему продвижению, что у меня поставка
превышает 10 000. Должно быть поле с ценой за ед. — если её вводят, тогда
сумма считается путём умножения; если не ввели, то сумма и есть сумма, не
надо делить и блокировать.»

До этой миграции feo_planned_items.amount была ИТОГОВОЙ суммой, а контроль
превышения плана (assert_tz_not_over_plan, app/services/feo_plan.py) всегда
ДЕЛИЛ amount на quantity, чтобы получить цену за единицу для проверки — из-за
этого условная сумма «200 000 ₽ / ~20 услуг» неявно превращалась в потолок
«10 000 ₽ за услугу», и покупка 21-й услуги в пределах тех же 200 000 ₽
блокировалась 409-м, хотя владелец явно этого не просил.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - unit_price   NUMERIC(15,2)  NULL — цена за единицу; NULL = не задана.

Семантика (см. FeoPlannedItem.unit_price в модели и assert_tz_not_over_plan):
  - unit_price задана  → план полноценный: количество, цена за единицу и
    сумма проверяются все, как раньше (amount = quantity × unit_price).
  - unit_price NULL    → amount является ИТОГОВОЙ суммой сама по себе,
    quantity — ОРИЕНТИРОВОЧНОЕ количество, деление НЕ выполняется, контроль
    превышения ограничивает только сумму.

ПОСЛАБЛЕНИЕ (осознанное, не забытый регресс): у всех позиций, заведённых до
этой миграции, unit_price = NULL — они автоматически переходят во второй,
более мягкий режим (раньше по ним работало деление amount/quantity и
ограничение по цене за единицу). Явно зафиксировано здесь и в докстринге
assert_tz_not_over_plan, чтобы не выглядеть незамеченной порчей контроля.

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'z1a2b3c4d5e6'
down_revision = 'p9r2t5v8x1z4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "unit_price" not in existing_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "unit_price" in existing_cols:
        op.drop_column("feo_planned_items", "unit_price")
