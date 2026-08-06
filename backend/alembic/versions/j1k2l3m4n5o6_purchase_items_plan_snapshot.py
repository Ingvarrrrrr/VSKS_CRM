"""purchase_items: снимок плана (planned_quantity/planned_unit_price/planned_total)

ШАГ 1 плана «план ≠ факт» (C:\\Users\\1\\.claude\\plans\\zany-fluttering-mountain.md).

Корень проблемы: у позиции закупки ОДНО поле цены (unit_price/total_price) —
одновременно «что выставили на закупку (ТЗ)», «план» и, пока нет договорных
данных, «факт». Правка цены по итогам закупки задним числом искажала ТЗ и
(в некоторых путях расчёта) двигала план. Эта миграция заводит отдельный
СНИМОК плана на позиции — planned_quantity/planned_unit_price/planned_total —
который дальше (код в wishes.py/purchases.py, тот же коммит) заполняется при
постановке в план и НЕ трогается после ухода закупки из статуса «План
закупок» (заморозка снимка — фактическая БЛОКИРОВКА правки поля вводится
отдельно, Шаг 2 плана, здесь только не портим уже заполненный снимок).

Что делает миграция (в этом порядке, каждый шаг печатает число строк):
  1. ADD COLUMN IF NOT EXISTS purchase_items.planned_quantity/planned_unit_price/
     planned_total (nullable) — идемпотентно, безопасно против check_schema/
     повторного прогона.
  2. Восстановление испорченного ТЗ: для позиций с wish_item_id, где
     purchase_items.unit_price разошёлся с wish_items.unit_price (кто-то поверх
     ТЗ вписал цену по итогам закупки в то же поле) — unit_price/total_price
     возвращаются из заявки (источник правды ТЗ), а прежнее (испорченное,
     вероятно фактическое) значение переносится в final_unit_price/final_total
     — но ТОЛЬКО если эти поля ещё пусты (не перетираем уже существующий факт).
     Если final_* уже заполнены — строка НЕ трогается вообще, попадает в отчёт
     для ручного разбора владельцем.
  3. Backfill снимка: для позиций с wish_item_id — planned_* из
     wish_items.quantity/unit_price/total_price (после шага 2 это то же, что и
     restored unit_price/total_price, но берём явно из заявки — источник
     правды); для позиций без wish_item_id — planned_* из текущих
     quantity/unit_price/total_price. Guard planned_total IS NULL — идемпотентно,
     повторный прогон не переписывает уже проставленный вручную снимок.
  4. Санитайзер-отчёт (ТОЛЬКО печать в лог миграции, ничего не правит):
     а) листья ФЭО (нет дочерних категорий), где planned_quantity > 1 и
        planned_quantity × planned_amount расходится с budget более чем вдвое —
        подозрение «в поле цены за единицу записали сумму» (кандидат К1 из
        Шага 0 диагностики);
     б) дубли FeoPlannedItem с одинаковым нормализованным (trim+lower) именем в
        одной активной категории — подозрение «старая позиция не деактивирована,
        рядом создана новая по факту» (кандидат К2).
     Отчёт печатается в лог `docker compose up -d --build backend` /
     `alembic upgrade head` — править по нему нужно ОТДЕЛЬНЫМ управляемым
     скриптом по согласованию с владельцем, не молча.

downgrade(): DROP COLUMN IF EXISTS (снимок необратимо теряется, unit_price/
total_price/final_* восстановлению шага 2 не подлежат — это ожидаемо для
downgrade структурной миграции).

Revision ID: j1k2l3m4n5o6
Revises: i9j0k1l2m3n4
Create Date: 2026-08-06 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'j1k2l3m4n5o6'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'purchase_items' not in inspector.get_table_names():
        return

    # --- 1. ADD COLUMN IF NOT EXISTS -----------------------------------------
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS planned_quantity NUMERIC(15, 4)"
    ))
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS planned_unit_price NUMERIC(15, 2)"
    ))
    op.execute(sa.text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS planned_total NUMERIC(15, 2)"
    ))

    has_wish_items = 'wish_items' in inspector.get_table_names()

    # --- 2. Восстановление испорченного ТЗ -----------------------------------
    if has_wish_items:
        diverged_total = bind.execute(sa.text(
            "SELECT COUNT(*) FROM purchase_items pi JOIN wish_items wi ON wi.id = pi.wish_item_id "
            "WHERE pi.wish_item_id IS NOT NULL AND pi.unit_price IS DISTINCT FROM wi.unit_price"
        )).scalar() or 0
        diverged_restorable = bind.execute(sa.text(
            "SELECT COUNT(*) FROM purchase_items pi JOIN wish_items wi ON wi.id = pi.wish_item_id "
            "WHERE pi.wish_item_id IS NOT NULL AND pi.unit_price IS DISTINCT FROM wi.unit_price "
            "AND pi.final_unit_price IS NULL AND pi.final_total IS NULL"
        )).scalar() or 0
        diverged_skipped_ids = [r[0] for r in bind.execute(sa.text(
            "SELECT pi.id FROM purchase_items pi JOIN wish_items wi ON wi.id = pi.wish_item_id "
            "WHERE pi.wish_item_id IS NOT NULL AND pi.unit_price IS DISTINCT FROM wi.unit_price "
            "AND (pi.final_unit_price IS NOT NULL OR pi.final_total IS NOT NULL)"
        )).fetchall()]

        restore_result = bind.execute(sa.text(
            "UPDATE purchase_items pi SET "
            "  final_unit_price = pi.unit_price, "
            "  final_total = pi.total_price, "
            "  unit_price = wi.unit_price, "
            "  total_price = wi.total_price "
            "FROM wish_items wi "
            "WHERE pi.wish_item_id = wi.id "
            "  AND pi.unit_price IS DISTINCT FROM wi.unit_price "
            "  AND pi.final_unit_price IS NULL AND pi.final_total IS NULL"
        ))
        print(
            f"[j1k2l3m4n5o6] восстановление ТЗ: разошлось с заявкой {diverged_total} строк, "
            f"восстановлено (вернули unit_price/total_price из заявки, старое значение → "
            f"final_unit_price/final_total) {restore_result.rowcount} строк, "
            f"пропущено (final_* уже заполнены, НЕ тронуты, см. отчёт) {len(diverged_skipped_ids)} строк"
        )
        if diverged_skipped_ids:
            print(f"[j1k2l3m4n5o6] отчёт: пропущенные purchase_items.id (final_* уже занят) = {diverged_skipped_ids}")
    else:
        print("[j1k2l3m4n5o6] таблицы wish_items нет — восстановление ТЗ пропущено")

    # --- 3. Backfill снимка плана ---------------------------------------------
    if has_wish_items:
        linked_result = bind.execute(sa.text(
            "UPDATE purchase_items pi SET "
            "  planned_quantity = wi.quantity, "
            "  planned_unit_price = wi.unit_price, "
            "  planned_total = wi.total_price "
            "FROM wish_items wi "
            "WHERE pi.wish_item_id = wi.id AND pi.planned_total IS NULL"
        ))
        print(f"[j1k2l3m4n5o6] backfill снимка из заявки (wish_item_id IS NOT NULL): {linked_result.rowcount} строк")

    direct_result = bind.execute(sa.text(
        "UPDATE purchase_items SET "
        "  planned_quantity = quantity, "
        "  planned_unit_price = unit_price, "
        "  planned_total = total_price "
        "WHERE wish_item_id IS NULL AND planned_total IS NULL"
    ))
    print(f"[j1k2l3m4n5o6] backfill снимка из текущих значений (wish_item_id IS NULL): {direct_result.rowcount} строк")

    # --- 4. Санитайзер-отчёт (только печать, ничего не правит) ---------------
    has_feo_categories = 'feo_categories' in inspector.get_table_names()
    if has_feo_categories:
        suspicious = bind.execute(sa.text(
            "SELECT c.id, c.name, c.subsidy_id, c.budget, c.planned_quantity, c.planned_amount, "
            "       (c.planned_quantity * c.planned_amount) AS plan_calc "
            "FROM feo_categories c "
            "WHERE c.id NOT IN (SELECT DISTINCT parent_id FROM feo_categories WHERE parent_id IS NOT NULL) "
            "  AND c.planned_quantity IS NOT NULL AND c.planned_quantity > 1 "
            "  AND c.planned_amount IS NOT NULL "
            "  AND c.budget IS NOT NULL AND c.budget > 0 "
            "  AND (c.planned_quantity * c.planned_amount) > (c.budget * 2)"
        )).fetchall()
        if suspicious:
            print(f"[j1k2l3m4n5o6] САНИТАЙЗЕР К1 (подозрение «сумма в поле цены за ед.»): {len(suspicious)} категорий")
            for r in suspicious:
                print(
                    f"[j1k2l3m4n5o6]   feo_category id={r[0]} name={r[1]!r} subsidy_id={r[2]} "
                    f"budget={r[3]} planned_quantity={r[4]} planned_amount={r[5]} "
                    f"planned_quantity*planned_amount={r[6]} — ПРОВЕРИТЬ ВРУЧНУЮ, не правится автоматически"
                )
        else:
            print("[j1k2l3m4n5o6] САНИТАЙЗЕР К1: подозрительных категорий не найдено")

    has_feo_planned_items = 'feo_planned_items' in inspector.get_table_names()
    if has_feo_planned_items:
        dupes = bind.execute(sa.text(
            "SELECT feo_category_id, lower(trim(name)) AS norm_name, COUNT(*) AS cnt, "
            "       array_agg(id ORDER BY id) AS ids, array_agg(amount ORDER BY id) AS amounts "
            "FROM feo_planned_items "
            "WHERE is_active = TRUE "
            "GROUP BY feo_category_id, lower(trim(name)) "
            "HAVING COUNT(*) > 1"
        )).fetchall()
        if dupes:
            print(f"[j1k2l3m4n5o6] САНИТАЙЗЕР К2 (дубли плановых позиций по имени): {len(dupes)} групп")
            for r in dupes:
                print(
                    f"[j1k2l3m4n5o6]   feo_category_id={r[0]} name={r[1]!r} count={r[2]} "
                    f"ids={r[3]} amounts={r[4]} — предложение: деактивировать новые дубли "
                    f"вручную по согласованию с владельцем, не правится автоматически"
                )
        else:
            print("[j1k2l3m4n5o6] САНИТАЙЗЕР К2: дублей плановых позиций не найдено")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'purchase_items' not in inspector.get_table_names():
        return
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS planned_quantity"))
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS planned_unit_price"))
    op.execute(sa.text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS planned_total"))
