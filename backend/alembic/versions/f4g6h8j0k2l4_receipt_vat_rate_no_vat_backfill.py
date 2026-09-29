"""Backfill: позиции из чеков (receipt_id заполнен) с пустой vat_rate →
'Без НДС' — то же для связанных contract_items по source_item_id.

Владелец (2026-09-30, авансовый ФАДМ_2026): «если из чека получены данные,
что НДС нет — это не ошибка, это данные: ставка «без НДС»». До правки
receipts_parsing.py::NDS_CODE_TO_RATE_STR код ФФД 6 («НДС не облагается») и
отсутствие тега 'nds' в строке чека маппились в None — документный гейт
(_require_per_item_vat_rate_for_doc, documents/templates.py) не отличал этот
None от «ставка ещё не выбрана» и требовал от человека выбрать ставку у
позиции, которую уже расшифровал чек. Код-источник исправлен отдельно (та же
сессия) — новые позиции из чеков сразу пишут vat_rate='Без НДС'; эта миграция
backfill'ит уже сохранённые NULL у позиций, которые пришли из чека раньше.

Позиции БЕЗ чека (receipt_id IS NULL) не трогаем — там пустая ставка
по-прежнему значит «ещё не выбрано», гейт обязан требовать выбор (см.
templates.py::_require_per_item_vat_rate_for_doc, ветка `not receipt_id`).

Идемпотентно (WHERE vat_rate IS NULL — повторный прогон не находит строк).

Revision ID: f4g6h8j0k2l4
Revises: e5f7g9h1j3k5
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f4g6h8j0k2l4"
down_revision = "e5f7g9h1j3k5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text(
        "UPDATE purchase_items SET vat_rate = 'Без НДС' "
        "WHERE receipt_id IS NOT NULL AND vat_rate IS NULL"
    ))
    if result.rowcount:
        print(f"[f4g6h8j0k2l4] purchase_items.vat_rate NULL -> 'Без НДС' (receipt_id заполнен): {result.rowcount}")

    # contract_items не хранят receipt_id напрямую — наследуют его через
    # source_item_id (FK на purchase_items, см. models/contract_item.py).
    result = conn.execute(sa.text(
        "UPDATE contract_items SET vat_rate = 'Без НДС' "
        "WHERE vat_rate IS NULL AND source_item_id IN ("
        "  SELECT id FROM purchase_items WHERE receipt_id IS NOT NULL"
        ")"
    ))
    if result.rowcount:
        print(f"[f4g6h8j0k2l4] contract_items.vat_rate NULL -> 'Без НДС' (source_item.receipt_id заполнен): {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — откат означал бы возврат к неотличимому от «не
    # выбрано» NULL, без какой-либо практической пользы (та же логика, что и
    # у e5f7g9h1j3k5.downgrade).
    pass
