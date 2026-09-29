# -*- coding: utf-8 -*-
"""Расчётные ставки НДС из чеков ФНС ('22/122' и т.п.) нормализуются в обычный
процент ('22%') на записи (receipts_parsing.NDS_CODE_TO_RATE_STR) и понимаются
как обычный процент на чтении (stages_amounts._parse_vat_rate_percent /
useVatCalc.parseVatRatePercent на фронте — не проверяется отсюда, offline-тест
бэка) — легаси-защита для уже сохранённых на проде значений.

Владелец (2026-09-30): позиция «ЛУКОЙЛ МОТО 2Т» — vat_rate хранился буквально
как "22/122", НДС сумма считалась 0,00, потому что старый _parse_vat_rate_percent
не умел делить дробную запись.
"""
from app.services.receipts_parsing import NDS_CODE_TO_RATE_STR, _nds_code_to_rate_str
from app.services.documents.stages_amounts import _parse_vat_rate_percent, _item_vat_amount
from types import SimpleNamespace


def test_nds_code_12_maps_to_plain_percent_not_fraction():
    """Код 12 (расчётная ставка 22%, НДС уже в цене) — хранится как '22%',
    не как '22/122' (легаси-формат, который дальше по цепочке не парсился)."""
    assert NDS_CODE_TO_RATE_STR[12] == "22%"
    assert _nds_code_to_rate_str(12) == "22%"


def test_all_calculated_codes_map_to_plain_percent():
    for code, expected in {3: "20%", 4: "10%", 9: "5%", 10: "7%", 12: "22%"}.items():
        assert NDS_CODE_TO_RATE_STR[code] == expected


def test_parse_vat_rate_percent_understands_legacy_fraction_format():
    """Данные, сохранённые ДО фикса (напр. с прода) — '22/122' — по-прежнему
    считаются как 22%, не как 0 (нераспознанная ставка)."""
    assert _parse_vat_rate_percent("22/122") == 22.0
    assert _parse_vat_rate_percent("20/120") == 20.0
    assert _parse_vat_rate_percent("5/105") == 5.0
    assert _parse_vat_rate_percent("7/107") == 7.0
    assert _parse_vat_rate_percent("10/110") == 10.0


def test_parse_vat_rate_percent_plain_percent_unaffected():
    assert _parse_vat_rate_percent("22%") == 22.0
    assert _parse_vat_rate_percent("0%") == 0.0
    assert _parse_vat_rate_percent(None) == 0.0


def test_item_vat_amount_nonzero_for_legacy_fraction_rate():
    """Регресс: позиция со старой '22/122' записью больше не даёт НДС=0,00."""
    item = SimpleNamespace(total_price=1220, vat_rate="22/122")
    amount = _item_vat_amount(item)
    assert amount > 0
    assert amount == round(1220 * 22 / 122, 2)


# ---------------------------------------------------------------------------
# Владелец (30.09, авансовый ФАДМ_2026): «если из чека получены данные, что
# НДС нет — это не ошибка, это данные: ставка «без НДС»» — код ФФД 6 и
# отсутствие тега 'nds' в строке чека раньше маппились в None, неотличимое от
# «ставка не выбрана».
# ---------------------------------------------------------------------------

def test_nds_code_6_maps_to_no_vat_not_none():
    assert NDS_CODE_TO_RATE_STR[6] == "Без НДС"
    assert _nds_code_to_rate_str(6) == "Без НДС"


def test_nds_tag_absent_maps_to_no_vat_not_none():
    """Строка чека без тега 'nds' вовсе (code=None) — тоже 'Без НДС', не None."""
    assert _nds_code_to_rate_str(None) == "Без НДС"


def test_nds_unknown_code_still_maps_to_none():
    """Нераспознанный числовой код — реальная ошибка парсинга, остаётся None."""
    assert _nds_code_to_rate_str(999) is None


def test_item_vat_amount_zero_for_no_vat_rate():
    item = SimpleNamespace(total_price=1000, vat_rate="Без НДС")
    assert _item_vat_amount(item) == 0.0
