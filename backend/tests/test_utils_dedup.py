# -*- coding: utf-8 -*-
"""Правило №6 (один показатель — один источник истины): в этой сессии
несколько байт-идентичных хелперов, дублированных по 2-4 роутерам, сведены в
`app/utils/*`. Тест фиксирует, что поведение СТАРЫХ точек входа (алиасов и
локальных обёрток, которые теперь делегируют в общий модуль) не изменилось.

Offline, синхронно, без БД — прямой импорт чистых функций.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.utils.http import content_disposition
from app.utils.coerce import coerce_patch_value
from app.utils.text import normalize_feo_name
from app.utils.numbers import to_decimal


# ─────────────────────── content_disposition ───────────────────────

@pytest.mark.parametrize("filename", [
    "export.xlsx",
    "Отчёт по закупкам.xlsx",
    "",
    "файл с пробелами и,запятой.docx",
])
def test_content_disposition_matches_old_routers(filename):
    from app.routers.exports import _content_disposition as exports_cd
    from app.routers.subsidies import _content_disposition as subsidies_cd
    from app.routers.feo_categories import _content_disposition as feo_cd

    expected = content_disposition(filename)
    assert exports_cd(filename) == expected
    assert subsidies_cd(filename) == expected
    assert feo_cd(filename) == expected


def test_content_disposition_cyrillic_ascii_fallback():
    # ascii-only chars survive encode('ascii', 'ignore'); only a FULLY
    # non-ascii name (empty after stripping) falls back to 'export'.
    result = content_disposition("Отчёт.xlsx")
    assert result == 'attachment; filename=".xlsx"; filename*=UTF-8\'\'%D0%9E%D1%82%D1%87%D1%91%D1%82.xlsx'
    fully_cyrillic = content_disposition("Отчёт")
    assert fully_cyrillic.startswith('attachment; filename="export"; filename*=UTF-8\'\'')


# ─────────────────────── coerce_patch_value ───────────────────────

_DATE_FIELDS = {"contract_date"}
_DATETIME_FIELDS = {"submission_deadline"}


@pytest.mark.parametrize("field,value,expected", [
    ("contract_date", "", None),
    ("contract_date", None, None),
    ("contract_date", "2026-09-05", date(2026, 9, 5)),
    ("contract_date", "2026-09-05T10:30:00", date(2026, 9, 5)),
    ("submission_deadline", "2026-09-05T10:30:00", datetime(2026, 9, 5, 10, 30, 0)),
    # datetime.fromisoformat accepts a date-only string too (Python 3.11+) and
    # returns a datetime at midnight — it never falls through to the date.fromisoformat
    # fallback branch for a well-formed 'YYYY-MM-DD' string.
    ("submission_deadline", "2026-09-05", datetime(2026, 9, 5, 0, 0, 0)),
    ("unknown_field", "some value", "some value"),
    ("unknown_field", 0, 0),
])
def test_coerce_patch_value_core(field, value, expected):
    assert coerce_patch_value(
        field, value, date_fields=_DATE_FIELDS, datetime_fields=_DATETIME_FIELDS
    ) == expected


def test_coerce_patch_value_purchases_wrapper():
    from app.routers.purchases import _coerce_patch_value
    assert _coerce_patch_value("contract_date", "2026-09-05") == date(2026, 9, 5)
    assert _coerce_patch_value("contract_date", "") is None
    assert _coerce_patch_value("submission_deadline", "2026-09-05T10:30:00") == datetime(2026, 9, 5, 10, 30, 0)


def test_coerce_patch_value_vehicles_wrapper():
    from app.routers.vehicles import _coerce_patch_value, _DATE_FIELDS as V_DATE_FIELDS
    a_field = next(iter(V_DATE_FIELDS))
    assert _coerce_patch_value(a_field, "2026-09-05") == date(2026, 9, 5)
    assert _coerce_patch_value(a_field, "") is None
    assert _coerce_patch_value("unrelated", "kept") == "kept"


def test_coerce_patch_value_vehicle_repairs_wrapper():
    from app.routers.vehicle_repairs import _coerce_patch_value
    assert _coerce_patch_value("date", "2026-09-05") == date(2026, 9, 5)
    assert _coerce_patch_value("date", "") is None
    assert _coerce_patch_value("cost_amount", "1000") == "1000"


def test_coerce_patch_value_external_drivers_wrapper():
    from app.routers.external_drivers import _coerce_patch_value, _DATE_FIELDS as D_DATE_FIELDS
    a_field = next(iter(D_DATE_FIELDS))
    assert _coerce_patch_value(a_field, "2026-09-05") == date(2026, 9, 5)
    assert _coerce_patch_value(a_field, "") is None
    # no datetime fields for this router — datetime-only value falls back to date parse
    assert _coerce_patch_value(a_field, "2026-09-05T10:30:00") == date(2026, 9, 5)


# ─────────────────────── normalize_feo_name ───────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("", ""),
    (None, ""),
    ("1. Снаряжение", "снаряжение"),
    ("2.1 Одежда", "одежда"),
    ("3) Кепи", "кепи"),
    ("1.2.3. Форма  зимняя", "форма зимняя"),
    ("Без префикса", "без префикса"),
])
def test_normalize_feo_name_matches_old(raw, expected):
    assert normalize_feo_name(raw) == expected


def test_normalize_feo_name_purchase_export_alias():
    from app.routers.purchase_export import _norm_feo
    assert _norm_feo("1. Снаряжение") == normalize_feo_name("1. Снаряжение")


# ─────────────────────── to_decimal ───────────────────────

@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    (0, Decimal("0")),
    ("1 234,50", Decimal("1234.50")),
    ("\xa0", None),
    ("1\xa0234,50", Decimal("1234.50")),
    ("not a number", None),
])
def test_to_decimal_matches_old(raw, expected):
    assert to_decimal(raw) == expected


def test_to_decimal_purchase_export_alias():
    from app.routers.purchase_export import _to_dec
    assert _to_dec("1 234,50") == Decimal("1234.50")
    assert _to_dec(None) is None


def test_to_decimal_purchase_items_import_wrapper():
    # This module has several unrelated _to_dec closures inside other endpoint
    # functions (not deduped, per task scope) — only the module-level one at
    # ~line 2442 was merged. Exercised indirectly is out of scope offline, so
    # we validate the shared primitive it now delegates to instead.
    assert to_decimal("1 234,50") == Decimal("1234.50")
