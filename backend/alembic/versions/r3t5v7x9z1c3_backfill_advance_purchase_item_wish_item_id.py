"""Backfill: purchase_items.wish_item_id для УЖЕ существующих авансовых закупок.

Владелец (продолжение инцидента заявки №88 / РЕЕ-2026-00962, 2026-09-30):
create_purchase/update_purchase теперь проставляют hard link
purchase_items.wish_item_id → wish_items.id при КАЖДОЙ пересборке WishItems
компаньона (см. app/services/advance_wish_sync.py — без него построчная
правка ФЭО согласующим в заявке-компаньоне, patch_wish_execution, не находит
строку закупки для обновления). Но у уже существующих на проде авансовых этот
link ещё NULL — до первого PUT такой закупки перепривязка в компаньоне снова
не доедет. Эта миграция — разовый backfill уже существующих пар.

Сопоставление строк (WishItem ↔ PurchaseItem) для пары
Purchase(purchase_method='advance', wish_id=W) ↔ Wish(id=W, source='advance_report'):
  - ТОЛЬКО пары с ОДИНАКОВЫМ числом строк с обеих сторон (иначе несоответствие
    уже само по себе сигнал рассинхрона состава — не гадаем, пропускаем ВСЮ
    закупку целиком);
  - позиционно по row_number() OVER (ORDER BY id) — тот же порядок, в котором
    purchases.py копирует позиции закупки → WishItem (см. wish_item_kwargs_from_purchase_item);
  - ДОПОЛНИТЕЛЬНО требуем совпадения item_name у сопоставляемой по номеру
    строки пары — расхождение имени на той же позиции означает, что состав
    успел разъехаться (ручная правка в обход обычного пути) и угадывать
    сопоставление небезопасно, пропускаем закупку целиком;
  - только там, где purchase_items.wish_item_id IS NULL (идемпотентно —
    повторный прогон не находит строк; НЕ перезаписывает уже проставленный
    link, в т.ч. поставленный кодом после этой миграции).

Revision ID: r3t5v7x9z1c3
Revises: d0g2i4k6m8o0
Create Date: 2026-09-30 00:00:02.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "r3t5v7x9z1c3"
down_revision = "d0g2i4k6m8o0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text("""
        WITH pairs AS (
            -- Пары закупка↔компаньон с ОДИНАКОВЫМ числом строк с обеих сторон.
            SELECT p.id AS purchase_id, w.id AS wish_id
            FROM purchases p
            JOIN wishes w ON w.id = p.wish_id AND w.source = 'advance_report'
            WHERE p.purchase_method = 'advance'
              AND (
                  SELECT COUNT(*) FROM purchase_items pi WHERE pi.purchase_id = p.id
              ) = (
                  SELECT COUNT(*) FROM wish_items wi WHERE wi.wish_id = w.id
              )
        ),
        pi_numbered AS (
            SELECT pi.id AS purchase_item_id, pi.purchase_id, pi.item_name, pi.wish_item_id,
                   row_number() OVER (PARTITION BY pi.purchase_id ORDER BY pi.id) AS rn
            FROM purchase_items pi
            JOIN pairs ON pairs.purchase_id = pi.purchase_id
        ),
        wi_numbered AS (
            SELECT wi.id AS wish_item_id, wi.wish_id, wi.item_name,
                   row_number() OVER (PARTITION BY wi.wish_id ORDER BY wi.id) AS rn
            FROM wish_items wi
            JOIN pairs ON pairs.wish_id = wi.wish_id
        ),
        -- Закупки, где ХОТЯ БЫ одна позиционная пара разошлась по item_name —
        -- пропускаем целиком (не угадываем сопоставление при разъехавшемся составе).
        mismatched_purchases AS (
            SELECT DISTINCT pairs.purchase_id
            FROM pairs
            JOIN pi_numbered pin ON pin.purchase_id = pairs.purchase_id
            JOIN wi_numbered win ON win.wish_id = pairs.wish_id AND win.rn = pin.rn
            WHERE pin.item_name IS DISTINCT FROM win.item_name
        ),
        matched AS (
            SELECT pin.purchase_item_id, win.wish_item_id
            FROM pairs
            JOIN pi_numbered pin ON pin.purchase_id = pairs.purchase_id
            JOIN wi_numbered win ON win.wish_id = pairs.wish_id AND win.rn = pin.rn
            WHERE pin.wish_item_id IS NULL
              AND pairs.purchase_id NOT IN (SELECT purchase_id FROM mismatched_purchases)
        )
        UPDATE purchase_items pi
        SET wish_item_id = m.wish_item_id
        FROM matched m
        WHERE pi.id = m.purchase_item_id
    """))
    print(f"[r3t5v7x9z1c3] purchase_items.wish_item_id backfilled: {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — откат означал бы стирание восстановленной связи (тот
    # же подход, что у соседних data-backfill миграций, см. b7d9f1h3j5k7).
    pass
