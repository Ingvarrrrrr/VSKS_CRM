"""test_purchase_amount_single_source.py — ПРАВИЛО №6 (2026-09-05): один
показатель («эффективная сумма закупки») обязан давать ОДНО число во ВСЕХ
переведённых на app.services.purchase_amounts читателях одновременно — не
«похожие», а РОВНО одно и то же значение на одних и тех же данных.

Кросс-тест построен на ОДНОЙ закупке в статусе `delivered` с
acceptance_doc_amount заданным (в этом статусе effective = acceptance_doc_
amount — общая ветка для ВСЕХ переведённых читателей: GET /api/purchases/
{id} (amounts.effective), SQL-агрегат dashboard.py (effective_amount_expr()),
_resolve_doc_amount (не-договорной doc_type), GET /api/feo-categories/
purchase-totals, _calculate_spent). Сверяется, что все пять дают одно число.

Второй блок — тесты единственного писателя денежных колонок
(app.services.purchase_money_writer.recalc_purchase_money): закупка в
`wishes` не получает contract_price из позиций; закупка в `contracted` с
ContractItem получает Σ ContractItem.total; рамочная голова не перезаписывается.
"""
import uuid
from decimal import Decimal

import pytest

from app.services.purchase_amounts import effective_amount_expr


async def _make_subsidy(db_session, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
                require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(subsidy_id=subsidy_id, parent_id=None, level=1,
                       name=f"Cat-{uuid.uuid4().hex[:8]}")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


# ---------------------------------------------------------------------------
# Кросс-сверка: одно число во всех пяти читателях
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delivered_purchase_same_number_everywhere(
    client, db_session, make_purchase, auth_headers,
):
    subsidy = await _make_subsidy(db_session)
    category = await _make_category(db_session, subsidy.id)
    p = await make_purchase(
        status="delivered",
        subsidy_id=subsidy.id,
        feo_category_id=category.id,
        acceptance_doc_amount=Decimal("123456.78"),
        contract_price=Decimal("111111"),  # должен быть перекрыт acceptance_doc_amount
    )
    expected = Decimal("123456.78")

    # 1) GET /api/purchases/{id} -> amounts.effective
    resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    amounts = resp.json()["amounts"]
    assert Decimal(str(amounts["effective"])) == expected
    assert amounts["effective_source"] == "acceptance_doc_amount"

    # 2) dashboard-агрегат (effective_amount_expr(), тот же SQL, что и в
    # dashboard.py/subsidies.py/feo_categories.py).
    from sqlalchemy import select, func
    from app.models.purchase import Purchase
    dash_val = (await db_session.execute(
        select(func.coalesce(func.sum(effective_amount_expr()), 0)).where(Purchase.id == p.id)
    )).scalar_one()
    assert Decimal(str(dash_val)) == expected

    # 3) _resolve_doc_amount — не-договорной doc_type
    from app.routers import documents as docs
    p_full = (await db_session.execute(
        select(Purchase).where(Purchase.id == p.id)
    )).scalar_one()
    doc_amount, amount_is_planned = docs._resolve_doc_amount(p_full, "tech_spec_request")
    assert Decimal(str(doc_amount)) == expected
    assert amount_is_planned is False  # acceptance_doc_amount — не план

    # 4) GET /api/feo-categories/purchase-totals
    resp2 = await client.get(
        "/api/feo-categories/purchase-totals", params={"subsidy_id": subsidy.id}, headers=auth_headers,
    )
    assert resp2.status_code == 200, resp2.text
    totals = resp2.json()
    assert Decimal(str(totals[str(category.id)])) == expected

    # 5) _calculate_spent
    from app.routers.subsidies import _calculate_spent
    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == expected


@pytest.mark.asyncio
async def test_contracted_purchase_same_number_across_readers(
    client, db_session, make_purchase, make_contract_item, auth_headers,
):
    """Тот же кросс-тест на стадии «Договор» (contract_price ?? Σci), без
    acceptance_doc_amount — effective приходит из contract_price."""
    subsidy = await _make_subsidy(db_session)
    p = await make_purchase(status="contracted", subsidy_id=subsidy.id, contract_price=Decimal("500000"))
    expected = Decimal("500000")

    resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    amounts = resp.json()["amounts"]
    assert Decimal(str(amounts["effective"])) == expected
    assert amounts["effective_source"] == "contract_price"

    from sqlalchemy import select, func
    from app.models.purchase import Purchase
    dash_val = (await db_session.execute(
        select(func.coalesce(func.sum(effective_amount_expr()), 0)).where(Purchase.id == p.id)
    )).scalar_one()
    assert Decimal(str(dash_val)) == expected

    from app.routers.subsidies import _calculate_spent
    spent = await _calculate_spent(db_session, subsidy.id)
    assert Decimal(str(spent)) == expected


# ---------------------------------------------------------------------------
# Единственный писатель — recalc_purchase_money
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_item_on_wishes_does_not_write_contract_price(
    client, db_session, make_purchase, auth_headers,
):
    """PATCH позиции закупки в статусе `wishes` пересчитывает план
    (planned_total_price/total_nmck), но НЕ пишет contract_price — до
    договора его писать некому (нет ContractItem)."""
    from app.models.purchase_item import PurchaseItem

    p = await make_purchase(status="wishes", contract_price=None)
    item = PurchaseItem(
        purchase_id=p.id, item_name="Товар", quantity=Decimal("1"),
        unit="шт", unit_price=Decimal("100"), total_price=Decimal("100"),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    resp = await client.patch(
        f"/api/purchases/{p.id}/items/{item.id}",
        json={"quantity": 3, "unit_price": "200"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    from sqlalchemy import select
    from app.models.purchase import Purchase
    refreshed = (await db_session.execute(select(Purchase).where(Purchase.id == p.id))).scalar_one()
    assert refreshed.planned_total_price == Decimal("600")
    assert refreshed.total_nmck == Decimal("600")
    assert refreshed.contract_price is None


@pytest.mark.asyncio
async def test_create_contract_item_on_contracted_writes_sum(
    client, make_purchase, admin_headers,
):
    """POST contract-items на закупке в `contracted` — contract_price := Σci
    (единственный писатель, вызванный из contract_items.py)."""
    p = await make_purchase(status="contracted", contract_price=None)
    resp = await client.post(
        f"/api/purchases/{p.id}/contract-items",
        json={"name": "A", "quantity": 2, "unit": "шт", "unit_price": "150", "total": "300"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    resp2 = await client.get(f"/api/purchases/{p.id}", headers=admin_headers)
    assert resp2.status_code == 200
    assert Decimal(str(resp2.json()["contract_price"])) == Decimal("300")


@pytest.mark.asyncio
async def test_framework_head_contract_price_not_overwritten_by_writer(
    db_session, make_purchase,
):
    """Рамочная голова с ContractItem — recalc_purchase_money НЕ перезаписывает
    ручной contract_price (та же гарантия, что test_purchase_contract_price_
    recalc.py даёт через _recalc_contract_price_from_contract_items, здесь —
    напрямую через писатель, на который обе обёртки теперь опираются)."""
    from app.models.contract_item import ContractItem
    from app.services.purchase_money_writer import recalc_purchase_money

    manual_price = Decimal("999999")
    head = await make_purchase(
        status="contracted", purchase_contract_type="framework_cumulative",
        parent_purchase_id=None, contract_price=manual_price,
    )
    ci = ContractItem(purchase_id=head.id, name="X", quantity=Decimal("1"),
                       unit="шт", unit_price=Decimal("1"), total=Decimal("1"))
    db_session.add(ci)
    await db_session.commit()

    await recalc_purchase_money(db_session, head)
    await db_session.commit()
    await db_session.refresh(head)
    assert head.contract_price == manual_price


@pytest.mark.asyncio
async def test_create_purchase_without_items_documents_contract_price_behavior_change(
    client, auth_headers,
):
    """QA-запрос (2026-09-06): зафиксировать фактическое поведение создания
    закупки БЕЗ единой позиции (авансовый отчёт: `items=[]`, в теле только
    `nmck`, БЕЗ `contract_price`) и сравнить с HEAD (git show
    HEAD:backend/app/routers/purchases.py ≈2073-2077, ДО этой волны).

    ДО (HEAD): `_items_sum_create = sum([]) or data.nmck` — Python-truthy
    `or` при пустых items ПРОВАЛИВАЛСЯ на data.nmck → `p.contract_price =
    data.nmck` записывалось БЕЗУСЛОВНО, даже для закупки без единой позиции
    и до всякого договора (это и есть «второе перо», которое эта волна
    устраняет).

    ПОСЛЕ (эта волна): create_purchase передаёт recalc_purchase_money
    `items_total=None` (нет строк items_data) и `contract_items_total=None`
    (нет ContractItem) — писатель видит «оба Σ пусты» и, по своему
    докстрингу («если у закупки нет ни позиций, ни договорных позиций —
    ничего не трогать»), НЕ пишет contract_price вообще. Результат —
    contract_price остаётся None, а не равен nmck.

    Экраны, где это видимо: карточка закупки (GET /api/purchases/{id},
    поле contract_price) и список (GET /api/purchases) для авансовых
    отчётов/СЗ, созданных БЕЗ позиций и без явного contract_price в форме —
    раньше в колонке/поле «Цена договора» сразу показывалось число (= НМЦК),
    теперь там пусто, пока договорные позиции/акт не появятся. planned_
    total_price/total_nmck/nmck остаются как заданы в payload (сюда
    recalc_purchase_money тоже не заходит при пустых items) — не затронуты
    этой сменой поведения."""
    resp = await client.post(
        "/api/purchases/",
        json={"purchase_method": "advance", "nmck": "12345.67", "items": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_price"] is None, (
        "contract_price больше не наследует nmck при создании без позиций — "
        "см. докстринг теста про смену поведения относительно HEAD"
    )


# ---------------------------------------------------------------------------
# /wishes/{id}/convert — approved_price владелец (2026-09-06, QA раунд 2, п.2):
# «Утверждённая цена» действует ТОЛЬКО для заявок БЕЗ позиций. У заявки С
# позициями согласующий правит количество/цену В САМИХ позициях — сумма
# закупки строго = Σ позиций, approved_price игнорируется (не 422).
# ---------------------------------------------------------------------------

async def _make_wish(db_session, test_org, test_user, **kwargs):
    from app.models.wish import Wish
    w = Wish(org_id=test_org.id, title="Тестовая заявка", status="approved",
              created_by=test_user.id, **kwargs)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


@pytest.mark.asyncio
async def test_convert_wish_with_items_ignores_approved_price(
    client, db_session, test_org, test_user, admin_headers,
):
    """Заявка с одной позицией (1000) + approved_price=700 в теле /convert —
    закупка создаётся суммой 1000 (Σ позиций), approved_price игнорируется."""
    from app.models.wish_item import WishItem

    subsidy = await _make_subsidy(db_session)
    category = await _make_category(db_session, subsidy.id)
    w = await _make_wish(db_session, test_org, test_user, subsidy_id=subsidy.id, feo_category_id=category.id)
    db_session.add(WishItem(
        wish_id=w.id, item_name="Товар", quantity=1, feo_category_id=category.id,
        unit_price=Decimal("1000"), total_price=Decimal("1000"),
    ))
    await db_session.commit()

    resp = await client.post(
        f"/api/wishes/{w.id}/convert",
        json={"approved_price": "700"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved_price_ignored"] is True

    from app.models.purchase import Purchase
    from sqlalchemy import select
    p = (await db_session.execute(select(Purchase).where(Purchase.id == body["purchase_id"]))).scalar_one()
    assert p.planned_total_price == Decimal("1000")
    assert p.total_nmck == Decimal("1000")
    assert p.nmck == Decimal("1000")


@pytest.mark.asyncio
async def test_convert_wish_without_items_uses_approved_price(
    client, db_session, test_org, test_user, admin_headers,
):
    """Заявка БЕЗ позиций + approved_price=700 в теле /convert — закупка
    получает сумму 700 (единственный способ задать её для headless-заявки)."""
    w = await _make_wish(db_session, test_org, test_user, estimated_price=Decimal("999"))

    resp = await client.post(
        f"/api/wishes/{w.id}/convert",
        json={"approved_price": "700"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved_price_ignored"] is False

    from app.models.purchase import Purchase
    from sqlalchemy import select
    p = (await db_session.execute(select(Purchase).where(Purchase.id == body["purchase_id"]))).scalar_one()
    assert p.planned_total_price == Decimal("700")
    assert p.total_nmck == Decimal("700")
    assert p.nmck == Decimal("700")
