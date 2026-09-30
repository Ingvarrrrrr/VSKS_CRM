"""Владелец (30.09): окно выбора рамочного договора в закупке не должно быть
заперто на субсидию закупки (кейс Любарец: закупка в МИНПРОС_2026, нужные
договоры ОФИСМАГ привязаны к ФАДМ_2026той же организации). GET /contracts/
теперь принимает prefer_subsidy_id — не сужает выборку, а ранжирует договоры
всего аккаунта (тот же контур видимости, что и всегда):

  contract_group 1 — субсидия закупки (свой subsidy_id ИЛИ доп. привязка
                     через contract_subsidies),
  contract_group 2 — другая субсидия ТОЙ ЖЕ организации,
  contract_group 3 — остальные договоры аккаунта (другая организация, тот же
                     контур/аккаунт),
  вне выдачи      — договор другого аккаунта (visibility не даёт течь).

См. backend/app/routers/contracts.py::list_contracts.
"""
import uuid
import pytest
from datetime import date


async def _make_subsidy(db_session, org_id, name, year=2026):
    from app.models.subsidy import Subsidy

    s = Subsidy(name=name, year=year, org_id=org_id, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_contract(db_session, subsidy_id, number, *, contract_type="framework_cumulative", d=None):
    from app.models.contract import Contract

    c = Contract(
        number=number,
        date=d,
        contract_type=contract_type,
        subsidy_id=subsidy_id,
        status="active",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.mark.asyncio
async def test_prefer_subsidy_id_ranks_and_scopes_to_account(
    db_session, client, test_org, test_admin_user, admin_headers,
):
    """Ранги 1/2/3 + доп. привязка contract_subsidies попадает в ранг 1 +
    договор ДРУГОГО аккаунта не виден вовсе."""
    from app.models.organization import Organization
    from app.models.contract_subsidy import ContractSubsidy

    # --- субсидии в АККАУНТЕ test_admin_user -------------------------------
    subsidy_target = await _make_subsidy(db_session, test_org.id, "МИНПРОС_2026")
    subsidy_other = await _make_subsidy(db_session, test_org.id, "ФАДМ_2026")

    # Дочерняя орг того же аккаунта (root_org_id → тот же контур, см.
    # compute_account_contour_org_ids) — субсидия там тоже должна попасть в
    # выдачу, только рангом 3.
    child_org = Organization(name=f"ChildOrg-{uuid.uuid4().hex[:8]}", root_org_id=test_org.id)
    db_session.add(child_org)
    await db_session.commit()
    await db_session.refresh(child_org)
    subsidy_child = await _make_subsidy(db_session, child_org.id, "ДРУГАЯ_ОРГ_2026")

    # Полностью ПОСТОРОННИЙ аккаунт — не должен утечь в выдачу вообще.
    foreign_org = Organization(name=f"ForeignOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(foreign_org)
    await db_session.commit()
    await db_session.refresh(foreign_org)
    subsidy_foreign = await _make_subsidy(db_session, foreign_org.id, "ЧУЖОЙ_АККАУНТ_2026")

    # --- договоры ------------------------------------------------------------
    contract_a = await _make_contract(db_session, subsidy_target.id, "A-OWN", d=date(2026, 1, 1))
    contract_b = await _make_contract(db_session, subsidy_other.id, "B-EXTRA-LINK", d=date(2026, 2, 1))
    # Доп. привязка contract_b → subsidy_target: раньше игнорировалась фильтром
    # subsidy_id== — теперь обязана поднять contract_b в ранг 1 несмотря на то,
    # что его СОБСТВЕННЫЙ subsidy_id — subsidy_other.
    db_session.add(ContractSubsidy(contract_id=contract_b.id, subsidy_id=subsidy_target.id))
    await db_session.commit()

    contract_c = await _make_contract(db_session, subsidy_other.id, "C-SAME-ORG", d=date(2026, 3, 1))
    contract_d = await _make_contract(db_session, subsidy_child.id, "D-OTHER-ORG", d=date(2026, 4, 1))
    contract_foreign = await _make_contract(db_session, subsidy_foreign.id, "X-FOREIGN-ACCOUNT")

    resp = await client.get(
        "/api/contracts/",
        params={"prefer_subsidy_id": subsidy_target.id, "contract_type": "framework_cumulative"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    by_number = {r["number"]: r for r in rows}

    # Договор чужого аккаунта не должен утечь вовсе (Правило №4/visibility).
    assert "X-FOREIGN-ACCOUNT" not in by_number, (
        f"Contract of a foreign account leaked into results: {list(by_number)}"
    )

    for expected_number in ("A-OWN", "B-EXTRA-LINK", "C-SAME-ORG", "D-OTHER-ORG"):
        assert expected_number in by_number, (
            f"Expected {expected_number} in response, got {list(by_number)}"
        )

    assert by_number["A-OWN"]["contract_group"] == 1
    assert by_number["B-EXTRA-LINK"]["contract_group"] == 1, (
        "contract_subsidies extra link to prefer_subsidy_id must rank as group 1"
    )
    assert by_number["C-SAME-ORG"]["contract_group"] == 2
    assert by_number["D-OTHER-ORG"]["contract_group"] == 3

    # subsidy_name/org_name — подпись для фронта на группах 2/3.
    assert by_number["C-SAME-ORG"]["subsidy_name"] == "ФАДМ_2026"
    assert by_number["D-OTHER-ORG"]["org_name"] == child_org.name

    # Сортировка: ранг возрастает, внутри ранга — дата по убыванию.
    order = [r["number"] for r in rows if r["number"] != "X-FOREIGN-ACCOUNT"]
    assert order.index("B-EXTRA-LINK") < order.index("A-OWN"), (
        "within group 1, later date (B, 2026-02-01) must come before earlier (A, 2026-01-01)"
    )
    assert order.index("A-OWN") < order.index("C-SAME-ORG") < order.index("D-OTHER-ORG")


@pytest.mark.asyncio
async def test_without_prefer_subsidy_id_group_is_none(
    db_session, client, test_org, test_admin_user, admin_headers,
):
    """Обычный вызов (без prefer_subsidy_id, как раньше — реестр договоров)
    не должен внезапно проставлять contract_group — только новый параметр
    включает ранжирование."""
    subsidy = await _make_subsidy(db_session, test_org.id, "ОБЫЧНАЯ_2026")
    await _make_contract(db_session, subsidy.id, "PLAIN", d=date(2026, 1, 1))

    resp = await client.get(
        "/api/contracts/",
        params={"subsidy_id": subsidy.id},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["contract_group"] is None
