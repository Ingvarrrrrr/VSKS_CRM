"""Дублирование отдельных закупок/заявки из ОДНОЙ субсидии в ДРУГУЮ, уже
существующую (задание владельца 06.10.2026, «ФАДМ_2026» -> «ФАДМ 2026_2»).
Та же техника, что test_subsidy_copy.py — сервис/модуль вызывается напрямую,
db_session = реальная БД в одной транзакции с откатом (conftest.py).
"""
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.subsidy_copy.copy_purchases import copy_purchases
from app.services.subsidy_copy.copy_into_existing import (
    build_category_map,
    build_planned_item_map,
    copy_wishes,
    normalize_name,
    relink_wish_and_purchase_copies,
)

from scripts.copy_into_subsidy import _find_duplicate


async def _make_subsidy(db_session, name: str | None = None) -> Subsidy:
    subsidy = Subsidy(name=name or f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


# --- build_category_map ------------------------------------------------

async def test_category_map_matches_by_path(db_session):
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)

    src_l1 = FeoCategory(subsidy_id=source.id, level=1, name="  Направление  расходов ")
    db_session.add(src_l1)
    await db_session.flush()
    src_l2 = FeoCategory(subsidy_id=source.id, level=2, parent_id=src_l1.id, name="Тип расходов")
    db_session.add(src_l2)
    await db_session.flush()
    # Лист, которого в целевом дереве нет вовсе под совпавшим путём ВЫШЕ —
    # должен найтись «по имени листа внутри совпавшего родителя».
    src_leaf_by_parent = FeoCategory(subsidy_id=source.id, level=3, parent_id=src_l2.id, name="Конкретизация А")
    db_session.add(src_leaf_by_parent)
    # Категория, которой в целевой субсидии нет вообще (ни путь, ни родитель не совпадут).
    src_orphan = FeoCategory(subsidy_id=source.id, level=1, name="Совсем другое направление")
    db_session.add(src_orphan)
    await db_session.commit()

    tgt_l1 = FeoCategory(subsidy_id=target.id, level=1, name="Направление расходов")  # лишние пробелы схлопнутся
    db_session.add(tgt_l1)
    await db_session.flush()
    tgt_l2 = FeoCategory(subsidy_id=target.id, level=2, parent_id=tgt_l1.id, name="ТИП РАСХОДОВ")  # casefold
    db_session.add(tgt_l2)
    await db_session.flush()
    tgt_leaf = FeoCategory(subsidy_id=target.id, level=3, parent_id=tgt_l2.id, name="Конкретизация А")
    db_session.add(tgt_leaf)
    await db_session.commit()
    await db_session.refresh(src_leaf_by_parent)
    await db_session.refresh(src_orphan)
    await db_session.refresh(tgt_leaf)

    result = await build_category_map(db_session, source.id, target.id)

    assert result.map[src_leaf_by_parent.id] == tgt_leaf.id
    assert result.map[src_orphan.id] is None
    assert src_orphan.id in result.unmatched


# --- build_planned_item_map --------------------------------------------

async def test_planned_item_map_matches_by_name(db_session):
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)

    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория")
    db_session.add(src_cat)
    await db_session.flush()
    tgt_cat = FeoCategory(subsidy_id=target.id, level=1, name="Категория")
    db_session.add(tgt_cat)
    await db_session.flush()

    src_item = FeoPlannedItem(feo_category_id=src_cat.id, name="  Бензин  АИ-95 ", amount=Decimal("1000"))
    db_session.add(src_item)
    src_item_no_match = FeoPlannedItem(feo_category_id=src_cat.id, name="Позиция без пары", amount=Decimal("500"))
    db_session.add(src_item_no_match)
    await db_session.flush()

    tgt_item = FeoPlannedItem(feo_category_id=tgt_cat.id, name="бензин аи-95", amount=Decimal("1000"))
    db_session.add(tgt_item)
    await db_session.commit()
    await db_session.refresh(src_item)
    await db_session.refresh(src_item_no_match)
    await db_session.refresh(tgt_item)

    category_map = {src_cat.id: tgt_cat.id}
    result = await build_planned_item_map(db_session, category_map)

    assert result.map[src_item.id] == tgt_item.id
    assert src_item.id not in result.cloned
    # Задание владельца 07.10.2026: «не найдена по имени» внутри СОПОСТАВЛЕННОЙ
    # категории -> клонируется, а не остаётся без плановой.
    cloned_id = result.map[src_item_no_match.id]
    assert cloned_id is not None
    assert cloned_id != src_item_no_match.id
    assert src_item_no_match.id in result.cloned
    cloned_row = await db_session.get(FeoPlannedItem, cloned_id)
    assert cloned_row.feo_category_id == tgt_cat.id
    assert cloned_row.name == src_item_no_match.name
    assert cloned_row.amount == Decimal("500")


async def test_planned_item_map_category_unmatched_does_not_clone(db_session):
    """Категория самой позиции НЕ сопоставлена -> клонировать некуда,
    позиция остаётся без плановой (map=None, в .unmatched), а не клонируется
    в случайное место."""
    source = await _make_subsidy(db_session)
    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория без пары")
    db_session.add(src_cat)
    await db_session.flush()
    src_item = FeoPlannedItem(feo_category_id=src_cat.id, name="Позиция", amount=Decimal("100"))
    db_session.add(src_item)
    await db_session.commit()
    await db_session.refresh(src_item)

    category_map = {src_cat.id: None}  # категория не сопоставлена
    result = await build_planned_item_map(db_session, category_map)

    assert result.map[src_item.id] is None
    assert src_item.id in result.unmatched
    assert src_item.id not in result.cloned


async def test_planned_item_map_item_ids_restricts_scope(db_session):
    """item_ids ограничивает клонирование только нужными позициями — остальные
    несопоставленные позиции той же категории не трогаются вовсе (не висят в
    .map/.unmatched/.cloned), чтобы не раздувать план целевой субсидии клонами
    неиспользуемых строк (copy_into_subsidy.py передаёт сюда только id,
    реально встреченные у копируемых закупок/заявки)."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория")
    db_session.add(src_cat)
    await db_session.flush()
    tgt_cat = FeoCategory(subsidy_id=target.id, level=1, name="Категория")
    db_session.add(tgt_cat)
    await db_session.flush()

    used_item = FeoPlannedItem(feo_category_id=src_cat.id, name="Используется", amount=Decimal("1"))
    unused_item = FeoPlannedItem(feo_category_id=src_cat.id, name="Не используется", amount=Decimal("2"))
    db_session.add_all([used_item, unused_item])
    await db_session.commit()
    await db_session.refresh(used_item)
    await db_session.refresh(unused_item)

    category_map = {src_cat.id: tgt_cat.id}
    result = await build_planned_item_map(db_session, category_map, item_ids={used_item.id})

    assert used_item.id in result.map
    assert used_item.id in result.cloned
    assert unused_item.id not in result.map
    assert unused_item.id not in result.cloned
    assert unused_item.id not in result.unmatched


async def test_planned_item_map_shared_old_item_maps_to_one_new_item(db_session):
    """Старая плановая, на которую ссылаются И закупка, И заявка (авансовый
    отчёт) — одна и та же, встреченная дважды в item_ids — должна дать РОВНО
    одну новую плановую, не два клона (задание 07.10.2026, п.1)."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория")
    db_session.add(src_cat)
    await db_session.flush()
    tgt_cat = FeoCategory(subsidy_id=target.id, level=1, name="Категория")
    db_session.add(tgt_cat)
    await db_session.flush()

    shared_item = FeoPlannedItem(feo_category_id=src_cat.id, name="Общая плановая", amount=Decimal("10"))
    db_session.add(shared_item)
    await db_session.commit()
    await db_session.refresh(shared_item)

    category_map = {src_cat.id: tgt_cat.id}
    # item_ids как set — дубль id схлопывается сам по себе (set), но главное —
    # результат один и тот же new id для единственного old id.
    result = await build_planned_item_map(db_session, category_map, item_ids={shared_item.id, shared_item.id})

    assert len(result.cloned) == 1
    new_id = result.map[shared_item.id]
    all_cloned_rows = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == tgt_cat.id)
    )).scalars().all()
    assert len(all_cloned_rows) == 1
    assert all_cloned_rows[0].id == new_id


async def test_planned_item_map_two_different_old_items_same_name_clone_separately(db_session):
    """Баг прода 07.10.2026: 7 РАЗНЫХ старых плановых с одинаковым именем
    («Обработка заказа в пункте выдачи», каждая со своей суммой) склеились в
    ОДНУ новую — первая клонировалась, остальные «нашлись по имени» среди
    только что склонированных. ДВЕ разные старые с одним именем должны дать
    ДВЕ разные новые (каждая клонируется отдельно), не одну общую."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория")
    db_session.add(src_cat)
    await db_session.flush()
    tgt_cat = FeoCategory(subsidy_id=target.id, level=1, name="Категория")
    db_session.add(tgt_cat)
    await db_session.flush()

    item_a = FeoPlannedItem(feo_category_id=src_cat.id, name="Обработка заказа в пункте выдачи", amount=Decimal("111"))
    item_b = FeoPlannedItem(feo_category_id=src_cat.id, name="Обработка заказа в пункте выдачи", amount=Decimal("222"))
    db_session.add_all([item_a, item_b])
    await db_session.commit()
    await db_session.refresh(item_a)
    await db_session.refresh(item_b)

    category_map = {src_cat.id: tgt_cat.id}
    result = await build_planned_item_map(db_session, category_map, item_ids={item_a.id, item_b.id})

    new_a = result.map[item_a.id]
    new_b = result.map[item_b.id]
    assert new_a is not None and new_b is not None
    assert new_a != new_b
    assert item_a.id in result.cloned
    assert item_b.id in result.cloned

    rows = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == tgt_cat.id)
    )).scalars().all()
    assert len(rows) == 2
    amounts = sorted(r.amount for r in rows)
    assert amounts == [Decimal("111"), Decimal("222")]


async def test_planned_item_map_name_match_ignores_items_cloned_in_this_run(db_session):
    """Та же ловушка в другой форме: целевая категория УЖЕ содержит позицию с
    этим именем (найдена честно, снимок ДО прогона), а в этом же прогоне
    клонируется ДРУГАЯ старая с тем же именем (её целевой категории своей пары
    не было) — обе ссылки НЕ должны схлопнуться в одну: первая находит
    существующую (однозначно — ровно одна старая claim'ит её), вторая (другая
    старая, другая категория) клонируется отдельно."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    src_cat1 = FeoCategory(subsidy_id=source.id, level=1, name="Категория 1")
    src_cat2 = FeoCategory(subsidy_id=source.id, level=1, name="Категория 2")
    db_session.add_all([src_cat1, src_cat2])
    await db_session.flush()
    tgt_cat1 = FeoCategory(subsidy_id=target.id, level=1, name="Категория 1")
    tgt_cat2 = FeoCategory(subsidy_id=target.id, level=1, name="Категория 2")
    db_session.add_all([tgt_cat1, tgt_cat2])
    await db_session.flush()

    existing_tgt = FeoPlannedItem(feo_category_id=tgt_cat1.id, name="Общее имя", amount=Decimal("5"))
    db_session.add(existing_tgt)
    await db_session.commit()
    await db_session.refresh(existing_tgt)

    item1 = FeoPlannedItem(feo_category_id=src_cat1.id, name="Общее имя", amount=Decimal("5"))
    item2 = FeoPlannedItem(feo_category_id=src_cat2.id, name="Общее имя", amount=Decimal("9"))
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(item1)
    await db_session.refresh(item2)

    category_map = {src_cat1.id: tgt_cat1.id, src_cat2.id: tgt_cat2.id}
    result = await build_planned_item_map(db_session, category_map, item_ids={item1.id, item2.id})

    assert result.map[item1.id] == existing_tgt.id
    assert item1.id not in result.cloned
    new_item2_id = result.map[item2.id]
    assert new_item2_id is not None
    assert new_item2_id != existing_tgt.id
    assert item2.id in result.cloned


def test_normalize_name_collapses_whitespace_and_case():
    assert normalize_name("  Бензин   АИ-95 ") == normalize_name("бензин аи-95")


# --- duplicate detection -------------------------------------------------

async def test_duplicate_detection_finds_same_contractor_and_amount(db_session):
    target = await _make_subsidy(db_session)
    contractor = Contractor(name=f"ООО Ромашка {uuid.uuid4().hex[:6]}")
    db_session.add(contractor)
    await db_session.flush()

    existing = Purchase(
        subsidy_id=target.id, item_name="Уже есть", status="paid",
        contractor_id=contractor.id, contract_price=Decimal("777.00"),
    )
    db_session.add(existing)
    await db_session.commit()

    dup = await _find_duplicate(db_session, target.id, contractor.id, Decimal("777.00"))
    assert dup is not None
    assert dup.id == existing.id

    no_dup = await _find_duplicate(db_session, target.id, contractor.id, Decimal("1.00"))
    assert no_dup is None

    # Ни контрагента, ни суммы для сравнения — дубль не ищем (не с чем).
    assert await _find_duplicate(db_session, target.id, None, Decimal("777.00")) is None
    assert await _find_duplicate(db_session, target.id, contractor.id, None) is None


# --- copy_purchases(purchase_ids=...) filter ------------------------------

async def _build_subsidy_with_two_purchases(db_session) -> tuple[Subsidy, dict]:
    subsidy = await _make_subsidy(db_session)
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория")
    db_session.add(cat)
    await db_session.flush()

    contract1 = Contract(number="Д-1", contract_type="single", subsidy_id=subsidy.id, subject="Договор 1")
    contract2 = Contract(number="Д-2", contract_type="single", subsidy_id=subsidy.id, subject="Договор 2")
    db_session.add_all([contract1, contract2])
    await db_session.flush()

    p1 = Purchase(subsidy_id=subsidy.id, item_name="Закупка 1", status="paid",
                  feo_category_id=cat.id, contract_id=contract1.id, contract_price=Decimal("100"))
    p2 = Purchase(subsidy_id=subsidy.id, item_name="Закупка 2", status="paid",
                  feo_category_id=cat.id, contract_id=contract2.id, contract_price=Decimal("200"))
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    return subsidy, {"category_id": cat.id, "p1": p1.id, "p2": p2.id,
                      "contract1": contract1.id, "contract2": contract2.id}


async def test_purchase_ids_filter_copies_only_selected_with_their_contracts(db_session):
    source, ids = await _build_subsidy_with_two_purchases(db_session)
    target = await _make_subsidy(db_session)

    result = await copy_purchases(
        db_session, source.id, target.id,
        category_id_map={}, planned_item_id_map={},
        purchase_ids={ids["p1"]},
    )

    assert result.purchase_count == 1
    assert result.contract_count == 1  # только договор ВЫБРАННОЙ закупки, не оба

    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    assert len(purchases) == 1
    assert purchases[0].contract_price == Decimal("100")

    contracts = (await db_session.execute(
        select(Contract).where(Contract.subsidy_id == target.id)
    )).scalars().all()
    assert len(contracts) == 1
    assert contracts[0].number == "Д-1"


async def test_parent_purchase_outside_filter_is_detached_with_warning(db_session):
    source = await _make_subsidy(db_session)
    parent = Purchase(subsidy_id=source.id, item_name="Родитель (рамочный)", status="paid")
    db_session.add(parent)
    await db_session.flush()
    child = Purchase(subsidy_id=source.id, item_name="Ребёнок (заказ)", status="paid",
                     parent_purchase_id=parent.id)
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(parent)
    await db_session.refresh(child)

    target = await _make_subsidy(db_session)

    # Копируем только ребёнка — родитель вне выборки.
    result = await copy_purchases(
        db_session, source.id, target.id,
        category_id_map={}, planned_item_id_map={},
        purchase_ids={child.id},
    )

    assert result.purchase_count == 1
    new_purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    assert len(new_purchases) == 1
    assert new_purchases[0].parent_purchase_id is None
    assert any("родитель" in w.lower() for w in result.warnings)


async def test_copy_purchases_without_filter_copies_everything_as_before(db_session):
    """Регрессия: purchase_ids=None (умолчание) обязан копировать ВСЕ закупки
    субсидии и ВСЕ договоры субсидии, как до рефакторинга (см. test_subsidy_copy.py)."""
    source, ids = await _build_subsidy_with_two_purchases(db_session)
    target = await _make_subsidy(db_session)

    result = await copy_purchases(
        db_session, source.id, target.id,
        category_id_map={}, planned_item_id_map={},
    )

    assert result.purchase_count == 2
    assert result.contract_count == 2


# --- copy_wishes -----------------------------------------------------------

async def test_copy_wishes_copies_wish_and_items_without_approvals(db_session):
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)

    src_cat = FeoCategory(subsidy_id=source.id, level=1, name="Категория")
    db_session.add(src_cat)
    await db_session.flush()
    tgt_cat = FeoCategory(subsidy_id=target.id, level=1, name="Категория")
    db_session.add(tgt_cat)
    await db_session.flush()

    org = (await db_session.execute(select(Subsidy.org_id).where(Subsidy.id == target.id))).scalar_one_or_none()

    wish = Wish(org_id=org or 1, title="Заявка-тест", subsidy_id=source.id,
               feo_category_id=src_cat.id, status="submitted")
    db_session.add(wish)
    await db_session.flush()
    item = WishItem(wish_id=wish.id, item_name="Товар", feo_category_id=src_cat.id)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(wish)

    category_map = {src_cat.id: tgt_cat.id}
    result = await copy_wishes(db_session, {wish.id}, target.id, category_map, {})

    assert result.wish_count == 1
    new_id = result.wish_id_map[wish.id]
    new_wish = await db_session.get(Wish, new_id)
    assert new_wish.subsidy_id == target.id
    assert new_wish.feo_category_id == tgt_cat.id
    assert new_wish.purchase_id is None
    assert new_wish.status == "submitted"

    new_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == new_id)
    )).scalars().all()
    assert len(new_items) == 1
    assert new_items[0].feo_category_id == tgt_cat.id


async def test_copy_wishes_rejected_status_becomes_submitted(db_session):
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    org = (await db_session.execute(select(Subsidy.org_id).where(Subsidy.id == target.id))).scalar_one_or_none()

    wish = Wish(org_id=org or 1, title="Отклонённая заявка", subsidy_id=source.id,
               status="rejected", rejection_reason="тест")
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    result = await copy_wishes(db_session, {wish.id}, target.id, {}, {})
    new_wish = await db_session.get(Wish, result.wish_id_map[wish.id])
    assert new_wish.status == "submitted"
    assert new_wish.rejection_reason is None


# --- relink_wish_and_purchase_copies ----------------------------------------

async def test_relink_reconnects_wish_and_purchase_copies(db_session):
    """Авансовый отчёт: заявка и её закупка ссылаются друг на друга
    (Wish.purchase_id / Purchase.wish_id) и позиция закупки — на строку заявки
    (PurchaseItem.wish_item_id). Копируем ОБЕ в одном прогоне -> связи между
    КОПИЯМИ должны восстановиться (задание владельца 07.10.2026, п.2)."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    org = (await db_session.execute(select(Subsidy.org_id).where(Subsidy.id == target.id))).scalar_one_or_none()

    purchase = Purchase(subsidy_id=source.id, item_name="Закупка-авансовый", status="paid",
                        contract_price=Decimal("300"))
    db_session.add(purchase)
    await db_session.flush()
    wish = Wish(org_id=org or 1, title="Авансовый отчёт", subsidy_id=source.id,
               status="submitted", purchase_id=purchase.id, source="advance_report")
    db_session.add(wish)
    await db_session.flush()
    purchase.wish_id = wish.id
    wish_item = WishItem(wish_id=wish.id, item_name="Позиция заявки")
    db_session.add(wish_item)
    await db_session.flush()
    purchase_item = PurchaseItem(purchase_id=purchase.id, item_name="Позиция закупки",
                                 quantity=Decimal("1"), unit_price=Decimal("300"), total_price=Decimal("300"),
                                 wish_item_id=wish_item.id)
    db_session.add(purchase_item)
    await db_session.commit()
    await db_session.refresh(purchase)
    await db_session.refresh(wish)

    purchase_copy = await copy_purchases(
        db_session, source.id, target.id, category_id_map={}, planned_item_id_map={},
        purchase_ids={purchase.id},
    )
    wish_copy = await copy_wishes(db_session, {wish.id}, target.id, {}, {})

    # До relink — копии НЕ связаны (как при раздельном копировании).
    new_purchase_before = await db_session.get(Purchase, purchase_copy.purchase_id_map[purchase.id])
    new_wish_before = await db_session.get(Wish, wish_copy.wish_id_map[wish.id])
    assert new_purchase_before.wish_id is None
    assert new_wish_before.purchase_id is None

    await relink_wish_and_purchase_copies(
        db_session,
        purchase_id_map=purchase_copy.purchase_id_map,
        wish_id_map=wish_copy.wish_id_map,
        wish_item_id_map=wish_copy.wish_item_id_map,
        purchase_item_id_map=purchase_copy.item_id_map,
    )

    new_purchase = await db_session.get(Purchase, purchase_copy.purchase_id_map[purchase.id])
    new_wish = await db_session.get(Wish, wish_copy.wish_id_map[wish.id])
    assert new_purchase.wish_id == new_wish.id
    assert new_wish.purchase_id == new_purchase.id

    new_item = await db_session.get(PurchaseItem, purchase_copy.item_id_map[purchase_item.id])
    new_wish_item_id = wish_copy.wish_item_id_map[wish_item.id]
    assert new_item.wish_item_id == new_wish_item_id

    # Оригиналы не тронуты.
    await db_session.refresh(purchase)
    await db_session.refresh(wish)
    assert purchase.wish_id == wish.id
    assert wish.purchase_id == purchase.id


async def test_relink_leaves_none_when_only_one_side_copied(db_session):
    """Копируется только закупка (без заявки) -> связь остаётся None, как и
    было (relink не имеет второй стороны, за которую можно зацепиться)."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)
    org = (await db_session.execute(select(Subsidy.org_id).where(Subsidy.id == target.id))).scalar_one_or_none()

    purchase = Purchase(subsidy_id=source.id, item_name="Закупка одна", status="paid")
    db_session.add(purchase)
    await db_session.flush()
    wish = Wish(org_id=org or 1, title="Заявка без копии", subsidy_id=source.id,
               status="submitted", purchase_id=purchase.id)
    db_session.add(wish)
    await db_session.flush()
    purchase.wish_id = wish.id
    await db_session.commit()

    purchase_copy = await copy_purchases(
        db_session, source.id, target.id, category_id_map={}, planned_item_id_map={},
        purchase_ids={purchase.id},
    )
    # wish НЕ копируем в этом прогоне.
    warnings = await relink_wish_and_purchase_copies(
        db_session,
        purchase_id_map=purchase_copy.purchase_id_map,
        wish_id_map={},
        wish_item_id_map={},
        purchase_item_id_map=purchase_copy.item_id_map,
    )
    assert warnings == []
    new_purchase = await db_session.get(Purchase, purchase_copy.purchase_id_map[purchase.id])
    assert new_purchase.wish_id is None
