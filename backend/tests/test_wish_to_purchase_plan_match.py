# -*- coding: utf-8 -*-
"""Прод-инцидент (субсидия «Абхазия», id 68, 08.10.2026): заявка №67 при
превращении в закупку создавала позиции БЕЗ собственной feo_category_id →
auto_assign_planned_items искала существующую плановую позицию ТОЛЬКО внутри
категории-фолбэка «Не определена», не находила и заводила НОВУЮ auto_created
FeoPlannedItem — хотя в ФЭО уже была строка с тем же именем/суммой в другой
категории. План субсидии задвоился (186 лишних позиций на проде).

Фикс — app.services.plan_autoassign.auto_assign_planned_items теперь ищет
такую позицию ПО ВСЕЙ субсидии (правило — app.services.feo_plan_duplicate_match,
ПРАВИЛО №6) перед тем, как завести дубль. Тест вызывает сам сервис напрямую
(минуя FastAPI/HTTP, по образцу test_feo_item_write_wish_path.py) — он и есть
общий код для пути «заявка → /convert → закупка» (см.
app/routers/wish_convert.py:252-255)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.wish import Wish
from app.models.wish_item import WishItem


async def _make_subsidy_with_categories(db_session, org_id):
    subsidy = Subsidy(
        name=f"TestAbkhaziaDup-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id,
    )
    db_session.add(subsidy)
    await db_session.flush()

    real_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Транспорт")
    fallback_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Не определена")
    db_session.add_all([real_cat, fallback_cat])
    await db_session.flush()
    return subsidy, real_cat, fallback_cat


@pytest.mark.asyncio
async def test_wish_item_matches_existing_feo_plan_by_name_and_amount(db_session, test_org):
    """Позиция заявки без собственной feo_category_id (падает на fallback
    «Не определена») находит СУЩЕСТВУЮЩУЮ плановую позицию ФЭО по имени+сумме
    в другой категории субсидии — новая auto_created позиция НЕ создаётся,
    позиция заявки привязывается к найденной."""
    subsidy, real_cat, fallback_cat = await _make_subsidy_with_categories(db_session, test_org.id)

    # Настоящая строка плана ФЭО, заведённая импортом (не auto_created),
    # в категории "Транспорт" — ровно как 189 позиций ФЭО на проде.
    real_fpi = FeoPlannedItem(
        feo_category_id=real_cat.id, name="Моторное судно РУСБОТ 60НС",
        quantity=Decimal("1"), amount=Decimal("4484400.00"),
        is_active=True, auto_created=False,
    )
    db_session.add(real_fpi)
    await db_session.flush()

    wish = Wish(
        title="Заявка №67", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=fallback_cat.id,
    )
    db_session.add(wish)
    await db_session.flush()

    # Позиция заявки — БЕЗ собственной feo_category_id (точно как на проде):
    # эффективная категория берётся из fallback_category_id ("Не определена").
    wish_item = WishItem(
        wish_id=wish.id, item_name="Моторное судно РУСБОТ 60НС",
        quantity=Decimal("1"), unit_price=Decimal("4484400.00"),
        total_price=Decimal("4484400.00"),
    )
    db_session.add(wish_item)
    await db_session.commit()
    await db_session.refresh(wish_item)

    before_count = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_([real_cat.id, fallback_cat.id]))
    )).scalars().all()
    assert len(before_count) == 1, "перед вызовом в субсидии должна быть только исходная плановая позиция"

    from app.services.plan_autoassign import auto_assign_planned_items
    await auto_assign_planned_items(
        [wish_item], fallback_cat.id, db_session, note="заявкой №67 (/convert)",
    )
    await db_session.commit()
    await db_session.refresh(wish_item)

    # Никакой новой FeoPlannedItem не появилось.
    all_items = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_([real_cat.id, fallback_cat.id]))
    )).scalars().all()
    assert len(all_items) == 1, (
        f"ожидалась ровно 1 плановая позиция (без дубля в «Не определена»), "
        f"получено {len(all_items)}: {[(i.id, i.name, i.feo_category_id, i.auto_created) for i in all_items]}"
    )

    # Позиция заявки привязана к НАЙДЕННОЙ (не-auto) позиции, а не к новой.
    assert wish_item.feo_planned_item_id == real_fpi.id
    # И переехала в её настоящую категорию ("Транспорт"), а не осталась в "Не определена".
    assert wish_item.feo_category_id == real_cat.id


@pytest.mark.asyncio
async def test_wish_item_without_match_still_creates_auto_item_in_fallback(db_session, test_org):
    """Контроль: если подходящей позиции ФЭО нигде в субсидии нет — старое
    поведение не регрессирует, auto_created позиция заводится как раньше."""
    subsidy, real_cat, fallback_cat = await _make_subsidy_with_categories(db_session, test_org.id)

    wish = Wish(
        title="Заявка без пары", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=fallback_cat.id,
    )
    db_session.add(wish)
    await db_session.flush()

    wish_item = WishItem(
        wish_id=wish.id, item_name="Совершенно новая позиция без пары",
        quantity=Decimal("1"), unit_price=Decimal("777.00"), total_price=Decimal("777.00"),
    )
    db_session.add(wish_item)
    await db_session.commit()
    await db_session.refresh(wish_item)

    from app.services.plan_autoassign import auto_assign_planned_items
    await auto_assign_planned_items(
        [wish_item], fallback_cat.id, db_session, note="заявкой (без пары)",
    )
    await db_session.commit()
    await db_session.refresh(wish_item)

    created = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == fallback_cat.id)
    )).scalars().all()
    assert len(created) == 1
    assert created[0].auto_created is True
    assert wish_item.feo_planned_item_id == created[0].id


@pytest.mark.asyncio
async def test_wish_item_same_amount_different_name_does_not_match(db_session, test_org):
    """Правка 08.10.2026 (координатор): живой путь (auto_assign_planned_items)
    НЕ должен склеивать по одной только сумме — иначе две РАЗНЫЕ позиции с
    одинаковой суммой (напр. две закупки по 100 000 ₽) ложно слились бы без
    проверки имени (урок проекта «дедуп только точный»). Позиция заявки с
    ДРУГИМ именем, но той же суммой, что и существующая плановая ФЭО, — пара
    НЕ берётся, заводится обычная auto_created позиция, как раньше."""
    subsidy, real_cat, fallback_cat = await _make_subsidy_with_categories(db_session, test_org.id)

    real_fpi = FeoPlannedItem(
        feo_category_id=real_cat.id, name="Катер",
        quantity=Decimal("1"), amount=Decimal("100000.00"),
        is_active=True, auto_created=False,
    )
    db_session.add(real_fpi)
    await db_session.flush()

    wish = Wish(
        title="Заявка с другим именем, той же суммой", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=fallback_cat.id,
    )
    db_session.add(wish)
    await db_session.flush()

    wish_item = WishItem(
        wish_id=wish.id, item_name="Набор инструментов",
        quantity=Decimal("1"), unit_price=Decimal("100000.00"), total_price=Decimal("100000.00"),
    )
    db_session.add(wish_item)
    await db_session.commit()
    await db_session.refresh(wish_item)

    from app.services.plan_autoassign import auto_assign_planned_items
    await auto_assign_planned_items(
        [wish_item], fallback_cat.id, db_session, note="заявкой (та же сумма, другое имя)",
    )
    await db_session.commit()
    await db_session.refresh(wish_item)

    # Пара по сумме НЕ взята — real_fpi не тронута, в fallback_cat заведена
    # СВОЯ новая auto_created позиция (старое поведение, без регресса).
    assert wish_item.feo_planned_item_id != real_fpi.id
    created = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == fallback_cat.id)
    )).scalars().all()
    assert len(created) == 1
    assert created[0].auto_created is True
    assert wish_item.feo_planned_item_id == created[0].id
