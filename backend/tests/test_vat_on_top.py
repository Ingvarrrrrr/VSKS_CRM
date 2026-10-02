# -*- coding: utf-8 -*-
"""НДС «в цене» или «сверху» при вводе цены позиции (владелец, 02.10.2026,
план .planning/quick/2026-10-02-vat-on-top/PLAN.md).

Покрывает:
  - item_amounts.line_total/vat_included_amount/effective_vat_on_top — формулы
    владельца (10 × 100 при 22% сверху = 1220,00; «в цене» = 1000; НДС «в т.ч.»
    от 1220 = 220,00, от 1000 = 180,33; ставка не указана → 1000);
  - per_item: флаг строки перебивает флаг шапки, null наследует флаг шапки;
  - PATCH одной позиции закупки с vat_on_top=true даёт total_price с надбавкой;
  - конвертация заявки в закупку переносит tz_vat_on_top/vat_on_top;
  - qty_price_check не ругается на расхождение, когда флаг учтён.
"""
from decimal import Decimal

import pytest

from app.services.item_amounts import (
    line_total,
    vat_included_amount,
    effective_vat_on_top,
    effective_vat_rate,
)
from app.services.qty_price_check import check_qty_price_sum


# ---------------------------------------------------------------------------
# Формулы — offline, числа владельца
# ---------------------------------------------------------------------------

def test_line_total_on_top_owner_example():
    """10 × 100 при 22% сверху = 1 220,00."""
    assert line_total(Decimal("10"), Decimal("100"), rate="22%", on_top=True) == Decimal("1220.00")


def test_line_total_in_price_unchanged():
    """«В цене» (on_top=False, умолчание) — сумма без надбавки = 1 000."""
    assert line_total(Decimal("10"), Decimal("100")) == Decimal("1000.00")
    assert line_total(Decimal("10"), Decimal("100"), rate="22%", on_top=False) == Decimal("1000.00")


def test_line_total_on_top_without_rate_falls_back_to_plain():
    """Ставка не указана/«Без НДС»/«ещё не знаю» → БЕЗ надбавки, итог 1 000."""
    assert line_total(Decimal("10"), Decimal("100"), rate=None, on_top=True) == Decimal("1000.00")
    assert line_total(Decimal("10"), Decimal("100"), rate="Без НДС", on_top=True) == Decimal("1000.00")
    assert line_total(Decimal("10"), Decimal("100"), rate="", on_top=True) == Decimal("1000.00")


def test_vat_included_amount_from_on_top_total():
    """НДС «в т.ч.» от суммы со «сверху» (1 220, 22%) = 220,00 — то есть ставка
    применяется к сумме, которая её УЖЕ несёт (1220 × 22/122 = 220)."""
    assert vat_included_amount(Decimal("1220"), "22%") == Decimal("220.00")


def test_vat_included_amount_from_in_price_total():
    """НДС «в т.ч.» от суммы «в цене» (1 000, 22%) = 180,33 (не 220 — та же
    сумма 1000 трактуется как УЖЕ включающая налог, другая база)."""
    assert vat_included_amount(Decimal("1000"), "22%") == Decimal("180.33")


def test_vat_included_amount_no_rate_is_zero():
    assert vat_included_amount(Decimal("1000"), None) == Decimal("0")
    assert vat_included_amount(Decimal("1000"), "Без НДС") == Decimal("0")


# ---------------------------------------------------------------------------
# effective_vat_on_top — per_item строка перебивает шапку, null наследует
# ---------------------------------------------------------------------------

def test_effective_vat_on_top_uniform_always_header():
    assert effective_vat_on_top(True, False, "uniform") is False
    assert effective_vat_on_top(None, True, "uniform") is True
    assert effective_vat_on_top(False, True, "uniform") is True  # uniform игнорирует флаг строки


def test_effective_vat_on_top_per_item_row_overrides_header():
    assert effective_vat_on_top(True, False, "per_item") is True
    assert effective_vat_on_top(False, True, "per_item") is False


def test_effective_vat_on_top_per_item_null_inherits_header():
    assert effective_vat_on_top(None, True, "per_item") is True
    assert effective_vat_on_top(None, False, "per_item") is False


# ---------------------------------------------------------------------------
# effective_vat_rate — uniform берёт ставку шапки (если шапка облагает НДС),
# per_item всегда свою; зеркалит фронтовый effectiveVatRateForItem
# (useVatCalc.ts:149-156)
# ---------------------------------------------------------------------------

def test_effective_vat_rate_uniform_uses_header_rate_when_applicable():
    assert effective_vat_rate(None, "uniform", True, 22) == 22


def test_effective_vat_rate_uniform_no_rate_when_header_not_applicable():
    assert effective_vat_rate(None, "uniform", False, 22) is None
    assert effective_vat_rate(None, "uniform", None, 22) is None


def test_effective_vat_rate_per_item_uses_row_rate_only():
    assert effective_vat_rate("10%", "per_item", True, 22) == "10%"
    assert effective_vat_rate(None, "per_item", True, 22) is None


# ---------------------------------------------------------------------------
# qty_price_check — расхождение не возникает, когда флаг учтён
# ---------------------------------------------------------------------------

def test_qty_price_check_no_mismatch_with_on_top_flag():
    """10 шт × 100 (без налога) и файл несёт сумму 1220 (с налогом, 22%
    сверху) — раньше это было бы sum_mismatch (1000 ≠ 1220), с флагом/
    ставкой расхождения нет."""
    result = check_qty_price_sum(
        1, "Позиция УПД", Decimal("10"), Decimal("100"), Decimal("1220"),
        vat_rate="22%", vat_on_top=True,
    )
    assert result is None


def test_qty_price_check_still_flags_real_mismatch():
    """Реальное расхождение (не объяснимое надбавкой) по-прежнему ловится."""
    result = check_qty_price_sum(
        1, "Позиция", Decimal("10"), Decimal("100"), Decimal("500"),
        vat_rate="22%", vat_on_top=True,
    )
    assert result is not None
    assert result["kind"] == "sum_mismatch"


def test_qty_price_check_default_behaviour_unchanged():
    """Без vat_rate/vat_on_top (умолчания) — поведение как раньше."""
    assert check_qty_price_sum(1, "Позиция", Decimal("10"), Decimal("100"), Decimal("1000")) is None
    bad = check_qty_price_sum(1, "Позиция", Decimal("10"), Decimal("100"), Decimal("1220"))
    assert bad is not None


# ---------------------------------------------------------------------------
# API: PATCH одной позиции закупки с vat_on_top → total_price с НДС
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_purchase_item_vat_on_top_saves_total_with_vat(client, auth_headers, db_session, test_org):
    """Закупка в статусе 'plan_schedule' (ТЗ ещё не заморожено) с одной
    позицией (vat_mode='per_item'), затем PATCH включает vat_on_top на САМОЙ
    позиции — total_price обязан пересчитаться С надбавкой (10×100 при 22%
    сверху = 1220,00)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    purchase = Purchase(
        subject="Проверка НДС сверху", purchase_method="single",
        status="plan_schedule", vat_mode="per_item",
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Товар УПД", item_type="товар",
        quantity=Decimal("10"), unit="шт",
        unit_price=Decimal("100"), total_price=Decimal("1000"),
        vat_rate="22%",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    patch_resp = await client.patch(
        f"/api/purchases/{purchase.id}/items/{item.id}",
        json={"vat_on_top": True},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert body["vat_on_top"] is True
    assert Decimal(str(body["total_price"])) == Decimal("1220.00")


@pytest.mark.asyncio
async def test_patch_purchase_item_uniform_vat_on_top_uses_header_rate(client, auth_headers, db_session, test_org):
    """Дефект «НДС сверху» (02.10.2026): закупка в режиме vat_mode='uniform',
    шапка — vat_applicable=True, vat_rate=22, tz_vat_on_top=True; у строки
    СВОЕЙ ставки нет (vat_rate=None, как и приходит с фронта в uniform —
    поле ввода ставки строки не рендерится). PATCH кол-ва/цены ОБЯЗАН взять
    ставку из шапки через effective_vat_rate — total_price = 10×100×1.22 =
    1220,00, а не 1000 (старый баг: формула читала пустую ставку строки)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    purchase = Purchase(
        subject="Проверка НДС сверху uniform", purchase_method="single",
        status="plan_schedule", vat_mode="uniform",
        vat_applicable=True, vat_rate=22, tz_vat_on_top=True,
    )
    db_session.add(purchase)
    await db_session.flush()
    item = PurchaseItem(
        purchase_id=purchase.id, item_name="Товар УПД", item_type="товар",
        quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("1"), total_price=Decimal("1"),
        vat_rate=None,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    patch_resp = await client.patch(
        f"/api/purchases/{purchase.id}/items/{item.id}",
        json={"quantity": "10", "unit_price": "100"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert Decimal(str(body["total_price"])) == Decimal("1220.00")


@pytest.mark.asyncio
async def test_sync_wish_items_to_purchases_uniform_vat_on_top_uses_header_rate(client, auth_headers, db_session, test_org):
    """_sync_wish_items_to_purchases (wish_distribution.py:977, тот же дефект
    «НДС сверху», 02.10.2026) раньше звала line_total(qty, price) совсем без
    rate/on_top — надбавка терялась при синхронизации позиции закупки из
    заявки. Закупка uniform, шапка 22%, tz_vat_on_top=True, у строки закупки
    своей ставки/флага нет (None/None) — после синка total_price обязан
    получиться 1220,00 (10 × 100 × 1.22), а не 1000."""
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.services.wish_distribution import _sync_wish_items_to_purchases

    wish = Wish(
        title="Заявка НДС сверху uniform sync", status="approved", org_id=test_org.id,
        vat_mode="uniform",
    )
    db_session.add(wish)
    await db_session.flush()
    wi = WishItem(
        wish_id=wish.id, item_name="Товар", item_type="товар",
        quantity=Decimal("10"), unit="шт",
        unit_price=Decimal("100"), total_price=Decimal("100"),
        vat_rate=None,
    )
    db_session.add(wi)
    await db_session.flush()

    purchase = Purchase(
        subject="Синхронизация НДС сверху uniform", purchase_method="single",
        status="plan_schedule", wish_id=wish.id, vat_mode="uniform",
        vat_applicable=True, vat_rate=22, tz_vat_on_top=True,
    )
    db_session.add(purchase)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=purchase.id, wish_item_id=wi.id,
        item_name="Товар", item_type="товар",
        quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("1"), total_price=Decimal("1"),
        vat_rate=None, vat_on_top=None,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(wish)
    wish.items = [wi]

    await _sync_wish_items_to_purchases(wish, db_session)

    await db_session.refresh(pi)
    assert Decimal(str(pi.total_price)) == Decimal("1220.00")


# ---------------------------------------------------------------------------
# Конвертация заявки → закупка переносит флаги
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wish_convert_carries_vat_on_top_flags(client, auth_headers, db_session, test_org):
    """tz_vat_on_top заявки и vat_on_top строки обязаны оказаться на закупке/
    позиции после конвертации (задача 3 плана)."""
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    import uuid as _uuid

    subsidy = Subsidy(name=f"TestVatOnTop-{_uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id, status="approved")
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория теста НДС сверху")
    db_session.add(cat)
    await db_session.flush()

    wish = Wish(
        title="Заявка НДС сверху", status="approved", org_id=test_org.id,
        subsidy_id=subsidy.id, feo_category_id=cat.id,
        tz_vat_on_top=True, vat_mode="per_item",
    )
    db_session.add(wish)
    await db_session.flush()
    from datetime import date, timedelta
    wi = WishItem(
        wish_id=wish.id, item_name="Товар", item_type="товар",
        quantity=Decimal("10"), unit="шт",
        unit_price=Decimal("100"), total_price=Decimal("1220"),
        vat_rate="22%", vat_on_top=True, feo_category_id=cat.id,
        needed_date=date.today() + timedelta(days=30),
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wish)

    resp = await client.post(
        f"/api/wishes/{wish.id}/convert",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text

    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from sqlalchemy import select
    purchase = (await db_session.execute(
        select(Purchase).where(Purchase.wish_id == wish.id)
    )).scalars().first()
    assert purchase is not None
    assert purchase.tz_vat_on_top is True

    item = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )).scalars().first()
    assert item is not None
    assert item.vat_on_top is True
