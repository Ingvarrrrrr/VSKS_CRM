"""Регресс-тесты на кеш `state.planned_items_by_category` (ревью 12.10.2026,
задача владельца «ускорить import-mapped» — N+1 по плановым позициям
категории заменён на один batch-SELECT, см. `preload_planned_items_by_category`/
`get_planned_items_for_category` в app/services/feo_import_duplicates.py).

Повод ревью: раньше КАЖДЫЙ SELECT внутри `_matching_items`/`apply_collected_plan`
делал autoflush и видел позиции, уже `db.add`'нутые раньше в этом же импорте —
batch-кеш, прогретый ОДИН раз ДО `finalize_lvl5_items`, этого не умеет сам по
себе. Разбор по коду (а не по догадке) показал: сегодня это НЕ ведёт к
расхождению, потому что действуют два инварианта:

  1. `lvl5_leaves.add(leaf.id)` вызывается в ОБОИХ местах `feo_import_apply.py`,
     где строка регистрируется в `pending_lvl5_items` (строки ~836 и ~1535) —
     значит множество leaf.id из `pending_lvl5_items` ВСЕГДА подмножество
     `lvl5_leaves`. `apply_collected_plan` (feo_import_plan.py) делает
     построчный SELECT существующих позиций ТОЛЬКО для `_cat_id NOT IN
     lvl5_leaves` (ветка «ЛИСТ без своих позиций Ур.5») — то есть ТОЛЬКО для
     категорий, которых `finalize_lvl5_items` не касался вовсе в этом же
     импорте. Пересечения множеств «кого коснулся finalize_lvl5_items» и
     «кого коснётся построчный SELECT в apply_collected_plan» в принципе нет.
  2. `group_key(subsidy_id, path, item_name)` включает ИМЯ позиции — одно и то
     же имя в одном и том же листе всегда один и тот же ключ словаря
     `pending_lvl5_items`, то есть ОДНА группа, а не две. Сценарий «вторая
     группа того же листа должна увидеть позицию, созданную первой» (риск
     ревью, п.2) требует ДВУХ групп с ОДНИМ И ТЕМ ЖЕ именем в одном листе —
     такого не бывает по построению словаря.

Итог: для сегодняшнего кода цепочка «создание → устаревшее прочтение» не
возникает. Тесты ниже НЕ пытаются искусственно обойти эти два инварианта (это
означало бы тестировать код, которого нет) — вместо этого:

  (A) `test_cache_invalidation_mechanism_sees_new_item` — прямой unit-тест
      механизма (`invalidate_planned_items_cache`/`get_planned_items_for_category`):
      кладём в кеш заведомо устаревший список, добавляем новую позицию мимо
      кеша (как в реальном коде — `db.add`+`db.flush`), зовём
      `invalidate_planned_items_cache` и проверяем, что следующее чтение видит
      новую позицию. Без этого вызова — не увидело бы (кеш оставался бы
      прежним списком).
  (B) `test_mixed_update_and_create_same_leaf_cached_matches_uncached` и
      `test_plan_row_leaf_with_preexisting_item_cached_matches_uncached` —
      сквозная проверка «с кешем и с принудительно отключённым кешем —
      ОДИНАКОВЫЙ результат» (как попросило ревью), на двух реалистичных
      сценариях (несколько групп дублей в одном листе, лист с «планом строки»
      без собственных Ур.5-позиций) — защита от будущей регрессии, если
      инварианты выше когда-нибудь перестанут выполняться.

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_planned_items_cache.py::<имя> -x -q`.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.feo_planned_item import FeoPlannedItem
from app.routers.feo_categories import _do_feo_import
from app.services import feo_import_core, feo_import_duplicates, feo_import_plan
from app.services.feo_import_duplicates import (
    get_planned_items_for_category,
    invalidate_planned_items_cache,
)
from tests.test_feo_import_tree import (
    _IDX,
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _make_subsidy,
    mk_row,
)


async def _import(db_session, subsidy_id, rows):
    return await _do_feo_import(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=_IDX["lvl4"], c_lvl5=_IDX["item_name"],
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=_IDX["code"], c_appendix=_IDX["appendix"], c_budget=_IDX["budget"], c_active=_IDX["active"],
        c_amt_lvl2=_IDX["amt_lvl2"],
        c_row_feo_qty=_IDX["feo_qty"], c_row_feo_unit=_IDX["feo_unit"],
        c_row_feo_price=_IDX["feo_price"], c_row_feo_sum=_IDX["feo_sum"],
        c_row_plan_qty=_IDX["plan_qty"], c_row_plan_unit=_IDX["plan_unit"],
        c_row_plan_price=_IDX["plan_price"], c_row_plan_sum=_IDX["plan_sum"],
        c_item_type=_IDX["item_type"],
        default_subsidy_id=subsidy_id,
        dry_run=False,
        db=db_session,
    )


async def _snapshot(db_session, subsidy_id):
    """Категории+позиции без id/дат — тот же приём, что в
    profile_feo_import.py, использованном для boевого профилирования этой же
    задачи (ускорение import-mapped)."""
    cats = await _get_categories(db_session, subsidy_id)
    by_id = {c.id: c for c in cats}

    def path_key(cat):
        names = []
        cur = cat
        while cur is not None:
            names.append(cur.name)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        names.reverse()
        return tuple(names)

    cat_snap = sorted([
        {"path": path_key(c), "budget": c.budget, "planned_amount": c.planned_amount}
        for c in cats
    ], key=lambda x: x["path"])

    items = []
    for c in cats:
        items.extend(await _get_items(db_session, c.id))
    item_snap = sorted([
        {
            "cat_path": path_key(by_id[it.feo_category_id]),
            "name": it.name, "quantity": it.quantity, "amount": it.amount,
            "is_active": it.is_active,
        }
        for it in items
    ], key=lambda x: (x["cat_path"], x["name"], x["amount"] or Decimal("0")))
    return cat_snap, item_snap


# --- (A) unit-тест самого механизма инвалидации -----------------------------

@pytest.mark.asyncio
async def test_cache_invalidation_mechanism_sees_new_item(db_session):
    """Без `invalidate_planned_items_cache` следующее чтение той же категории
    вернуло бы устаревший список (кеш не знает о позиции, добавленной мимо
    него) — этот тест проверяет САМ механизм хука напрямую, без сборки
    сценария импорта, который заставил бы два места кода столкнуться (см.
    докстринг модуля — на сегодня такого сценария в коде нет)."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        result = await _import(db_session, subsidy_id, [
            mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1000"),
        ])
        assert result["errors"] == []
        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Кухня")

        class _FakeState:
            db = db_session
            planned_items_by_category = {}

        state = _FakeState()

        # Прогреваем кеш "устаревшим" снимком — ДО того, как появится новая позиция.
        state.planned_items_by_category[leaf.id] = list(await get_planned_items_for_category(state, leaf.id))
        assert len(state.planned_items_by_category[leaf.id]) == 1

        new_item = FeoPlannedItem(feo_category_id=leaf.id, name="Чайник", amount=Decimal("500"), is_active=True)
        db_session.add(new_item)
        await db_session.flush()

        # Без сброса кеш «не видит» новую позицию.
        stale = state.planned_items_by_category[leaf.id]
        assert len(stale) == 1, "кеш — обычный список в памяти, сам себя не обновляет"

        invalidate_planned_items_cache(state, leaf.id)
        assert leaf.id not in state.planned_items_by_category, "инвалидация должна убрать ключ целиком"

        fresh = await get_planned_items_for_category(state, leaf.id)
        assert len(fresh) == 2, "после инвалидации следующее чтение обязано увидеть новую позицию"
        assert {it.name for it in fresh} == {"Утюг", "Чайник"}
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


# --- (B) сквозная проверка "с кешем == без кеша" -----------------------------

def _disable_cache(monkeypatch):
    """Принудительно отключает batch-кеш: preload — no-op,
    get_planned_items_for_category — всегда свежий SELECT, результат никуда
    не складывается (имитирует ТОЧНО то поведение, что было до этой
    оптимизации — каждый вызов идёт в БД)."""
    async def _noop_preload(state):
        return None

    async def _always_fresh(state, cat_id):
        return (await state.db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == cat_id)
        )).scalars().all()

    monkeypatch.setattr(feo_import_core, "preload_planned_items_by_category", _noop_preload)
    monkeypatch.setattr(feo_import_duplicates, "get_planned_items_for_category", _always_fresh)
    monkeypatch.setattr(feo_import_plan, "get_planned_items_for_category", _always_fresh)


async def _run_mixed_scenario(db_session, subsidy_id):
    """Лист «Кухня» уже содержит «Утюг» (создан предыдущим импортом) — новый
    импорт ОБНОВЛЯЕТ «Утюг» (новая сумма) И СОЗДАЁТ «Чайник» (новая позиция) в
    ТОМ ЖЕ листе за один проход `finalize_lvl5_items` — ровно тот порядок
    «встретили существующую → затем создали новую в том же листе», который
    опасен для устаревшего кеша."""
    await _import(db_session, subsidy_id, [
        mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1500"),
        mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="2000"),
    ])
    return await _snapshot(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_mixed_update_and_create_same_leaf_cached_matches_uncached(db_session, monkeypatch):
    subsidy_a = await _make_subsidy(db_session)
    subsidy_b = await _make_subsidy(db_session)
    sid_a, sid_b = subsidy_a.id, subsidy_b.id
    try:
        # Общая "предыстория" — импорт 1 в обеих субсидиях одинаков.
        await _import(db_session, sid_a, [mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1000")])
        await _import(db_session, sid_b, [mk_row(lvl2="Кухня", item_name="Утюг", plan_sum="1000")])

        cached_cats, cached_items = await _run_mixed_scenario(db_session, sid_a)

        _disable_cache(monkeypatch)
        uncached_cats, uncached_items = await _run_mixed_scenario(db_session, sid_b)

        assert cached_cats == uncached_cats
        assert cached_items == uncached_items
        assert [it["name"] for it in cached_items] == ["Чайник", "Утюг"] or \
            {it["name"] for it in cached_items} == {"Чайник", "Утюг"}
    finally:
        await _cleanup_subsidy(db_session, sid_a)
        await _cleanup_subsidy(db_session, sid_b)


async def _run_plan_row_scenario(db_session, subsidy_id):
    """Лист «Ванная» получает «план строки» через сумму на уровне категории
    (без своей колонки «Плановая позиция» в файле) — apply_collected_plan идёт
    в построчную ветку «ЛИСТ без своих позиций Ур.5» и обязан найти/обновить
    уже существующую позицию «Ванная» (заведённую предыдущим импортом) через
    get_planned_items_for_category, а не создать вторую."""
    await _import(db_session, subsidy_id, [
        mk_row(lvl2="Ванная", plan_sum="3000"),
    ])
    return await _snapshot(db_session, subsidy_id)


@pytest.mark.asyncio
async def test_plan_row_leaf_with_preexisting_item_cached_matches_uncached(db_session, monkeypatch):
    subsidy_a = await _make_subsidy(db_session)
    subsidy_b = await _make_subsidy(db_session)
    sid_a, sid_b = subsidy_a.id, subsidy_b.id
    try:
        await _import(db_session, sid_a, [mk_row(lvl2="Ванная", plan_sum="1000")])
        await _import(db_session, sid_b, [mk_row(lvl2="Ванная", plan_sum="1000")])

        cached_cats, cached_items = await _run_plan_row_scenario(db_session, sid_a)

        _disable_cache(monkeypatch)
        uncached_cats, uncached_items = await _run_plan_row_scenario(db_session, sid_b)

        assert cached_cats == uncached_cats
        assert cached_items == uncached_items
        assert len(cached_items) == 1, "повторный план строки обновляет, а не задваивает позицию"
        assert cached_items[0]["amount"] == Decimal("3000")
    finally:
        await _cleanup_subsidy(db_session, sid_a)
        await _cleanup_subsidy(db_session, sid_b)
