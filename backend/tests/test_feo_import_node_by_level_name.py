"""Автотесты на ВТОРУЮ часть правила владельца 2026-09-09 (повторный разбор,
решение владельца: дерево/суммы НЕ меняем — файл читается буквально; вместо
переклассификации узлов — ПРЕДУПРЕЖДЕНИЕ о человеческом факторе, когда имя
«Плановой позиции» ГДЕ-ТО в файле само встречается как значение колонки
уровня). См. докстринг `build_level_name_index` в
`app/services/feo_import_common.py` и блок `item_name_used_as_level` в
`app/services/feo_import_apply.py`.

Боевой пример (файл «ЦЕНТРПОИСК_ВСКС...xlsx», без колонки «Уровень 4»):
строка 211 (Ур2=«Логистика и проживание», Ур3=«Межрегиональные перевозки»,
Плановая позиция=«Обеспечение топливом при работах в зоне гуманитарной
помощи», Сумма по ФЭО=200 000) — позиция остаётся внутри «Межрегиональных
перевозок» КАК И БЫЛО (дерево не меняем), но то же имя «Обеспечение
топливом...» встречается как значение Уровня 3 в строке 212 — предупреждение
должно назвать ОБЕ строки (211 и 212).

Используем ту же 18-колоночную тестовую раскладку и `_import17` (c_lvl4=None),
что и `test_feo_import_promote_level.py` — воспроизводит раскладку уровней
боевого файла владельца.

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_node_by_level_name.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest

from tests.test_feo_import_promote_level import _import17
from tests.test_feo_import_tree import _cleanup_subsidy, _get_categories, _get_items, _make_subsidy, mk_row


# --- Строка 211: позиция ОСТАЁТСЯ внутри «Межрегиональных перевозок», но выдано предупреждение

@pytest.mark.asyncio
async def test_item_name_matching_other_row_level_warns_but_keeps_tree(db_session):
    """Имя «Плановой позиции» первой строки совпадает с именем, которое во
    ВТОРОЙ строке файла стоит как значение Уровня 3 — дерево остаётся КАК
    БЫЛО (позиция внутри «Межрегиональные перевозки», её сумма — жёсткая
    расшифровка внутри этой категории, is_feo_breakdown), но выдаётся
    предупреждение `item_name_used_as_level`, называющее ОБЕ строки (211 и
    212), уровень (Уровень 3) и сумму."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Логистика и проживание", lvl3="Межрегиональные перевозки",
                item_name="Обеспечение топливом при работах в зоне гуманитарной помощи",
                feo_sum="200000",
            ),
            # Строка-«декларация» имени как значения Уровня 3 (аналог строки
            # 212 боевого файла) — без денег.
            mk_row(
                lvl2="Логистика и проживание",
                lvl3="Обеспечение топливом при работах в зоне гуманитарной помощи",
            ),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        # Дерево НЕ поменялось: позиция осталась внутри «Межрегиональных перевозок»
        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        leaf = by_name["Межрегиональные перевозки"]
        assert leaf.budget in (None, Decimal("0")), (
            "бюджет категории не должен получить сумму позиции — она осталась расшифровкой"
        )
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "Обеспечение топливом при работах в зоне гуманитарной помощи"
        assert item.amount == Decimal("200000")
        if hasattr(item, "is_feo_breakdown"):
            assert item.is_feo_breakdown is True

        # Предупреждение называет обе строки, уровень и сумму
        w = next(w for w in result["warnings"] if w["kind"] == "item_name_used_as_level")
        assert w["row"] == 2  # первая строка файла = row_num 2
        assert "Уровень 3" in w["message"]
        assert "строка 3" in w["message"]  # номер строки-декларации (row_num=3 в тестовой раскладке)
        assert "Межрегиональные перевозки" in w["message"]
        assert "200 000" in w["message"] or "200000" in w["message"]
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Контроль: имя НЕ встречается нигде как уровень → предупреждения НЕТ (строка 188)

@pytest.mark.asyncio
async def test_item_name_not_matching_anywhere_gets_no_warning(db_session):
    """«Аренда Хендей ГрандСтарекс» (аналог строки 188 боевого файла) — имя не
    встречается нигде в файле как значение колонки уровня → предупреждения
    `item_name_used_as_level` быть не должно. Дерево/суммы не меняются (это
    поведение и так не трогаем — регресс для test_row188_style_... в
    test_feo_import_promote_level.py)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Аренда автотранспортных средств", feo_sum="500000",
                plan_qty="1", plan_unit="услуга",
            ),
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Аренда Хендей ГрандСтарекс", feo_sum="142500",
            ),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "item_name_used_as_level" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Аренда автотранспортных средств")
        assert leaf.budget == Decimal("500000")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        assert items[0].name == "Аренда Хендей ГрандСтарекс"
        assert items[0].amount == Decimal("142500")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Негатив: имя встречается как уровень, но у строки нет денег → предупреждения нет

@pytest.mark.asyncio
async def test_item_name_matching_level_without_money_gets_no_warning(db_session):
    """Имя совпадает со значением Уровня 3 другой строки, но у строки-кандидата
    НЕТ «Суммы по ФЭО» (и вообще никакой денежной колонки) — предупреждение не
    выдаётся: без денег нечего показывать («сумма вошла в расшифровку» было бы
    бессмысленно), сама строка остаётся обычной плановой позицией."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Обеспечение топливом при работах в зоне гуманитарной помощи",
                # ни feo_sum, ни plan_sum/plan_price — денег по строке нет вовсе
            ),
            mk_row(
                lvl2="Логистика и проживание",
                lvl3="Обеспечение топливом при работах в зоне гуманитарной помощи",
            ),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "item_name_used_as_level" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        leaf = by_name["Аренда автотранспортных средств"]
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        assert items[0].name == "Обеспечение топливом при работах в зоне гуманитарной помощи"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- Несколько совпадающих строк → отдельное предупреждение на каждую (не сводится в одно)

@pytest.mark.asyncio
async def test_multiple_matching_rows_get_separate_warnings(db_session):
    """Две РАЗНЫЕ позиции, чьи имена совпадают со значениями уровня где-то в
    файле, должны получить ДВА отдельных предупреждения (каждое со своим
    номером строки) — правило владельца: «это редкий случай, сводить в одно
    не надо»."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Логистика и проживание", lvl3="Межрегиональные перевозки",
                item_name="Обеспечение топливом", feo_sum="200000",
            ),
            mk_row(
                lvl2="Логистика и проживание", lvl3="Аренда автотранспортных средств",
                item_name="Хозяйственные расходы", feo_sum="50000",
            ),
            mk_row(lvl2="Логистика и проживание", lvl3="Обеспечение топливом"),
            mk_row(lvl2="Логистика и проживание", lvl3="Хозяйственные расходы"),
        ]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []
        matches = [w for w in result["warnings"] if w["kind"] == "item_name_used_as_level"]
        assert len(matches) == 2
        rows_warned = {m["row"] for m in matches}
        assert rows_warned == {2, 3}
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
