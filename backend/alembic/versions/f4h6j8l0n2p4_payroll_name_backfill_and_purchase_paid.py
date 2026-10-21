"""Повторный бэкфилл feo_categories.is_payroll (расширенное правило имени —
«заработная/заробатная/зароботная плата», «зарплата») + разовая простановка
status='paid' закупкам, у которых эффективная статья — ФОТ и которые уже
оплачены, но не помечены.

Повод: прод, субсидия «ХРО_2026» — «Импорт факта» 20.10.2026 создал 3
закупки («ЗП» 8 235 337,78, «Отчисления» 705 426,29, «Командировочные»
67 900,00) на подстатьях «Заработная плата работников» / «Обязательные
начисления на заработную плату работников 7,8%» / «Командировочные расходы»
верхней статьи «Заробатная плата и иные выплаты» (опечатка в данных
владельца). Ни одна статья не была is_payroll — правило имени
(app.services.feo_payroll.is_payroll_name) не знало слова «заработная
плата» до этой же сессии (патч самой функции — отдельным изменением, не
здесь, ПРАВИЛО №6: эта миграция не копирует regex, зовёт ту же функцию, как
6a570b9c50d5 зовёт text_case.capitalize_first — is_payroll_name тоже чистая
функция без зависимостей от БД/app-конфига). Все три закупки:
status=work_in_progress, contract_id NULL, payment_amount_declared ==
planned_total_price (оплачены «по отметке» без договора), но раз статья не
была ФОТ — карточка «Оплачено» их не находила ни в товарах, ни в услугах, и
вся сумма горела «сверх поставленного».

Что делает upgrade():
  1. is_payroll=true для существующих категорий, где is_payroll=false и
     is_payroll_name(name) теперь True (та же формула, что и e3f5g7h9i1j3/
     d4f6h8j0k2l4, просто шире — там было «фот»/«оплата труда»/«выплаты
     персоналу», здесь добавляется «заработная плата»/«зарплата»).
  2. Статус «Оплачено» закупкам, у которых ЭФФЕКТИВНАЯ статья — ФОТ (себя
     ИЛИ любого предка, SQL-перевод app.services.feo_payroll.
     payroll_category_ids — рекурсивный CTE по дереву feo_categories,
     ПРАВИЛО №6: резолвер один, здесь просто SQL-эквивалент того же
     обхода), которые уже оплачены (payment_amount + payment_amount_declared
     > 0), ещё не остановлены (stopped_at IS NULL) и статус ещё не 'paid'.
     Эффективная статья закупки — purchases.feo_category_id ИЛИ
     purchase_items.feo_category_id ИЛИ категория плановой позиции
     (purchase_items.feo_planned_item_id → feo_planned_items.
     feo_category_id).

Идемпотентно — оба шага защищены условием «ещё не применено» (is_payroll
IS false / status <> 'paid'), безопасно гонять повторно. downgrade —
no-op (разовый бэкфилл данных, как у e3f5g7h9i1j3/d4f6h8j0k2l4).

Revision ID: f4h6j8l0n2p4
Revises: ad77191f6be0
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

from app.services.feo_payroll import is_payroll_name

revision = 'f4h6j8l0n2p4'
down_revision = 'ad77191f6be0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- Шаг 1: бэкфилл is_payroll по расширенному правилу имени ---
    rows = bind.execute(sa.text(
        "SELECT id, name FROM feo_categories WHERE NOT is_payroll"
    )).fetchall()
    ids_to_mark = [r.id for r in rows if is_payroll_name(r.name)]
    if ids_to_mark:
        bind.execute(
            sa.text("UPDATE feo_categories SET is_payroll = true WHERE id = ANY(:ids)"),
            {"ids": ids_to_mark},
        )

    # --- Шаг 2: закупки на эффективной статье ФОТ, уже оплаченные, не paid ---
    bind.execute(sa.text(
        r"""
        WITH RECURSIVE cat_payroll AS (
            SELECT id, parent_id, is_payroll AS effective_payroll
            FROM feo_categories
            WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, c.parent_id, (c.is_payroll OR p.effective_payroll) AS effective_payroll
            FROM feo_categories c
            JOIN cat_payroll p ON c.parent_id = p.id
        )
        UPDATE purchases p
        SET status = 'paid'
        WHERE p.stopped_at IS NULL
          AND p.status <> 'paid'
          AND (COALESCE(p.payment_amount, 0) + COALESCE(p.payment_amount_declared, 0)) > 0
          AND (
            EXISTS (
                SELECT 1 FROM cat_payroll cp
                WHERE cp.id = p.feo_category_id AND cp.effective_payroll
            )
            OR EXISTS (
                SELECT 1
                FROM purchase_items pi
                LEFT JOIN cat_payroll cp_item ON cp_item.id = pi.feo_category_id
                LEFT JOIN feo_planned_items fpi ON fpi.id = pi.feo_planned_item_id
                LEFT JOIN cat_payroll cp_plan ON cp_plan.id = fpi.feo_category_id
                WHERE pi.purchase_id = p.id
                  AND (COALESCE(cp_item.effective_payroll, false) OR COALESCE(cp_plan.effective_payroll, false))
            )
          )
        """
    ))


def downgrade() -> None:
    # Разовый бэкфилл данных — откат не возвращает прежние значения (как и
    # у e3f5g7h9i1j3/d4f6h8j0k2l4), downgrade — no-op.
    pass
