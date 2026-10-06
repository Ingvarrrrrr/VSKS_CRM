"""GET /dashboard/charts?scope=managed — страница «Субсидии» (план breezy-
mixing-lovelace.md, Часть Б, правка после приёмки):
  - строка копии ОСТАЁТСЯ в subsidy_stats (её нужно удалить/сделать настоящей)
    и несёт is_sandbox=true/copied_from_id;
  - «итого» страницы (contracts_amt/contracts_cnt/monthly_payments_total,
    собранные в widgets) НЕ подмешивают копию.

Через httpx-клиент (client/superadmin_headers — тот же приём, что
test_subsidy_budget_optional.py), т.к. нужен полноценный HTTP-роут со всей
видимостью/агрегацией, не только сервис напрямую.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.contract import Contract
from app.models.purchase import Purchase


async def _make_subsidy_with_contract(client, superadmin_headers, db_session):
    resp = await client.post(
        "/api/subsidies/",
        json={"name": f"Тест-дашборд-копия-{uuid.uuid4().hex[:8]}", "year": 2026},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    sid = resp.json()["id"]

    contract = Contract(
        number=f"Д-{uuid.uuid4().hex[:8]}", contract_type="single", subsidy_id=sid,
        subject="Тестовый договор", status="active", max_amount=Decimal("300000.00"),
    )
    db_session.add(contract)
    await db_session.flush()
    purchase = Purchase(
        subsidy_id=sid, item_name="Тестовая закупка", status="contracted",
        contract_id=contract.id, contract_price=Decimal("300000.00"),
    )
    db_session.add(purchase)
    await db_session.commit()
    return sid


async def test_sandbox_copy_row_present_with_flag_but_totals_unchanged(client, superadmin_headers, db_session):
    sid = await _make_subsidy_with_contract(client, superadmin_headers, db_session)

    before = await client.get("/api/dashboard/charts?scope=managed", headers=superadmin_headers)
    assert before.status_code == 200, before.text
    before_data = before.json()
    before_contracts_amt = before_data["widgets"]["contracts"]["amount"]
    before_contracts_cnt = before_data["widgets"]["contracts"]["count"]
    orig_row_before = next(s for s in before_data["subsidy_stats"] if s["id"] == sid)
    assert orig_row_before["is_sandbox"] is False
    assert orig_row_before["copied_from_id"] is None

    copy_resp = await client.post(f"/api/subsidies/{sid}/copy", headers=superadmin_headers)
    assert copy_resp.status_code == 200, copy_resp.text
    copy_id = copy_resp.json()["id"]

    try:
        after = await client.get("/api/dashboard/charts?scope=managed", headers=superadmin_headers)
        assert after.status_code == 200, after.text
        after_data = after.json()

        # 1. Копия ЕСТЬ в списке, с правильными флагами.
        copy_row = next(s for s in after_data["subsidy_stats"] if s["id"] == copy_id)
        assert copy_row["is_sandbox"] is True
        assert copy_row["copied_from_id"] == sid
        # Оригинал остаётся обычной субсидией.
        orig_row_after = next(s for s in after_data["subsidy_stats"] if s["id"] == sid)
        assert orig_row_after["is_sandbox"] is False

        # 2. Копия НЕСЁТ свои собственные («как обычно») суммы, а не нули —
        # иначе управлять копией/видеть её состояние было бы нельзя.
        assert copy_row["total_contracts"] == orig_row_after["total_contracts"]

        # 3. «Итого» страницы НЕ изменилось — копия не подмешана в widgets.
        assert after_data["widgets"]["contracts"]["amount"] == before_contracts_amt
        assert after_data["widgets"]["contracts"]["count"] == before_contracts_cnt
    finally:
        del_resp = await client.delete(f"/api/subsidies/{copy_id}/sandbox", headers=superadmin_headers)
        assert del_resp.status_code == 200, del_resp.text

    # Копия действительно удалена, оригинал цел.
    assert await db_session.get(Subsidy, copy_id) is None
    assert await db_session.get(Subsidy, sid) is not None


async def test_sandbox_copy_type_split_matches_original_not_all_unspecified(
    client, superadmin_headers, db_session,
):
    """Находка координатора (06.10.2026, жалоба владельца «ХО (копия)»):
    _purchase_filter внутри dashboard_charts.py (?type_split=true) — тот же
    _apply_purchase_org_filter, что basket_q/monthly_ordered_map, БЕЗ
    explicit_subsidy_ids — он намеренно исключает is_sandbox-копии из ГЛОБАЛЬНЫХ
    widgets[stage] (как contracts_amt/monthly_payments_total). Но раньше этот
    же фильтр применялся и к PER-SUBSIDY раскладке закупок копии (raw_split
    ["per_subsidy"]), оставляя её пустой — reconcile_split форсил ВСЮ сумму
    карточек «Ведётся работа»/«Заказано»/«Поставлено»/«Оплачено» копии в «без
    типа», хотя «Заключено договоров» (contracts, у него внутри
    compute_type_split_raw свой контур БЕЗ sandbox-исключения) считалось
    верно — ровно симптом с живого стенда. Закреплено: разбивка ВСЕХ этапов
    копии должна побайтово совпадать с разбивкой оригинала, без «без типа»
    там, где у позиций закупки есть товар/услуга."""
    from app.models.purchase_item import PurchaseItem

    sid = await _make_subsidy_with_contract(client, superadmin_headers, db_session)
    # Доп. закупка в статусе paid с типизированными позициями — чтобы
    # "work"/"ordered"/"delivered"/"paid" стадии (не только "contracted") тоже
    # были ненулевыми и проверяемыми.
    paid_purchase = Purchase(
        subsidy_id=sid, item_name="Оплаченная закупка", status="paid",
        payment_amount=Decimal("1000.00"),
    )
    db_session.add(paid_purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=paid_purchase.id, item_name="товар", item_type="товар",
        quantity=Decimal("1"), unit_price=Decimal("600"), total_price=Decimal("600"),
    ))
    db_session.add(PurchaseItem(
        purchase_id=paid_purchase.id, item_name="услуга", item_type="услуга",
        quantity=Decimal("1"), unit_price=Decimal("400"), total_price=Decimal("400"),
    ))
    await db_session.commit()

    copy_resp = await client.post(f"/api/subsidies/{sid}/copy", headers=superadmin_headers)
    assert copy_resp.status_code == 200, copy_resp.text
    copy_id = copy_resp.json()["id"]

    try:
        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "managed", "type_split": "true"},
            headers=superadmin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        orig_row = next(s for s in data["subsidy_stats"] if s["id"] == sid)
        copy_row = next(s for s in data["subsidy_stats"] if s["id"] == copy_id)

        for stage in ("work", "ordered", "delivered", "paid", "contracts", "plan_schedule"):
            ow = orig_row["widget"][stage]
            cw = copy_row["widget"][stage]
            assert cw["amount"] == ow["amount"], stage
            for kind in ("goods", "services", "unspecified"):
                key = f"{stage}_{kind}"
                assert cw[key] == ow[key], f"{stage}/{kind}: копия {cw[key]} != оригинал {ow[key]}"
            # «paid» этапа копии должен иметь реальную разбивку товар/услуга
            # (600/400) — НЕ всё в unspecified, хотя закупка без договора.
            if stage == "paid":
                assert cw["paid_goods"] == 600.0
                assert cw["paid_services"] == 400.0
                assert cw["paid_unspecified"] == 0.0

        # Глобальные widgets (без песочницы) не задвоились правкой — инвариант
        # Σ(goods+services+unspecified) == amount по-прежнему держится.
        for stage in ("work", "ordered", "paid", "contracts"):
            w = data["widgets"][stage]
            total = w[f"{stage}_goods"] + w[f"{stage}_services"] + w[f"{stage}_unspecified"]
            assert total == pytest.approx(w["amount"]), stage
    finally:
        del_resp = await client.delete(f"/api/subsidies/{copy_id}/sandbox", headers=superadmin_headers)
        assert del_resp.status_code == 200, del_resp.text
