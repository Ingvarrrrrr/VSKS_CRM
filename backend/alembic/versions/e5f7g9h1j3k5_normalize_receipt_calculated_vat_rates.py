"""Backfill: расчётные ставки НДС из чеков ФНС ('22/122', '20/120', '10/110',
'5/105', '7/107') → обычная процентная запись ('22%', '20%', '10%', '5%', '7%').

Владелец (2026-09-30, авансовый ФАДМ_2026, позиция «ЛУКОЙЛ МОТО 2Т» — vat_rate
хранился буквально как "22/122", НДС сумма в документе считалась 0,00 —
_parse_vat_rate_percent/parseVatRatePercent не понимали дробную запись):
«преобразовывать к 22%, а не писать тупо из чека». Код-источник
(app/services/receipts_parsing.py::NDS_CODE_TO_RATE_STR) исправлен отдельно
(та же сессия) — новые чеки пишут сразу "22%"/"20%"/... Эта миграция —
backfill уже сохранённых значений в трёх текстовых vat_rate-колонках
(purchase_items, contract_items, wish_items — единственные String(20)
vat_rate; Purchase.vat_rate/Wish.vat_rate — Integer, дробной записи там нет
физически). _parse_vat_rate_percent/parseVatRatePercent на чтении тоже умеют
X/1XX как X% защитно, но хранить нормализованную строку правильнее — меньше
особых случаев в коде документов/экспортов дальше по цепочке.

Идемпотентно (WHERE vat_rate IN (...) — повторный прогон после первого не
находит строк для замены).

Revision ID: e5f7g9h1j3k5
Revises: c5d7e9f1a3b5
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "e5f7g9h1j3k5"
down_revision = "c5d7e9f1a3b5"
branch_labels = None
depends_on = None


# X/(100+X) → "X%" — тот же маппинг, что теперь в NDS_CODE_TO_RATE_STR.
_RATE_MAP = {
    "20/120": "20%",
    "10/110": "10%",
    "5/105": "5%",
    "7/107": "7%",
    "22/122": "22%",
}

_TABLES = ["purchase_items", "contract_items", "wish_items"]


def upgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        for old, new in _RATE_MAP.items():
            result = conn.execute(sa.text(
                f"UPDATE {table} SET vat_rate = :new WHERE vat_rate = :old"
            ), {"new": new, "old": old})
            if result.rowcount:
                print(f"[e5f7g9h1j3k5] {table}.vat_rate '{old}' -> '{new}': {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — откат означал бы возврат к нечитаемой для
    # _parse_vat_rate_percent записи, без какой-либо практической пользы.
    pass
