"""Автотесты на боевой разбор жалобы владельца 2026-09-09 (файл
«ЦЕНТРПОИСК_ВСКС_Новый_ФЭО_...новый.xlsx»): предупреждения импорта ФЭО не
называли номера строк файла и один раз реально считали неверно.

Три дефекта, воспроизведённые dry-run прогоном реального файла и
исправленные в `feo_import_apply.py`/`feo_import_plan.py`/
`feo_import_common.py`:

  A/C. Сводные предупреждения (`duplicate_row_in_file`, `parent_sum_mismatch`)
       и «Сумма по ФЭО одного узла из нескольких строк» (новый kind
       `budget_overwritten_by_row`) не называли ни одной строки файла —
       теперь все номера в тексте через общий helper `format_rows`
       (feo_import_common.py).
  B.   Строка с Суммой по ФЭО, но пустым Уровнем 2, которая НЕ попадает под
       промоушен в направление (Уровень 3 уже заполнен — промоушен работает
       только когда ВСЕ уровни пусты), раньше молча пропадала под общим
       текстом «(пустая строка) — нет наименования»: сумма терялась без
       единого упоминания. Новый kind `amount_without_level2` называет сумму
       прямо в тексте.
  D.   Строка без единого содержательного значения (нет «Товар/услуга», нет
       чисел по ФЭО, цена и сумма плана — 0/пусто), но с технически
       заполненным «Плановое количество» (скопированная 1/100), раньше всё
       равно перезаписывала «план строки» категории суммой 0 — искажая
       сравнение plan_vs_items_mismatch. Теперь такая строка пропускается
       как пустая и планом строки не считается вовсе.

Использует те же макет строки (`mk_row`/`ROW_FIELDS`/`_IDX`) и хелперы
(`_make_subsidy`/`_cleanup_subsidy`/`_get_categories`/`_get_items`/`_import`),
что и `test_feo_import_tree.py` — импортированы оттуда напрямую (Правило №6,
не дублировать макет строки второй раз).

ВАЖНО (та же особенность, что в test_feo_import_tree.py): async-тесты в этом
файле падают с «different loop», если запускать 2+ штук в одном вызове
pytest. Гонять по одному:
`python -m pytest tests/test_feo_import_warnings_rows.py::<имя> -x -q`.
"""
import pytest

from tests.test_feo_import_tree import (
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _import,
    _make_subsidy,
    mk_row,
)


# --- 1. Сводные предупреждения называют номера строк ------------------------

@pytest.mark.asyncio
async def test_duplicate_row_in_file_names_rows(db_session):
    """duplicate_row_in_file обязан называть строку(и)-повтор в тексте, не
    только количество."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Аренда офиса R1", item_name="Аренда офиса R1", plan_sum="1000"),
            mk_row(lvl2="Аренда офиса R1", item_name="Аренда офиса R1", plan_sum="2000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        dup = [w for w in result["warnings"] if w["kind"] == "duplicate_row_in_file"]
        assert len(dup) == 1
        assert "строка 3" in dup[0]["message"], f"должна называться строка-повтор: {dup[0]['message']!r}"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_budget_overwritten_by_row_names_all_rows(db_session):
    """Несколько строк подряд задают Сумму по ФЭО ОДНОГО И ТОГО ЖЕ узла
    (Уровень 3 пуст) — новый warning budget_overwritten_by_row обязан назвать
    ВСЕ строки-кандидаты и их суммы, не только победившую."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Родитель W1", feo_sum="500000"),                        # row 2
            mk_row(lvl2="Родитель W1", lvl3="Дочерний W1", feo_sum="200000"),     # row 3
            mk_row(lvl2="Родитель W1", feo_sum="999999"),                        # row 4
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        overwritten = [w for w in result["warnings"] if w["kind"] == "budget_overwritten_by_row"]
        ow = next((w for w in overwritten if w["name"] == "Родитель W1"), None)
        assert ow is not None, f"нет budget_overwritten_by_row для «Родитель W1»: {result['warnings']}"
        msg = ow["message"]
        assert "2" in msg and "500 000.00" in msg, msg
        assert "4" in msg and "999 999.00" in msg, msg
        assert "учтена последняя (строка 4)" in msg, msg

        cats = await _get_categories(db_session, subsidy.id)
        parent = next(c for c in cats if c.name == "Родитель W1")
        assert parent.budget == 999999, "победить должна последняя строка (4), поведение не меняем"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_parent_sum_mismatch_names_parent_and_children_rows(db_session):
    """parent_sum_mismatch обязан называть строку(и), задавшую бюджет
    родителя, И строки, задавшие бюджеты подразделов, вошедшие в сумму —
    формулировка «раздел .../подразделов», не «Родитель:»."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Родитель W2", feo_sum="500000"),                        # row 2 -> budget родителя
            mk_row(lvl2="Родитель W2", lvl3="Дочерний W2", feo_sum="200000"),     # row 3 -> budget ребёнка
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        mism = [w for w in result["warnings"] if w["kind"] == "parent_sum_mismatch" and w["name"] == "Родитель W2"]
        assert len(mism) == 1
        msg = mism[0]["message"]
        assert "раздела «Родитель W2»" in msg, msg
        assert "500 000.00" in msg and "строка 2" in msg, msg
        assert "200 000.00" in msg and "строка 3" in msg, msg
        assert "подразделов" in msg, msg
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 2. Сумма по ФЭО без Уровня 2 — деньги не пропадают молча ---------------

@pytest.mark.asyncio
async def test_amount_without_level2_names_the_amount(db_session):
    """Уровень 2 пуст, Уровень 3 заполнен (промоушен на направление не
    срабатывает) + Сумма по ФЭО задана → строка пропущена, но
    warning amount_without_level2 называет саму сумму; ничего не создаётся."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(lvl3="Транспорт и техника F1", feo_sum="29000000")]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert result["created"] == 0, "строка без Уровня 2 не должна ничего создавать"

        aw = [w for w in result["warnings"] if w["kind"] == "amount_without_level2"]
        assert len(aw) == 1
        assert aw[0]["row"] == 2
        assert "29 000 000.00" in aw[0]["message"]
        assert "Уровень 2" in aw[0]["message"]

        assert len(result["skipped_details"]) == 1
        _reason = result["skipped_details"][0]["reason"]
        assert "29 000 000.00" in _reason, f"skipped_details не должен молчать про сумму: {_reason!r}"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_row_without_level2_and_without_money_keeps_old_wording(db_session):
    """Контроль: полностью пустая строка (без Уровня 2 И без единой суммы)
    по-прежнему получает старый нейтральный текст, никакой лишней суммы 0 в
    сообщении не появляется."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row()]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "amount_without_level2" for w in result["warnings"])
        assert result["skipped_details"][0]["reason"] == "нет наименования (уровень 2 пуст)"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 3. Полностью пустая строка не создаёт ложное «план = 0» ---------------

@pytest.mark.asyncio
async def test_contentless_row_does_not_fake_zero_plan(db_session):
    """Строка без «Товар/услуга», без сумм по ФЭО, без цены/суммы плана, но
    с технически заполненным «Плановое количество» (дефект боевого файла:
    ПланКол=1, всё остальное пусто/0) — не создаёт запись плана категории и
    НЕ порождает предупреждение о расхождении «план vs сумма позиций»."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(
                lvl2="Направление E1", lvl3="Категория E1",
                item_name="Позиция E1", plan_qty="2", plan_price="1000", plan_sum="2000",
            ),
            # Пустая строка-«хвост»: только plan_qty=1 технический, sum=0.
            mk_row(lvl2="Направление E1", lvl3="Категория E1", plan_qty="1", plan_sum="0"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "plan_vs_items_mismatch" for w in result["warnings"]), (
            f"пустая строка не должна порождать сравнение план/позиции: {result['warnings']}"
        )

        _empty_skip = next(
            (d for d in result["skipped_details"] if d["row"] == 3), None,
        )
        assert _empty_skip is not None, f"строка 3 должна попасть в skipped_details: {result['skipped_details']}"
        assert _empty_skip["reason"] == (
            "нет ни плановой позиции, ни товара/услуги, суммы нулевые — строка пропущена"
        )

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Категория E1")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1, "реальная позиция Ур.5 из строки 2 не должна пострадать"
        assert items[0].amount == 2000
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
