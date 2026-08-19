"""Разделить «по нашим данным» (ручная отметка) и «подтверждено казначейством».

Владелец (2026-08-19), дословно: «Поставленная человеком галочка, что платёж
прошёл, без подтверждения выпиской из казначейства, не является подтверждением,
что платёж прошёл. Надо разделить, что по нашим данным платёж прошёл и по
казначейству.» Предыдущая волна смешала два факта в одном флаге
payments.matched_confirmed (ручная форма тоже ставила его в True — см.
app/routers/payments.py::create_payment до этой правки).

Схема:
  payments.payment_source          varchar(20) 'manual' | 'statement'
  payments.confirmed_by_statement  boolean — платёж найден в выписке и
                                    разнесён на закупку
  purchases.payment_amount_declared numeric(15,2) — сумма ручных
                                    неподтверждённых («заявлено, ждёт
                                    подтверждения»)
  purchases.payment_amount остаётся «оплачено» — но теперь считается ТОЛЬКО
  по confirmed_by_statement=True (см. app/services/purchase_payments.py).

Бэкфилл (idempotent, через inspector-guard):
  payments: bank_payment_id IS NOT NULL → payment_source='statement',
            confirmed_by_statement=true; иначе → 'manual', false.
  purchases.payment_amount / payment_amount_declared пересчитываются из
  payments по новой классификации (только для purchase_id, у которых есть
  строки payments — остальные не трогаем, чтобы не затирать legacy-значения,
  проставленные напрямую импортом/руками мимо таблицы payments).

Локально (2026-08-19) payments пуста (0 строк) — бэкфилл/пересчёт отработает
на 0 строк, колонки просто появятся.

downgrade() — no-op: см. паттерн b4c8e1a6f3d9/y2z3a4b5c6d7 (новые колонки
используются новой логикой разнесения payment_lookup.py/purchase_payments.py,
откатывать данные-классификацию некуда).

Revision ID: c7d9f2a1b3e5
Revises: b4c8e1a6f3d9
Create Date: 2026-08-19 15:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7d9f2a1b3e5'
down_revision = 'b4c8e1a6f3d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- 1. payments.payment_source / confirmed_by_statement (idempotent) ---
    if inspector.has_table("payments"):
        existing_cols = {c["name"] for c in inspector.get_columns("payments")}

        if "payment_source" not in existing_cols:
            op.execute(sa.text(
                "ALTER TABLE payments ADD COLUMN payment_source VARCHAR(20) "
                "NOT NULL DEFAULT 'manual'"
            ))
            print("[c7d9f2a1b3e5] payments.payment_source добавлен")

        if "confirmed_by_statement" not in existing_cols:
            op.execute(sa.text(
                "ALTER TABLE payments ADD COLUMN confirmed_by_statement BOOLEAN "
                "NOT NULL DEFAULT FALSE"
            ))
            print("[c7d9f2a1b3e5] payments.confirmed_by_statement добавлен")

        # Бэкфилл классификации по существующему признаку bank_payment_id.
        r1 = bind.execute(sa.text(
            "UPDATE payments SET payment_source = 'statement', confirmed_by_statement = TRUE "
            "WHERE bank_payment_id IS NOT NULL "
            "AND (payment_source IS DISTINCT FROM 'statement' OR confirmed_by_statement IS DISTINCT FROM TRUE)"
        ))
        print(f"[c7d9f2a1b3e5] payments → statement/confirmed: строк = {r1.rowcount}")

        r2 = bind.execute(sa.text(
            "UPDATE payments SET payment_source = 'manual', confirmed_by_statement = FALSE "
            "WHERE bank_payment_id IS NULL "
            "AND (payment_source IS DISTINCT FROM 'manual' OR confirmed_by_statement IS DISTINCT FROM FALSE)"
        ))
        print(f"[c7d9f2a1b3e5] payments → manual/неподтверждён: строк = {r2.rowcount}")

    # --- 2. purchases.payment_amount_declared (idempotent) ---
    if inspector.has_table("purchases"):
        existing_p_cols = {c["name"] for c in inspector.get_columns("purchases")}
        if "payment_amount_declared" not in existing_p_cols:
            op.execute(sa.text(
                "ALTER TABLE purchases ADD COLUMN payment_amount_declared NUMERIC(15, 2)"
            ))
            print("[c7d9f2a1b3e5] purchases.payment_amount_declared добавлен")

    # --- 3. Пересчёт агрегатов purchases из payments по новой классификации ---
    if inspector.has_table("payments") and inspector.has_table("purchases"):
        r3 = bind.execute(sa.text("""
            UPDATE purchases p SET
                payment_amount = agg.confirmed_total,
                payment_amount_declared = agg.declared_total
            FROM (
                SELECT
                    purchase_id,
                    SUM(amount) FILTER (WHERE confirmed_by_statement = TRUE) AS confirmed_total,
                    SUM(amount) FILTER (WHERE payment_source = 'manual' AND confirmed_by_statement = FALSE) AS declared_total
                FROM payments
                WHERE purchase_id IS NOT NULL
                GROUP BY purchase_id
            ) agg
            WHERE p.id = agg.purchase_id
        """))
        print(f"[c7d9f2a1b3e5] purchases пересчитаны из payments: строк = {r3.rowcount}")


def downgrade() -> None:
    # No-op намеренно — см. докстринг модуля.
    pass
