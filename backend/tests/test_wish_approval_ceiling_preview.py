"""Предпросмотр жёсткого потолка ФЭО ДО нажатия «Согласовать» на заявке
(владелец, 19.10.2026, решение по жёсткому потолку субсидии, п.1 задания
«заметнее»): согласующий обязан увидеть сумму превышения ДО решения.

Проверяет app.services.wish_approval_ceiling_preview.preview_wish_approval_ceiling:
  (а) заявка, которая после согласования вытолкнет план субсидии ВЫШЕ потолка
      ФЭО — applicable=True, over_amount > 0, число совпадает с ручным
      подсчётом (plan_before + сумма позиций заявки - ceiling);
  (б) заявка, которая НЕ выталкивает план за потолок — applicable=True,
      over_amount == 0;
  (в) сухой прогон НЕ оставляет следов в БД (нет Purchase/новой
      FeoPlannedItem по этой заявке после вызова preview — SAVEPOINT реально
      откатился).

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.feo_planned_item import FeoPlannedItem
from app.services.wish_approval_ceiling_preview import preview_wish_approval_ceiling


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"CeilingPreview-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount, name="Позиция плана"):
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal("1"),
        unit="шт",
        amount=Decimal(str(amount)),
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_wish_with_item(db_session, org_id, subsidy_id, feo_category_id, item_amount):
    wish = Wish(
        org_id=org_id, title="Заявка-превью потолка", subsidy_id=subsidy_id,
        feo_category_id=feo_category_id, status="submitted",
    )
    db_session.add(wish)
    await db_session.flush()
    item = WishItem(
        wish_id=wish.id, item_name="Новая позиция заявки", feo_category_id=feo_category_id,
        quantity=Decimal("1"), unit="шт", unit_price=Decimal(str(item_amount)),
        total_price=Decimal(str(item_amount)),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(wish)
    # items — lazy="selectin", перечитываем, чтобы wish.items был заполнен сразу
    # (ORM-объект wish выше создан в этой же сессии ДО flush позиции).
    await db_session.refresh(wish, attribute_names=["items"])
    return wish


@pytest.mark.asyncio
async def test_preview_applicable_and_over_ceiling(db_session, test_org, test_admin_user):
    """(а) ФЭО-бюджет (потолок) 100, уже запланировано 90 — заявка добавляет
    ещё 20 новой (неприкреплённой) позиции: план станет 110 > 100, превышение
    10 (с точностью до округления автозаведения плановой позиции)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Единственная категория", budget=Decimal("100"))
    await _make_planned_item(db_session, cat.id, amount=90)
    wish = await _make_wish_with_item(db_session, test_org.id, subsidy.id, cat.id, item_amount=20)

    result = await preview_wish_approval_ceiling(db_session, wish, test_admin_user)

    assert result["applicable"] is True, result
    assert result["subsidy_id"] == subsidy.id
    assert result["ceiling"] == pytest.approx(100.0, abs=0.01)
    assert result["total_plan_before"] == pytest.approx(90.0, abs=0.01)
    assert result["total_plan_after"] == pytest.approx(110.0, abs=0.01)
    assert result["over_amount"] == pytest.approx(10.0, abs=0.01)


@pytest.mark.asyncio
async def test_preview_applicable_but_within_ceiling(db_session, test_org, test_admin_user):
    """(б) Потолок 1000, план до заявки 0, заявка добавляет 20 — план станет
    20 <= 1000, over_amount == 0 (ничего не стоит)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Категория с запасом", budget=Decimal("1000"))
    wish = await _make_wish_with_item(db_session, test_org.id, subsidy.id, cat.id, item_amount=20)

    result = await preview_wish_approval_ceiling(db_session, wish, test_admin_user)

    assert result["applicable"] is True, result
    assert result["over_amount"] == 0.0


@pytest.mark.asyncio
async def test_preview_rolls_back_dry_run(db_session, test_org, test_admin_user):
    """(в) Превью не должно оставлять следов — ни Purchase, ни новой
    FeoPlannedItem по этой заявке в БД после вызова (SAVEPOINT откатился)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Категория", budget=Decimal("100"))
    await _make_planned_item(db_session, cat.id, amount=90)
    wish = await _make_wish_with_item(db_session, test_org.id, subsidy.id, cat.id, item_amount=20)

    wish_id = wish.id  # читаем ДО сухого прогона — после nested.rollback()
    # атрибуты ORM-объекта wish могут протухнуть (expired), а их ленивая
    # подгрузка вне greenlet-контекста теста падает MissingGreenlet — это
    # особенность теста, не бага предпросмотра, поэтому id сохраняем заранее.
    before_items = (await db_session.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id == cat.id)
    )).scalars().all()

    result = await preview_wish_approval_ceiling(db_session, wish, test_admin_user)
    assert result["applicable"] is True, result

    purchases_after = (await db_session.execute(
        select(Purchase.id).where(Purchase.wish_id == wish_id)
    )).scalars().all()
    assert purchases_after == [], "Сухой прогон не обязан создавать реальную закупку"

    items_after = (await db_session.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id == cat.id)
    )).scalars().all()
    assert sorted(items_after) == sorted(before_items), (
        "Сухой прогон не обязан оставлять новую плановую позицию в БД — SAVEPOINT должен откатиться"
    )

    wish_after = await db_session.get(Wish, wish_id)
    assert wish_after.purchase_id is None, "wish.purchase_id не должен устанавливаться сухим прогоном"
