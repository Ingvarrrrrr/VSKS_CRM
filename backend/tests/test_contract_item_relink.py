"""Прод-инцидент (сессия 2026-09-01, см. app/services/contract_item_link.py):
PUT закупки удаляет+пересоздаёт PurchaseItem под новыми id, что рвёт
ContractItem.source_item_id через ON DELETE SET NULL. Эти тесты покрывают
и главный регресс (пересохранение заявки не должно ронять связь), и сам
матчер relink_contract_items изолированно (по стилю
test_contract_item_model.py — db_session + фабрики make_purchase/
make_contract_item из conftest.py).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.contract_item import ContractItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.routers.purchases import update_purchase
from app.schemas.schemas import PurchaseCreate, PurchaseItemCreate
from app.services.contract_item_link import relink_contract_items


async def _make_feo_category(db_session, name="Тестовая категория"):
    """Создаёт минимальную живую пару Subsidy+FeoCategory — feo_category_id
    у PurchaseItem/FeoCategory реальный FK, тесты гоняются против настоящего
    Postgres (см. conftest.py), фиктивный id упал бы на INSERT."""
    subsidy = Subsidy(name=f"Test subsidy {name}", year=2026, budget=0)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name=name)
    db_session.add(cat)
    await db_session.flush()
    return cat


@pytest.mark.asyncio
async def test_resave_purchase_same_items_preserves_source_item_id(db_session, test_user):
    """Главный регресс-тест: PUT закупки с ТЕМИ ЖЕ позициями не должен рвать
    ContractItem.source_item_id — после сохранения ссылки указывают на НОВЫЕ
    id и ведут к ТОЙ ЖЕ feo_category_id, что и раньше."""
    cat = await _make_feo_category(db_session, "Канцелярия")

    p = Purchase(status="planned", item_type="goods", item_name="Test purchase")
    db_session.add(p)
    await db_session.flush()
    pi1 = PurchaseItem(purchase_id=p.id, item_name="Товар А", quantity=Decimal("2"),
                        unit="шт", unit_price=Decimal("100"), total_price=Decimal("200"),
                        feo_category_id=cat.id)
    pi2 = PurchaseItem(purchase_id=p.id, item_name="Товар Б", quantity=Decimal("3"),
                        unit="шт", unit_price=Decimal("50"), total_price=Decimal("150"),
                        feo_category_id=cat.id)
    db_session.add_all([pi1, pi2])
    await db_session.flush()
    ci1 = ContractItem(purchase_id=p.id, source_item_id=pi1.id, name="Товар А",
                        quantity=Decimal("2"), unit="шт", unit_price=Decimal("100"),
                        total=Decimal("200"))
    ci2 = ContractItem(purchase_id=p.id, source_item_id=pi2.id, name="Товар Б",
                        quantity=Decimal("3"), unit="шт", unit_price=Decimal("50"),
                        total=Decimal("150"))
    db_session.add_all([ci1, ci2])
    await db_session.commit()
    old_pi1_id, old_pi2_id = pi1.id, pi2.id

    payload = PurchaseCreate(items=[
        PurchaseItemCreate(item_name="Товар А", quantity=Decimal("2"), unit="шт",
                            unit_price=Decimal("100"), total_price=Decimal("200"),
                            feo_category_id=cat.id),
        PurchaseItemCreate(item_name="Товар Б", quantity=Decimal("3"), unit="шт",
                            unit_price=Decimal("50"), total_price=Decimal("150"),
                            feo_category_id=cat.id),
    ])
    await update_purchase(pid=p.id, data=payload, admin_override=False,
                           db=db_session, current_user=test_user)

    # PurchaseItem id-шники ДОЛЖНЫ были смениться (PUT удаляет и пересоздаёт).
    new_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert len(new_items) == 2
    new_ids = {it.id for it in new_items}
    assert old_pi1_id not in new_ids
    assert old_pi2_id not in new_ids

    ci_rows = (await db_session.execute(
        select(ContractItem).where(ContractItem.purchase_id == p.id)
    )).scalars().all()
    assert len(ci_rows) == 2
    for ci in ci_rows:
        assert ci.source_item_id is not None, f"source_item_id рухнул в NULL у ContractItem {ci.name!r}"
        matched_pi = next((it for it in new_items if it.id == ci.source_item_id), None)
        assert matched_pi is not None, "source_item_id указывает не на позицию этой закупки"
        assert matched_pi.item_name == ci.name
        # Ключевая проверка: категория ФЭО восстановлена (documents.py читает
        # её ИСКЛЮЧИТЕЛЬНО через source_item_id → PurchaseItem.feo_category_id).
        assert matched_pi.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_relink_by_exact_name(db_session, make_purchase, make_purchase_with_items, make_contract_item):
    """relink по точному совпадению item_name восстанавливает связь."""
    p = await make_purchase_with_items(items_count=1, item_total=Decimal("300"))
    pi = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalar_one()
    ci = await make_contract_item(
        purchase_id=p.id, name=pi.item_name, quantity=Decimal("1"),
        unit_price=Decimal("300"), total=Decimal("300"), source_item_id=None,
    )
    relinked = await relink_contract_items(db_session, p.id)
    assert relinked == 1
    # relink_contract_items коммит не делает (это ответственность вызывающего) —
    # flush перед refresh, иначе refresh() отбросит несохранённое изменение.
    await db_session.flush()
    await db_session.refresh(ci)
    assert ci.source_item_id == pi.id


@pytest.mark.asyncio
async def test_relink_ambiguous_name_stays_null(db_session, make_purchase, make_contract_item):
    """Две плановые позиции с ОДИНАКОВЫМ именем, но РАЗНЫМИ feo_category_id —
    связь НЕ восстанавливается, чужая категория не подставляется (владелец:
    честное «не определена» лучше подмены — см. documents.py:920-924)."""
    cat_a = await _make_feo_category(db_session, "Категория А")
    cat_b = await _make_feo_category(db_session, "Категория Б")
    p = await make_purchase()
    pi_a = PurchaseItem(purchase_id=p.id, item_name="Одинаковое имя", quantity=Decimal("1"),
                         unit="шт", unit_price=Decimal("100"), total_price=Decimal("100"),
                         feo_category_id=cat_a.id)
    pi_b = PurchaseItem(purchase_id=p.id, item_name="Одинаковое имя", quantity=Decimal("1"),
                         unit="шт", unit_price=Decimal("100"), total_price=Decimal("100"),
                         feo_category_id=cat_b.id)
    db_session.add_all([pi_a, pi_b])
    await db_session.commit()

    ci = await make_contract_item(
        purchase_id=p.id, name="Одинаковое имя", quantity=Decimal("1"),
        unit_price=Decimal("100"), total=Decimal("100"), source_item_id=None,
    )
    relinked = await relink_contract_items(db_session, p.id)
    assert relinked == 0
    await db_session.flush()
    await db_session.refresh(ci)
    assert ci.source_item_id is None


@pytest.mark.asyncio
async def test_relink_positional_fallback_equal_counts(db_session, make_purchase, make_contract_item):
    """Позиционный 1↔1 (Pass 4): разные имена, равное количество плановых и
    договорных позиций, ничего ещё не занято — связывает по ORDER BY id."""
    p = await make_purchase()
    pi1 = PurchaseItem(purchase_id=p.id, item_name="Позиция плана 1", quantity=Decimal("1"),
                        unit="шт", unit_price=Decimal("10"), total_price=Decimal("10"))
    pi2 = PurchaseItem(purchase_id=p.id, item_name="Позиция плана 2", quantity=Decimal("2"),
                        unit="шт", unit_price=Decimal("20"), total_price=Decimal("40"))
    db_session.add_all([pi1, pi2])
    await db_session.commit()

    ci1 = await make_contract_item(purchase_id=p.id, name="Совсем другое имя 1",
                                    quantity=Decimal("9"), unit_price=Decimal("9"),
                                    total=Decimal("81"), source_item_id=None)
    ci2 = await make_contract_item(purchase_id=p.id, name="Совсем другое имя 2",
                                    quantity=Decimal("8"), unit_price=Decimal("8"),
                                    total=Decimal("64"), source_item_id=None)

    relinked = await relink_contract_items(db_session, p.id)
    assert relinked == 2
    await db_session.flush()
    await db_session.refresh(ci1)
    await db_session.refresh(ci2)
    assert ci1.source_item_id == pi1.id
    assert ci2.source_item_id == pi2.id


@pytest.mark.asyncio
async def test_relink_split_contract_item_pass0_preserves_shared_source(db_session, test_user):
    """D-05 (splitContractRow, PurchaseItemsEditor.vue:1455): договорная позиция
    разбита на ДВЕ строки с ОДНИМ И ТЕМ ЖЕ source_item_id (легальное состояние,
    покрыто e2e/27-contract-items.spec.ts:78). PUT закупки пересоздаёт плановые
    позиции под новыми id — Pass 0 (id_map) обязан восстановить связь ОБЕИМ
    половинам на общую новую плановую позицию, а не только первой."""
    cat = await _make_feo_category(db_session, "Канцелярия")

    p = Purchase(status="planned", item_type="goods", item_name="Test purchase")
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(purchase_id=p.id, item_name="Товар А", quantity=Decimal("4"),
                       unit="шт", unit_price=Decimal("100"), total_price=Decimal("400"),
                       feo_category_id=cat.id)
    db_session.add(pi)
    await db_session.flush()
    # Разбитая договорная позиция: обе половины ссылаются на одну и ту же
    # плановую позицию, quantity/total у них разные (в этом смысл разбиения).
    ci1 = ContractItem(purchase_id=p.id, source_item_id=pi.id, name="Товар А",
                        quantity=Decimal("2"), unit="шт", unit_price=Decimal("100"),
                        total=Decimal("200"))
    ci2 = ContractItem(purchase_id=p.id, source_item_id=pi.id, name="Товар А",
                        quantity=Decimal("2"), unit="шт", unit_price=Decimal("100"),
                        total=Decimal("200"))
    db_session.add_all([ci1, ci2])
    await db_session.commit()
    old_pi_id = pi.id

    payload = PurchaseCreate(items=[
        PurchaseItemCreate(item_name="Товар А", quantity=Decimal("4"), unit="шт",
                            unit_price=Decimal("100"), total_price=Decimal("400"),
                            feo_category_id=cat.id),
    ])
    await update_purchase(pid=p.id, data=payload, admin_override=False,
                           db=db_session, current_user=test_user)

    new_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert len(new_items) == 1
    new_pi = new_items[0]
    assert new_pi.id != old_pi_id

    ci_rows = (await db_session.execute(
        select(ContractItem).where(ContractItem.purchase_id == p.id)
    )).scalars().all()
    assert len(ci_rows) == 2
    for ci in ci_rows:
        assert ci.source_item_id == new_pi.id, (
            f"обе половины разбитой позиции {ci.name!r} должны указывать "
            f"на общую новую плановую позицию"
        )
    assert new_pi.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_relink_split_contract_item_by_name_no_id_map(db_session, make_purchase):
    """D-05 без id_map (Pass 1/2 по имени): source_item_id у ОБЕИХ половин
    разбитой позиции уже NULL, старый id физически утрачен — единственный
    ориентир - совпадающее имя. Единственная плановая позиция с этим именем
    не является неоднозначностью со стороны плана — обе половины обязаны
    получить её как общего родителя."""
    cat = await _make_feo_category(db_session, "Канцелярия")
    p = await make_purchase()
    pi = PurchaseItem(purchase_id=p.id, item_name="Почётная грамота", quantity=Decimal("4"),
                       unit="шт", unit_price=Decimal("100"), total_price=Decimal("400"),
                       feo_category_id=cat.id)
    db_session.add(pi)
    await db_session.commit()

    ci1 = ContractItem(purchase_id=p.id, source_item_id=None, name="Почётная грамота",
                        quantity=Decimal("2"), unit="шт", unit_price=Decimal("100"),
                        total=Decimal("200"))
    ci2 = ContractItem(purchase_id=p.id, source_item_id=None, name="Почётная грамота",
                        quantity=Decimal("2"), unit="шт", unit_price=Decimal("100"),
                        total=Decimal("200"))
    db_session.add_all([ci1, ci2])
    await db_session.commit()

    relinked = await relink_contract_items(db_session, p.id)
    assert relinked == 2
    await db_session.flush()
    await db_session.refresh(ci1)
    await db_session.refresh(ci2)
    assert ci1.source_item_id == pi.id
    assert ci2.source_item_id == pi.id


@pytest.mark.asyncio
async def test_relink_never_crosses_purchases(db_session, make_purchase, make_contract_item):
    """relink никогда не связывает с PurchaseItem чужой закупки — даже если
    имя совпадает буквально с позицией из ДРУГОЙ закупки."""
    p_a = await make_purchase()
    p_b = await make_purchase()

    # Позиция плана в закупке B с именем, которое совпадает с договорной
    # позицией закупки A. У самой закупки A такой плановой позиции нет.
    pi_b = PurchaseItem(purchase_id=p_b.id, item_name="Общее имя", quantity=Decimal("1"),
                         unit="шт", unit_price=Decimal("100"), total_price=Decimal("100"))
    db_session.add(pi_b)
    await db_session.commit()

    ci_a = await make_contract_item(
        purchase_id=p_a.id, name="Общее имя", quantity=Decimal("1"),
        unit_price=Decimal("100"), total=Decimal("100"), source_item_id=None,
    )

    relinked = await relink_contract_items(db_session, p_a.id)
    assert relinked == 0
    await db_session.flush()
    await db_session.refresh(ci_a)
    assert ci_a.source_item_id is None, "договорная позиция закупки A не должна связаться с позицией закупки B"
