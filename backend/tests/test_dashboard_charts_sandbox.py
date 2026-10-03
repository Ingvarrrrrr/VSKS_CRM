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
