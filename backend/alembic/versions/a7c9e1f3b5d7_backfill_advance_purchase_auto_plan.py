"""Backfill: авто-плановые позиции для УЖЕ существующих авансовых отчётов.

Владелец (30.09.2026, повторное и жёсткое решение): «Из авансового все
позиции АВТОМАТИЧЕСКИ привязываются к плану... Это отдельная покупка, которую
человек принёс в чеке — её не было в плане. Не сопоставляем». С этой даты
create_purchase/update_purchase/patch_purchase_item/пересчёт из чеков
(app/services/advance_auto_plan.py::sync_advance_auto_plan_items) заводят
такую позицию сами на каждом сохранении — но у авансовых, заведённых ДО этой
правки и ещё не ушедших дальше «Плана закупок», привязки нет, и без единого
сохранения (которое сделает это само) они остаются вне плана.

Разовый backfill: для авансовых закупок (purchase_method='advance') в
статусах ДО договора ('draft', 'wishes', 'plan_schedule') — то есть состав ещё
может дособираться, а не уже зафиксирован как факт — каждая позиция с
конечной категорией ФЭО (своей, purchase_items.feo_category_id, либо
шапочной, purchases.feo_category_id — тот же fallback, что и везде в
проекте), БЕЗ привязки к плану (feo_planned_item_id IS NULL) и не отмеченная
«сверх плана» (over_plan), получает СОБСТВЕННУЮ новую FeoPlannedItem —
БЕЗ поиска существующей по имени (та же логика, что и в рантайме: одноимённые
позиции из разных чеков — разные плановые строки).

Уже привязанные к плану позиции (feo_planned_item_id IS NOT NULL) НЕ
трогаются — идемпотентно, повторный прогон не находит подходящих строк.
Заявка-компаньон (Wish source='advance_report', связь через
purchase_items.wish_item_id) получает ту же привязку — иначе дашборд заявки
и дашборд закупки разойдутся сразу после миграции.

is_feo_breakdown=False/is_internal_plan=True — то же значение, которое
app.services.feo_import_common.resolve_origin_flags(feo_money=None, ...)
детерминированно возвращает для любой позиции, рождённой из реальной
закупки/заявки, а не из файла ФЭО (см. её докстринг и
app/services/plan_autoassign.py::create_auto_planned_item — тот же путь в
рантайме использует ровно эту функцию, здесь она не вызывается напрямую
только потому, что это чистый SQL/Python backfill без загрузки ORM-графа).

Revision ID: a7c9e1f3b5d7
Revises: r3t5v7x9z1c3
Create Date: 2026-09-30 00:00:03.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a7c9e1f3b5d7"
down_revision = "r3t5v7x9z1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    eligible = conn.execute(sa.text("""
        SELECT
            pi.id AS purchase_item_id,
            pi.wish_item_id,
            COALESCE(pi.feo_category_id, p.feo_category_id) AS eff_category_id,
            pi.item_name,
            pi.quantity,
            pi.unit,
            pi.item_type,
            pi.total_price,
            pi.unit_price
        FROM purchase_items pi
        JOIN purchases p ON p.id = pi.purchase_id
        WHERE p.purchase_method = 'advance'
          AND p.status IN ('draft', 'wishes', 'plan_schedule')
          AND pi.feo_planned_item_id IS NULL
          AND COALESCE(pi.over_plan, false) = false
          AND COALESCE(pi.feo_category_id, p.feo_category_id) IS NOT NULL
        ORDER BY pi.id
    """)).fetchall()

    created = 0
    wish_items_synced = 0
    for row in eligible:
        new_id = conn.execute(sa.text("""
            INSERT INTO feo_planned_items (
                feo_category_id, name, quantity, unit, item_type, amount,
                unit_price, notes, is_active, auto_created,
                is_feo_breakdown, is_internal_plan, payment_mode, created_at
            ) VALUES (
                :cat_id, :name, :qty, :unit, :item_type, :amount,
                :unit_price, :notes, TRUE, TRUE,
                FALSE, TRUE, 'one_time', now()
            )
            RETURNING id
        """), {
            "cat_id": row.eff_category_id,
            "name": row.item_name,
            "qty": row.quantity,
            "unit": row.unit,
            "item_type": row.item_type,
            "amount": row.total_price,
            "unit_price": row.unit_price,
            "notes": "Создано миграцией backfill авансовых плановых позиций (30.09.2026)",
        }).scalar_one()
        created += 1

        conn.execute(sa.text("""
            UPDATE purchase_items
            SET feo_planned_item_id = :fpi_id, feo_category_id = :cat_id, over_plan = FALSE
            WHERE id = :pi_id
        """), {"fpi_id": new_id, "cat_id": row.eff_category_id, "pi_id": row.purchase_item_id})

        # Заявка-компаньон авансового отчёта (source='advance_report') — зеркалим
        # ту же привязку через существующий hard link purchase_items.wish_item_id
        # (см. app/services/advance_wish_sync.py::apply_wish_item_feo_link_to_purchase_item,
        # то же направление, что и в рантайме).
        if row.wish_item_id is not None:
            result = conn.execute(sa.text("""
                UPDATE wish_items
                SET feo_planned_item_id = :fpi_id, feo_category_id = :cat_id, over_plan = FALSE
                WHERE id = :wi_id
            """), {"fpi_id": new_id, "cat_id": row.eff_category_id, "wi_id": row.wish_item_id})
            if result.rowcount:
                wish_items_synced += 1

    print(
        f"[a7c9e1f3b5d7] авто-плановых позиций создано: {created}, "
        f"заявок-компаньонов синхронизировано: {wish_items_synced}"
    )


def downgrade() -> None:
    # Намеренно no-op — откат означал бы стирание созданных плановых позиций
    # и обнуление привязок, которые к этому моменту уже могут использоваться
    # человеком (тот же подход, что у соседних data-backfill миграций, см.
    # r3t5v7x9z1c3/b7d9f1h3j5k7).
    pass
