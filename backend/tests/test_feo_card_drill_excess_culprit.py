"""test_feo_card_drill_excess_culprit.py — виновники превышения направления
по типу (card="free", kind≠"all"), владелец 08.10.2026: раскрытие направления
с превышением в окне «Свободно — товары/услуги» показывало ВЕСЬ состав
плановых позиций (десятки строк) — «какие именно закупки дали превышение —
абсолютно непонятно». Новый файл (ПРАВИЛО №5 — не дописываем в
test_feo_card_drill.py, отдельная ответственность: не сама карточка, а отбор
виновников внутри неё).

Проверяет app.services.feo_card_drill._excess_culprit_items (вызывается
card_drill_rows для card="free", kind≠"all" — см. докстринг модуля и функции):
от самой НОВОЙ плановой позиции (created_at DESC) накапливаем сумму, пока она
не покроет |amount| строки направления; граничная позиция несёт ЧАСТЬ своей
суммы как "over_amount". Фабрики переиспользованы из
test_feo_plan_tree_scenarios.py (ПРАВИЛО №6)."""
from decimal import Decimal

import pytest

from app.services.feo_card_drill import card_drill_rows
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


async def _set_created_at(db_session, item, dt):
    item.created_at = dt
    await db_session.commit()
    await db_session.refresh(item)


@pytest.mark.asyncio
async def test_culprit_is_only_newest_item_covering_excess(db_session, test_org):
    """ФЭО (бюджет направления по типу «товар») 1000, позиции 600 (старая) +
    300 + 200 (новая) = 1100 → превышение 100. Виновником обязана оказаться
    ТОЛЬКО новая позиция (200), со over_amount=100 — а не весь состав из трёх
    позиций."""
    import datetime as _dt

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    old = await _make_planned_item(db_session, article.id, "Старая позиция (600)", 1, 600)
    old.item_type = "товар"
    mid = await _make_planned_item(db_session, article.id, "Средняя позиция (300)", 1, 300)
    mid.item_type = "товар"
    new = await _make_planned_item(db_session, article.id, "Новая позиция (200)", 1, 200)
    new.item_type = "товар"
    await db_session.commit()
    await _set_created_at(db_session, old, _dt.datetime(2026, 1, 1, 10, 0, 0))
    await _set_created_at(db_session, mid, _dt.datetime(2026, 1, 2, 10, 0, 0))
    await _set_created_at(db_session, new, _dt.datetime(2026, 1, 3, 10, 0, 0))

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    assert result["reason"] is None
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["budget_amount"] == pytest.approx(1000.0)
    assert row["planned_amount"] == pytest.approx(1100.0)
    assert row["amount"] == pytest.approx(-100.0)

    # Полный состав (для ссылки «Показать весь состав») — все 3 позиции, как и раньше.
    assert len(row["items"]) == 3

    # Виновники — ТОЛЬКО новая позиция (200), сверх ФЭО = 100.
    assert len(row["excess_items"]) == 1
    culprit = row["excess_items"][0]
    assert culprit["name"] == "Новая позиция (200)"
    assert culprit["amount"] == pytest.approx(200.0)
    assert culprit["over_amount"] == pytest.approx(100.0)
    assert culprit["purchase_id"] is None  # не привязана к закупке

    # Σ over_amount обязана совпасть с превышением направления (|amount|).
    assert row["excess_items_total"] == pytest.approx(abs(row["amount"]))


@pytest.mark.asyncio
async def test_culprit_is_single_large_new_item(db_session, test_org):
    """ФЭО 1000, позиции 600 (старая) + 500 (новая) = 1100 → превышение 100.
    Виновник — новая позиция (500), over_amount=100 (та же логика, другое
    соотношение сумм — граничная позиция крупнее самого превышения)."""
    import datetime as _dt

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    article = await _make_category(db_session, subsidy.id, name="Статья", parent_id=direction.id)

    old = await _make_planned_item(db_session, article.id, "Старая позиция (600)", 1, 600)
    old.item_type = "товар"
    new = await _make_planned_item(db_session, article.id, "Новая позиция (500)", 1, 500)
    new.item_type = "товар"
    await db_session.commit()
    await _set_created_at(db_session, old, _dt.datetime(2026, 1, 1, 10, 0, 0))
    await _set_created_at(db_session, new, _dt.datetime(2026, 1, 2, 10, 0, 0))

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    row = result["rows"][0]
    assert row["amount"] == pytest.approx(-100.0)
    assert len(row["items"]) == 2

    assert len(row["excess_items"]) == 1
    culprit = row["excess_items"][0]
    assert culprit["name"] == "Новая позиция (500)"
    assert culprit["amount"] == pytest.approx(500.0)
    assert culprit["over_amount"] == pytest.approx(100.0)
    assert row["excess_items_total"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_no_excess_no_culprits(db_session, test_org):
    """Без превышения (план <= ФЭО) — excess_items обязаны остаться пустыми,
    поведение строки не меняется (владелец: «для направления без превышения —
    как сейчас»)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    direction = await _make_category(db_session, subsidy.id, name="Направление", budget=Decimal("1000"))
    item = await _make_planned_item(db_session, direction.id, "Позиция", 1, 400)
    item.item_type = "товар"
    await db_session.commit()

    result = await card_drill_rows(db_session, subsidy.id, "free", "goods")
    row = result["rows"][0]
    assert row["amount"] == pytest.approx(600.0)
    assert row["excess_items"] == []
    assert row["excess_items_total"] == pytest.approx(0.0)
