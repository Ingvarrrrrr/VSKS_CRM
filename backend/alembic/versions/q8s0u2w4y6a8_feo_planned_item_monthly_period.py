"""feo_planned_items: конец периода ежемесячного платежа (monthly_end_date) +
нормализация quantity для ежемесячных позиций (владелец, Волна 3, п.3, 2026-09-13).

ЖАЛОБА, часть 1: «Пытаюсь редактировать позицию, требует число в поле
"Количество месяцев", хотя я ввёл "6,66"... Наверное, надо для ежемесячных
платежей ввести количество месяцев и дней сверх месяцев целых... должно быть
помесячная оплата из месяца в месяц.» Решение (владелец): период «с даты по
дату» вместо целого «Количество месяцев» — см. app/services/
feo_monthly_schedule.py (compute_monthly_schedule, единственная формула) и
FeoPlannedItem.monthly_end_date.

ЖАЛОБА, часть 2 («двоится Количество»): «Кол-во» 6.66, а в данные по субсидии
идёт число 6.66 под видом планового количества — количество ТОВАРА/УСЛУГИ и
количество МЕСЯЦЕВ путались в одном поле quantity. Причина в проде: при
Integer-валидации months_count дробное «6,66» уходило в quantity (Numeric,
дробей не запрещает) и оттуда — в SUM(FeoPlannedItem.quantity) фолбэка
«План» категории (app/routers/feo_planned_items_reports.py::cat_plan_fallback),
всплывая как «плановое количество» на уровне субсидии.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  feo_planned_items:
    - monthly_end_date   DATE  NULL — конец периода; NULL = легаси-режим
      (months_count работает по-старому, см. модель/compute_monthly_schedule).

Backfill (идемпотентно, WHERE-условие после первого прогона не находит строк):
  для ВСЕХ активных и неактивных позиций payment_mode='monthly' quantity
  нормализуется в 1 — для ежемесячного платежа quantity не участвует в
  формуле суммы (amount = monthly_amount × months_count/период) НИ ДО, НИ
  ПОСЛЕ этой правки, единственная его историческая роль — случайно
  просочившееся число месяцев. Годные значения (уже 1 или NULL) не трогает.
  Обычные (payment_mode='one_time') позиции backfill не затрагивает.

Перед применением на проде посчитать затрагиваемые строки:
  SELECT count(*) FROM feo_planned_items
  WHERE payment_mode = 'monthly' AND quantity IS DISTINCT FROM 1;

Downgrade — DROP COLUMN IF EXISTS monthly_end_date; backfill quantity не
откатывается (тот же паттерн необратимого DML-backfill, что и в
o7q9s1u3w5y7_feo_categories_zero_budget_to_null.py) — старое значение quantity
для ежемесячных позиций уже не несло смысла до этой миграции.

Revision ID: q8s0u2w4y6a8
Revises: o7q9s1u3w5y7
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'q8s0u2w4y6a8'
down_revision = 'o7q9s1u3w5y7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "monthly_end_date" not in existing_cols:
        op.add_column(
            "feo_planned_items",
            sa.Column("monthly_end_date", sa.Date(), nullable=True),
        )

    op.execute(
        "UPDATE feo_planned_items SET quantity = 1 "
        "WHERE payment_mode = 'monthly' AND quantity IS DISTINCT FROM 1"
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("feo_planned_items")}
    if "monthly_end_date" in existing_cols:
        op.drop_column("feo_planned_items", "monthly_end_date")
