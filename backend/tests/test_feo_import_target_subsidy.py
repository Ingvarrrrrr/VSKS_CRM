"""Автотесты на баг 2026-09-09 (прод, владелец): импорт ФЭО в открытую (только
что созданную, пустую) субсидию «ЦП_2026_2» показывал «Будет обновлено: N»,
хотя обновлять было нечего.

Разбор (см. docstring `resolve_target_subsidy_id` в feo_import_common.py и
комментарий у `existing_plan_item_ids` в feo_import_apply.py) дал ДВЕ разные
находки:

1. Латентный риск (пункт A/B задания, подтверждён эмпирически, но НЕ был
   причиной конкретной жалобы владельца): если колонка «Субсидия» файла
   называет ДРУГУЮ существующую субсидию, `default_subsidy_id` (открытая
   карточка) раньше проигрывал — строки на 100% уходили в чужую субсидию.
   Открытая субсидия должна побеждать безусловно.
2. Настоящая причина жалобы (разобрана по скриншоту владельца): в файле
   ОДНА и та же позиция (одинаковое имя в одной категории) встречалась
   ДВАЖДЫ — вторая строка «находила» позицию, созданную первой строкой ЭТОГО
   ЖЕ импорта (видна через `db.flush()` в той же транзакции), и отчитывалась
   как «обновлена позиция», что выглядело как обновление существующих данных
   в пустой субсидии. Имя в колонке «Субсидия» при этом было именем УЖЕ
   УДАЛЁННОЙ субсидии — фолбэк на открытую сработал верно, дело было не в
   маршрутизации.

`_do_feo_import` вызывается НАПРЯМУЮ (тот же приём, что и в
test_feo_import_tree.py) — колонки задаются индексами через свой собственный
18-колоночный макет строки `mk_row(...)`.

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_target_subsidy.py::<имя> -x -q`.
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.routers.feo_categories import _do_feo_import
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


ROW_FIELDS = [
    "subsidy_name", "lvl2", "lvl3", "lvl4", "item_name", "item_type",
    "item_qty", "item_unit", "item_amt", "item_price",
    "code", "appendix", "budget", "active",
]
_IDX = {name: i for i, name in enumerate(ROW_FIELDS)}


def mk_row(**kwargs):
    unknown = set(kwargs) - set(ROW_FIELDS)
    assert not unknown, f"неизвестные поля строки: {unknown}"
    row = [None] * len(ROW_FIELDS)
    for k, v in kwargs.items():
        row[_IDX[k]] = v
    return row


async def _make_subsidy(db_session, name=None, budget=0):
    s = Subsidy(
        name=name or f"TestFeoImportTarget-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _cleanup_subsidy(db_session, subsidy_id):
    """Убирает за собой всё, что мог создать импорт: позиции → категории →
    саму субсидию. Явные DELETE, не полагаемся на ON DELETE CASCADE."""
    await db_session.execute(text(
        "DELETE FROM feo_planned_items WHERE feo_category_id IN "
        "(SELECT id FROM feo_categories WHERE subsidy_id = :sid)"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM feo_categories WHERE subsidy_id = :sid"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM subsidies WHERE id = :sid"
    ), {"sid": subsidy_id})
    await db_session.commit()


async def _get_categories(db_session, subsidy_id):
    res = await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    return res.scalars().all()


async def _get_items(db_session, feo_category_id):
    res = await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == feo_category_id)
    )
    return res.scalars().all()


async def _import(db_session, subsidy_id, rows, dry_run=False):
    return await _do_feo_import(
        rows=rows,
        c_subsidy=_IDX["subsidy_name"],
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=_IDX["lvl4"], c_lvl5=_IDX["item_name"],
        c_qty=_IDX["item_qty"], c_unit=_IDX["item_unit"], c_item_amt=_IDX["item_amt"],
        c_item_price=_IDX["item_price"],
        c_code=_IDX["code"], c_appendix=_IDX["appendix"], c_budget=_IDX["budget"], c_active=_IDX["active"],
        c_item_type=_IDX["item_type"],
        default_subsidy_id=subsidy_id,
        dry_run=dry_run,
        db=db_session,
    )


# --- 1. Имя в файле НЕ существует ни в одной субсидии → фолбэк на открытую --

@pytest.mark.asyncio
async def test_nonexistent_subsidy_name_falls_back_to_open_target(db_session):
    """Сценарий владельца: колонка «Субсидия» называет УЖЕ УДАЛЁННУЮ субсидию.
    `sub_by_name.get(...)` промахивается → должна сработать открытая
    (default_subsidy_id), новая пустая субсидия не должна показать
    «обновлено» просто от факта импорта."""
    test_sub = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(subsidy_name="Центрпоиск_2026_2_УДАЛЕНА", lvl2="Направление A", item_name="Товар 1", item_amt=100),
            mk_row(subsidy_name="Центрпоиск_2026_2_УДАЛЕНА", lvl2="Направление B", item_name="Товар 2", item_amt=200),
        ]
        result = await _import(db_session, test_sub.id, rows)
        assert result["errors"] == []
        assert result["updated"] == 0, "новая пустая субсидия не может иметь что обновлять"
        assert result["created"] > 0
        assert not any(w["kind"] == "subsidy_name_ignored" for w in result["warnings"]), \
            "имени нет ни у одной субсидии — предупреждать об игнорировании нечего"

        cats = await _get_categories(db_session, test_sub.id)
        assert len(cats) == 2
        for c in cats:
            assert c.subsidy_id == test_sub.id
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)


# --- 2. Имя в файле совпадает с ДРУГОЙ существующей субсидией --------------

@pytest.mark.asyncio
async def test_existing_other_subsidy_name_ignored_open_subsidy_wins(db_session):
    """Латентный риск (пункт A задания): раньше 100% строк уходило в чужую
    существующую субсидию, названную в файле, открытая оставалась пустой.
    Теперь открытая субсидия побеждает безусловно + одно предупреждение."""
    other_sub = await _make_subsidy(db_session)
    test_sub = await _make_subsidy(db_session)
    try:
        other_cats_before = await _get_categories(db_session, other_sub.id)
        assert len(other_cats_before) == 0

        rows = [
            mk_row(subsidy_name=other_sub.name, lvl2="Направление A", item_name="Товар 1", item_amt=100),
            mk_row(subsidy_name=other_sub.name, lvl2="Направление B", item_name="Товар 2", item_amt=200),
        ]
        result = await _import(db_session, test_sub.id, rows)
        assert result["errors"] == []
        assert result["updated"] == 0

        cats_target = await _get_categories(db_session, test_sub.id)
        cats_other = await _get_categories(db_session, other_sub.id)
        assert len(cats_other) == 0, "чужая субсидия не должна получить ни одной категории"
        assert len(cats_target) == 2, "все строки должны лечь в открытую субсидию"

        _ignored = [w for w in result["warnings"] if w["kind"] == "subsidy_name_ignored"]
        assert len(_ignored) == 1, "одно агрегированное предупреждение, не на каждую строку"
        assert other_sub.name in _ignored[0]["message"]
        assert test_sub.name in _ignored[0]["message"]
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)
        await _cleanup_subsidy(db_session, other_sub.id)


@pytest.mark.asyncio
async def test_subsidy_name_matches_open_target_no_warning(db_session):
    """Имя в файле совпадает с ОТКРЫТОЙ субсидией — поведение прежнее, без
    предупреждения (не молчим только когда есть о чём молчать)."""
    test_sub = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(subsidy_name=test_sub.name, lvl2="Направление A", item_name="Товар 1", item_amt=100),
        ]
        result = await _import(db_session, test_sub.id, rows)
        assert result["errors"] == []
        assert not any(w["kind"] == "subsidy_name_ignored" for w in result["warnings"])
        cats = await _get_categories(db_session, test_sub.id)
        assert len(cats) == 1
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)


# --- 3. Настоящая причина жалобы: повтор строки в самом файле ---------------

@pytest.mark.asyncio
async def test_duplicate_row_in_file_reported_as_repeat_not_update(db_session):
    """Одна и та же позиция (то же имя в той же категории) дважды в файле —
    вторая строка не должна выглядеть как «обновление существующих данных»:
    reason обязан читаться как повтор, со ссылкой на первую строку."""
    test_sub = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Аренда офиса", item_name="Аренда офиса", item_amt=1000),
            mk_row(lvl2="Аренда офиса", item_name="Аренда офиса", item_amt=2000),
        ]
        result = await _import(db_session, test_sub.id, rows)
        assert result["errors"] == []
        assert result["created"] == 2, "1 категория + 1 позиция на первой строке"
        assert result["updated"] == 1, "вторая строка — единственное 'обновление'"
        assert len(result["updated_details"]) == 1
        _reason = result["updated_details"][0]["reason"]
        assert "повтор строки" in _reason, f"неожиданный reason: {_reason!r}"
        assert "повтор строки 2" in _reason, f"должна называться первая строка (row_num=2): {_reason!r}"
        assert "обновлена позиция —" not in _reason, "не должно читаться как обновление существующих данных"

        _dup_warnings = [w for w in result["warnings"] if w["kind"] == "duplicate_row_in_file"]
        assert len(_dup_warnings) == 1
        assert "1" in _dup_warnings[0]["message"]

        cats = await _get_categories(db_session, test_sub.id)
        assert len(cats) == 1
        items = await _get_items(db_session, cats[0].id)
        assert len(items) == 1, "дублей позиции быть не должно — одна и та же строка обновлялась"
        assert items[0].amount == 2000, "должно победить значение из ПОСЛЕДНЕЙ строки файла"
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)


@pytest.mark.asyncio
async def test_real_pre_existing_item_update_keeps_update_wording(db_session):
    """Контроль: позиция, реально существовавшая ДО импорта (создана
    предыдущим отдельным импортом), при повторной загрузке ДОЛЖНА
    по-прежнему читаться как «обновлена позиция», а не как «повтор строки» —
    так и должно быть, тут ничего не сломано."""
    test_sub = await _make_subsidy(db_session)
    try:
        rows1 = [mk_row(lvl2="Аренда офиса", item_name="Аренда офиса", item_amt=1000)]
        result1 = await _import(db_session, test_sub.id, rows1)
        assert result1["created"] == 2

        rows2 = [mk_row(lvl2="Аренда офиса", item_name="Аренда офиса", item_amt=3000)]
        result2 = await _import(db_session, test_sub.id, rows2)
        assert result2["created"] == 0
        assert result2["updated"] == 1
        _reason = result2["updated_details"][0]["reason"]
        assert _reason == "обновлена позиция — значения перезаписаны из файла", f"неожиданный reason: {_reason!r}"
        assert not any(w["kind"] == "duplicate_row_in_file" for w in result2["warnings"])
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)


# --- 4. Тексты не содержат внутреннего жаргона «Ур.N» -----------------------

@pytest.mark.asyncio
async def test_messages_do_not_contain_ur_shorthand(db_session):
    """Владелец: «на какой уровень 5 ссылается, если в шаблоне всего три
    уровня» — «Ур.N» не должно попадать в тексты, уходящие на фронт."""
    test_sub = await _make_subsidy(db_session)
    try:
        rows = [
            # level_gap: lvl2 + lvl4 без lvl3 — "Уровень 4 поднят на место Уровень 3".
            mk_row(lvl2="Направление Gap", lvl4="Статья Gap", item_name="Товар Gap", item_amt=10),
            # level_duplicate: lvl2 и lvl3 названы одинаково после нормализации.
            mk_row(lvl2="Аренда А", lvl3="Аренда А", item_name="Товар Dup", item_amt=20),
            # item_promoted_to_level2: ни одного уровня, только плановая позиция.
            mk_row(item_name="Позиция без уровня", item_amt=30),
            # column_shift: числовая строка попала в колонку "Ед. изм.".
            mk_row(lvl2="Направление Shift", item_name="Товар Shift", item_amt=40, item_unit="123456"),
        ]
        result = await _import(db_session, test_sub.id, rows)
        assert result["errors"] == []

        _texts = []
        for w in result["warnings"]:
            _texts.append(w.get("message") or "")
        for bucket in (result["created_details"], result["updated_details"], result["skipped_details"]):
            for d in bucket:
                _texts.append(d.get("reason") or "")

        _offenders = [t for t in _texts if "Ур." in t]
        assert not _offenders, f"остался внутренний жаргон «Ур.»: {_offenders!r}"
    finally:
        await _cleanup_subsidy(db_session, test_sub.id)
