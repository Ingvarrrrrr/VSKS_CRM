"""Автотесты на два дефекта импорта ФЭО с прода (скриншоты 2026-09-07):

Дефект A (`feo_import_engine.py`, блок «Плановые поля»): сумма плана = 0 без
кол-во раньше всё равно создавала плановую позицию с qty=1 — ноль превращался
в фиктивную позицию «0 шт. по цене 0». Теперь такая строка плановую позицию
не создаёт (в collected_plan не попадает), даётся warning kind
`zero_plan_skipped`; сумма > 0 без кол-во ведёт себя как раньше (qty=1).

Дефект B (`feo_import_engine.py`, блок подсказок отчёта «несопоставленные
узлы»): существующий узел «A / Лист» (2 уровня в БД) не сопоставлялся с новым
путём «A / B / Лист» (в файле появился промежуточный уровень), хотя корень и
лист — те же самые. Добавлена 4-я стратегия подсказки — совпадение по
(корень, лист); при ровно одном кандидате предлагается suggestion с reason
"отличается уровнем вложенности", при нескольких — suggestion остаётся None
(suggestion_candidates только информативно).

Использует те же макет строки (`mk_row`/`ROW_FIELDS`/`_IDX`) и хелперы
(`_make_subsidy`/`_cleanup_subsidy`/`_get_categories`/`_get_items`/`_import`),
что и `test_feo_import_tree.py` — импортированы оттуда напрямую (Правило №6,
не дублировать макет строки второй раз). `_do_feo_import` в этой версии кода
живёт монолитом в `app/services/feo_import_engine.py`, `test_feo_import_tree.py`
импортирует его через `app.routers.feo_categories` (совместимый реэкспорт) —
здесь используется тот же путь, чтобы не заводить второй способ импорта.

ВАЖНО (та же особенность, что в test_feo_import_tree.py): async-тесты в этом
файле падают с «different loop», если запускать 2+ штук в одном вызове
pytest. Гонять по одному:
`python -m pytest tests/test_feo_import_zero_plan_and_leaf_match.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest

from tests.test_feo_import_tree import (
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _import,
    _make_subsidy,
    mk_row,
)


# --- 1. Сумма плана = 0 без кол-во → плановая позиция не создаётся ----------

@pytest.mark.asyncio
async def test_zero_plan_sum_without_qty_skips_planned_item(db_session):
    """plan_sum=0, plan_qty пуст → категория есть, FeoPlannedItem НЕТ, warning
    kind zero_plan_skipped."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление Z1", lvl3="Категория Z1",
            plan_sum="0",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert any(w["kind"] == "zero_plan_skipped" for w in result["warnings"]), (
            "должно быть предупреждение zero_plan_skipped"
        )
        assert not any(w["kind"] == "sum_without_qty" for w in result["warnings"]), (
            "старое предупреждение sum_without_qty (qty=1) не должно выдаваться для нулевой суммы"
        )

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert set(by_name) == {"Направление Z1", "Категория Z1"}, "категория должна быть создана как обычно"
        leaf = by_name["Категория Z1"]

        items = await _get_items(db_session, leaf.id)
        assert items == [], "плановая позиция НЕ должна быть создана для суммы плана = 0"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 2. Сумма плана > 0 без кол-во → прежнее поведение (qty=1) --------------

@pytest.mark.asyncio
async def test_nonzero_plan_sum_without_qty_still_defaults_to_one(db_session):
    """plan_sum=600000, plan_qty пуст → плановая позиция создаётся с qty=1,
    прежнее предупреждение sum_without_qty сохранено."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление Z2", lvl3="Категория Z2",
            plan_sum="600000",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert any(w["kind"] == "sum_without_qty" for w in result["warnings"])
        assert not any(w["kind"] == "zero_plan_skipped" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория Z2")

        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.quantity == Decimal("1")
        assert item.amount == Decimal("600000")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 3. Узел «A / Лист» → «A / B / Лист»: подсказка по (корень, лист) ------

@pytest.mark.asyncio
async def test_unmatched_suggestion_by_leaf_when_level_depth_changes(db_session):
    """Первый импорт создаёт «A / Лист» с ненулевым ФЭО (own_data). Второй
    импорт того же корня с новым промежуточным уровнем «A / B / Лист» не
    трогает старый узел «A / Лист» (другой parent_id) → он должен попасть в
    unmatched (needs_mapping, own_data) с suggestion = «A / B / Лист» и
    reason «отличается уровнем вложенности» (ни одна из трёх прежних
    канонизаций полного пути под это не подходит — уровней стало больше)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows1 = [mk_row(lvl2="Организация питания Z3", lvl3="ИРП/Сухпай Z3", feo_sum="12345")]
        result1 = await _import(db_session, subsidy.id, rows1)
        assert result1["errors"] == []

        rows2 = [mk_row(
            lvl2="Организация питания Z3", lvl3="Питание при проживании Z3", lvl4="ИРП/Сухпай Z3",
            feo_sum="54321",
        )]
        result2 = await _import(db_session, subsidy.id, rows2)
        assert result2["errors"] == []

        unmatched = result2["unmatched"]
        cand = next((u for u in unmatched if u["path"] == "Организация питания Z3 / ИРП/Сухпай Z3"), None)
        assert cand is not None, f"старый узел «A / Лист» должен попасть в unmatched: {unmatched}"
        assert cand["kind"] == "needs_mapping", "узел с ФЭО (own_data) не должен считаться пустым"
        assert cand["suggestion"] == "Организация питания Z3 / Питание при проживании Z3 / ИРП/Сухпай Z3"
        assert cand["suggestion_reason"] == "отличается уровнем вложенности"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 4. Два кандидата с одним листом под тем же корнем → suggestion = None -

@pytest.mark.asyncio
async def test_unmatched_suggestion_none_when_leaf_ambiguous(db_session):
    """Тот же сценарий, что и тест 3, но новый файл содержит ДВА разных пути
    с одинаковым листом «ИРП/Сухпай Z4» под одним корнем — неоднозначность,
    suggestion не предлагается (кандидаты не выбираются автоматически)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows1 = [mk_row(lvl2="Организация питания Z4", lvl3="ИРП/Сухпай Z4", feo_sum="12345")]
        result1 = await _import(db_session, subsidy.id, rows1)
        assert result1["errors"] == []

        rows2 = [
            mk_row(
                lvl2="Организация питания Z4", lvl3="Питание при проживании Z4", lvl4="ИРП/Сухпай Z4",
                feo_sum="1000",
            ),
            mk_row(
                lvl2="Организация питания Z4", lvl3="Иной блок Z4", lvl4="ИРП/Сухпай Z4",
                feo_sum="2000",
            ),
        ]
        result2 = await _import(db_session, subsidy.id, rows2)
        assert result2["errors"] == []

        unmatched = result2["unmatched"]
        cand = next((u for u in unmatched if u["path"] == "Организация питания Z4 / ИРП/Сухпай Z4"), None)
        assert cand is not None
        assert cand["kind"] == "needs_mapping"
        assert cand["suggestion"] is None, "при нескольких кандидатах с одним листом suggestion не предлагается"
        assert cand["suggestion_candidates"] is not None and len(cand["suggestion_candidates"]) == 2
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
