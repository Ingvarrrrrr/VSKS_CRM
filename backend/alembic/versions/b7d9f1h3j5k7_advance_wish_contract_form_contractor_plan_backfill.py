"""Backfill: заявки-компаньоны авансовых отчётов (wishes.source='advance_report')
без формы договора/контрагента/привязки позиций к плану.

Владелец (жалоба по заявке №88, РЕЕ-2026-00962, 2026-09-30): на авто-заявке
компаньоне авансового отчёта пустая «Форма договора», пустой контрагент и
плашка «Позиции этой закупки пока не привязаны к плановой позиции», хотя в
самом авансовом всё привязано к плану. Причина — create_purchase (и
синхронизация при правке) не копировали эти поля с закупки на компаньона
(исправлено отдельно, см. app/services/advance_wish_sync.py, ПРАВИЛО №6).
Эта миграция — разовый backfill уже существующих строк.

Только там, где значение сейчас NULL (идемпотентно — повторный прогон не
находит строк):
  1) wishes.contract_form ← purchases.contract_form связанной закупки, иначе
     'goods_single' (см. ADVANCE_DEFAULT_CONTRACT_FORM — авансовые отчёты не
     оформляются рамочным договором, «разовый договор» ближе всего по смыслу
     из 9 существующих форм, services/dictionaries.py::CONTRACT_FORM_LABELS).
  2) wishes.contractor_id ← purchases.contractor_id, если задан на закупке.
  3) wishes.contractor_name ← ФИО (или логин) создателя заявки — ТОЛЬКО когда
     у закупки нет ни contractor_id (Purchase не хранит свободный
     contractor_name).
  4) wish_items.feo_planned_item_id ← purchase_items.feo_planned_item_id той
     же закупки, сопоставление по (item_name, quantity, total_price) —
     ТОЛЬКО когда пара уникальна с обеих сторон (COUNT(*) OVER (...) = 1);
     неоднозначные (несколько позиций с одинаковым именем/кол-вом/суммой)
     сознательно пропускаются, а не угадываются.

Закупка-источник ищется по purchases.wish_id = wishes.id (основное
направление, см. create_purchase) с фолбэком на wishes.purchase_id.

Revision ID: b7d9f1h3j5k7
Revises: f4g6h8j0k2l4
Create Date: 2026-09-30 00:00:01.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "b7d9f1h3j5k7"
down_revision = "f4g6h8j0k2l4"
branch_labels = None
depends_on = None


# Общий CTE, связывающий заявку-компаньон с её закупкой — переиспользуется в
# каждом UPDATE ниже (один источник направления связи, ПРАВИЛО №6).
_LINKED_CTE = """
    WITH linked AS (
        SELECT w.id AS wish_id,
               COALESCE(pw.id, w.purchase_id) AS purchase_id
        FROM wishes w
        LEFT JOIN LATERAL (
            SELECT p.id FROM purchases p WHERE p.wish_id = w.id ORDER BY p.id LIMIT 1
        ) pw ON true
        WHERE w.source = 'advance_report'
    )
"""


def upgrade() -> None:
    conn = op.get_bind()

    # 1) contract_form
    result = conn.execute(sa.text(_LINKED_CTE + """
        UPDATE wishes w
        SET contract_form = COALESCE(p.contract_form, 'goods_single')
        FROM linked l
        JOIN purchases p ON p.id = l.purchase_id
        WHERE w.id = l.wish_id
          AND w.contract_form IS NULL
    """))
    if result.rowcount:
        print(f"[b7d9f1h3j5k7] wishes.contract_form backfilled: {result.rowcount}")

    # 2) contractor_id (закупка знает контрагента)
    result = conn.execute(sa.text(_LINKED_CTE + """
        UPDATE wishes w
        SET contractor_id = p.contractor_id
        FROM linked l
        JOIN purchases p ON p.id = l.purchase_id
        WHERE w.id = l.wish_id
          AND w.contractor_id IS NULL
          AND w.contractor_name IS NULL
          AND p.contractor_id IS NOT NULL
    """))
    if result.rowcount:
        print(f"[b7d9f1h3j5k7] wishes.contractor_id backfilled: {result.rowcount}")

    # 3) contractor_name ← ФИО/логин создателя заявки (закупка контрагента не знает)
    result = conn.execute(sa.text(_LINKED_CTE + """
        UPDATE wishes w
        SET contractor_name = COALESCE(u.full_name, u.username)
        FROM linked l
        JOIN purchases p ON p.id = l.purchase_id
        CROSS JOIN users u
        WHERE w.id = l.wish_id
          AND u.id = w.created_by
          AND w.contractor_id IS NULL
          AND w.contractor_name IS NULL
          AND p.contractor_id IS NULL
          AND (u.full_name IS NOT NULL OR u.username IS NOT NULL)
    """))
    if result.rowcount:
        print(f"[b7d9f1h3j5k7] wishes.contractor_name backfilled from creator: {result.rowcount}")

    # 4) wish_items.feo_planned_item_id — только однозначные совпадения по
    # (item_name, quantity, total_price) в пределах одной закупки.
    result = conn.execute(sa.text(_LINKED_CTE + """,
        wi_keyed AS (
            SELECT wi.id AS wish_item_id, l.purchase_id,
                   wi.item_name, wi.quantity, wi.total_price,
                   COUNT(*) OVER (
                       PARTITION BY l.purchase_id, wi.item_name, wi.quantity, wi.total_price
                   ) AS wi_cnt
            FROM wish_items wi
            JOIN linked l ON l.wish_id = wi.wish_id
            WHERE wi.feo_planned_item_id IS NULL AND l.purchase_id IS NOT NULL
        ),
        pi_keyed AS (
            SELECT pi.purchase_id, pi.item_name, pi.quantity, pi.total_price,
                   pi.feo_planned_item_id,
                   COUNT(*) OVER (
                       PARTITION BY pi.purchase_id, pi.item_name, pi.quantity, pi.total_price
                   ) AS pi_cnt
            FROM purchase_items pi
        ),
        matched AS (
            SELECT DISTINCT wk.wish_item_id, pk.feo_planned_item_id
            FROM wi_keyed wk
            JOIN pi_keyed pk
              ON pk.purchase_id = wk.purchase_id
             AND pk.item_name = wk.item_name
             AND pk.quantity IS NOT DISTINCT FROM wk.quantity
             AND pk.total_price IS NOT DISTINCT FROM wk.total_price
            WHERE wk.wi_cnt = 1 AND pk.pi_cnt = 1
              AND pk.feo_planned_item_id IS NOT NULL
        )
        UPDATE wish_items wi
        SET feo_planned_item_id = m.feo_planned_item_id
        FROM matched m
        WHERE wi.id = m.wish_item_id
    """))
    if result.rowcount:
        print(f"[b7d9f1h3j5k7] wish_items.feo_planned_item_id backfilled (unique match): {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — откат означал бы стирание восстановленных данных
    # (форма/контрагент/привязка к плану), которые были потеряны дефектом, а
    # не введены осознанно; тот же подход, что у соседних data-backfill
    # миграций (e5f7g9h1j3k5, f4g6h8j0k2l4).
    pass
