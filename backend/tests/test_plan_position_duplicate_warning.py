"""Владелец (2026-09-29): «про то, что это дубликат, ничего не написано; я это
уже просил» — боевой случай на проде: плановая позиция «Брендвол» попала в ДВЕ
заявки (№83 конвертирована в закупку РЕЕ-2026-00959, №82 осталась на
согласовании), и карточка заявки №82 не показывала, что позиция уже занята.

Покрывает:
  1. GET /api/feo-categories/plan-positions отдаёт linked_purchases (с
     registry_number/status/wish_id) для плановой позиции уровня ЛИСТА
     (kind='plan_position' — план введён прямо на FeoCategory, БЕЗ отдельной
     FeoPlannedItem) — раньше это поле считалось ТОЛЬКО для kind='planned_item'
     (см. app.services.feo_plan_fact.category_plan_links, новая функция).
  2. Та же плановая позиция отдаёт linked_wishes — другую незакрытую заявку
     (submitted), у которой WishItem ссылается на ту же категорию.
  3. app.services.plan_duplicate_warning.collect_plan_duplicate_warnings находит
     дубль и формирует предупреждение с номером закупки и заявки-источника —
     тот самый текст, который теперь видит согласующий заявки №82 ДО того, как
     подтвердит согласование (см. app.routers.wish_approvals.decide_wish_approval).

Вызывает сервисы напрямую (без HTTP/FastAPI DI), как test_feo_plan_tree_scenarios.py —
не требует авторизации, быстрее и не зависит от роутинга.
"""
import uuid
from decimal import Decimal

import pytest

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem


async def _make_subsidy_leaf(db_session, org_id, qty=2, unit_price=14_757):
    subsidy = Subsidy(name=f"TestDup-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    leaf = FeoCategory(
        subsidy_id=subsidy.id, level=1, name="Брендвол",
        planned_quantity=Decimal(str(qty)), planned_amount=Decimal(str(unit_price)),
    )
    db_session.add(leaf)
    await db_session.commit()
    await db_session.refresh(leaf)
    return subsidy, leaf


async def _make_wish(db_session, org_id, subsidy_id, feo_category_id, status, qty=2, unit_price=14_757, planned_item_id=None):
    total = Decimal(str(qty)) * Decimal(str(unit_price))
    wish = Wish(title="Заявка теста дубля", status=status, org_id=org_id, subsidy_id=subsidy_id)
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    wi = WishItem(
        wish_id=wish.id, item_name="Брендвол", quantity=Decimal(str(qty)),
        unit="шт", unit_price=Decimal(str(unit_price)), total_price=total,
        feo_category_id=feo_category_id, feo_planned_item_id=planned_item_id,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)
    return wish, wi


async def _make_purchase_from_wish(db_session, subsidy_id, feo_category_id, wish_id, registry_number, qty=2, unit_price=14_757, status="work_in_progress"):
    total = Decimal(str(qty)) * Decimal(str(unit_price))
    p = Purchase(
        subsidy_id=subsidy_id, feo_category_id=feo_category_id, wish_id=wish_id,
        item_name="Брендвол", registry_number=registry_number, status=status,
        planned_quantity=Decimal(str(qty)), planned_total_price=total,
        total_nmck=total, nmck=total,
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id, item_name="Брендвол", quantity=Decimal(str(qty)), unit="шт",
        unit_price=Decimal(str(unit_price)), total_price=total, feo_category_id=feo_category_id,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return p, pi


@pytest.mark.asyncio
async def test_plan_positions_show_linked_purchase_and_wish_for_leaf_category(db_session, test_org):
    """Заявка №83 (converted) уже породила закупку РЕЕ-... по «Брендвол» — заявка
    №82 (submitted), запрашивающая /plan-positions для той же плановой позиции
    (kind='plan_position', план введён прямо на листе, без FeoPlannedItem),
    обязана увидеть linked_purchases (с registry_number/status/wish_id) И
    linked_wishes (другая незакрытая заявка на ту же категорию)."""
    from app.routers.feo_plan_reads_tree import get_plan_positions

    subsidy, leaf = await _make_subsidy_leaf(db_session, test_org.id)
    wish83, _wi83 = await _make_wish(db_session, test_org.id, subsidy.id, leaf.id, status="converted")
    purchase, _pi = await _make_purchase_from_wish(
        db_session, subsidy.id, leaf.id, wish_id=wish83.id, registry_number="РЕЕ-2026-00959",
    )
    wish82, _wi82 = await _make_wish(db_session, test_org.id, subsidy.id, leaf.id, status="submitted")

    rows = await get_plan_positions(
        subsidy_id=subsidy.id, exclude_purchase_id=None, exclude_wish_id=wish82.id,
        db=db_session, _=None,
    )
    row = next(r for r in rows if r["category_id"] == leaf.id and r["kind"] == "plan_position")

    assert row["linked_purchases"], "leaf-level (kind='plan_position') plan position must expose linked_purchases too"
    lp = row["linked_purchases"][0]
    assert lp["registry_number"] == "РЕЕ-2026-00959"
    assert lp["wish_id"] == wish83.id
    assert lp["status_label"]

    # wish82 сама себя не видит среди linked_wishes (excluded); а другая
    # открытая заявка на ту же категорию — видна была бы, если бы существовала.
    assert all(w["id"] != wish82.id for w in row["linked_wishes"])


@pytest.mark.asyncio
async def test_duplicate_warning_on_second_wish_targeting_occupied_plan(db_session, test_org):
    """collect_plan_duplicate_warnings — согласующий заявки №82 должен увидеть
    предупреждение о дубле ДО подтверждения (см. wish_approvals.decide_wish_approval)."""
    from app.services.plan_duplicate_warning import collect_plan_duplicate_warnings

    subsidy, leaf = await _make_subsidy_leaf(db_session, test_org.id)
    wish83, _wi83 = await _make_wish(db_session, test_org.id, subsidy.id, leaf.id, status="converted")
    await _make_purchase_from_wish(
        db_session, subsidy.id, leaf.id, wish_id=wish83.id, registry_number="РЕЕ-2026-00959",
    )
    wish82, wi82 = await _make_wish(db_session, test_org.id, subsidy.id, leaf.id, status="submitted")

    warnings = await collect_plan_duplicate_warnings(db_session, [wi82], exclude_wish_id=wish82.id)

    assert len(warnings) == 1
    w = warnings[0]
    assert w["type"] == "duplicate"
    assert "Брендвол" in w["message"]
    assert "РЕЕ-2026-00959" in w["message"]
    assert f"№{wish83.id}" in w["message"]

    # Никакого дубля, если исключить саму заявку-конкурента из выборки нельзя —
    # но если запрос идёт от ИМЕНИ заявки №83 (её же собственная закупка) — тишина.
    warnings_self = await collect_plan_duplicate_warnings(db_session, [_wi83], exclude_wish_id=wish83.id)
    assert warnings_self == []
