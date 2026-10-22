# -*- coding: utf-8 -*-
"""Жалоба владельца (заявка №209, 22.10.2026): согласующий открывает заявку по
субсидии ХРО_2026 — в поле «Договор (рамочный)» видны ВСЕ рамочные договоры
аккаунта, включая другие организации. Должны быть видны только рамочные
договоры субсидии заявки и других субсидий ТОЙ ЖЕ организации.

Единственная формула — app/services/contract_subsidy_scope.py (contract_group/
ensure_wish_contract_allowed), вызванная из app/routers/contracts.py
(only_subsidy_org) и трёх мест записи Wish.contract_id (create_wish/
update_wish/patch_wish_execution).

Приёмы — по образцу test_contracts_prefer_subsidy_ranking.py (GET /contracts/)
и test_wish_org_from_subsidy.py (прямой вызов сервисных функций с db_session)."""
import uuid

import pytest
from fastapi import HTTPException

from app.models.wish import Wish
from app.routers.wishes import create_wish
from app.routers.wish_transitions import patch_wish_execution
from app.schemas.wishes import WishCreate, WishExecutionPatch


async def _make_subsidy(db_session, org_id, name, year=2026):
    from app.models.subsidy import Subsidy

    s = Subsidy(name=f"{name}-{uuid.uuid4().hex[:8]}", year=year, org_id=org_id, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_contract(db_session, subsidy_id, number, *, contract_type="framework_cumulative"):
    from app.models.contract import Contract

    c = Contract(number=number, contract_type=contract_type, subsidy_id=subsidy_id, status="active")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _make_org(db_session, root_org_id=None):
    from app.models.contractor import Contractor
    from app.models.organization import Organization

    name = f"WishContractScope-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id, root_org_id=root_org_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.mark.asyncio
async def test_only_subsidy_org_excludes_other_org_contracts(
    db_session, client, test_org, test_admin_user, admin_headers,
):
    """(a) only_subsidy_org=true убирает group 3 (другая организация), оставляя
    group 1/2; без параметра — старое поведение (видны все 3)."""
    from app.models.organization import Organization

    subsidy_target = await _make_subsidy(db_session, test_org.id, "ХРО_2026")
    subsidy_other = await _make_subsidy(db_session, test_org.id, "ХРО_ДРУГАЯ_2026")

    child_org = Organization(name=f"ChildOrg-{uuid.uuid4().hex[:8]}", root_org_id=test_org.id)
    db_session.add(child_org)
    await db_session.commit()
    await db_session.refresh(child_org)
    subsidy_child = await _make_subsidy(db_session, child_org.id, "ДРУГАЯ_ОРГ_2026")

    contract_own = await _make_contract(db_session, subsidy_target.id, "OWN")
    contract_same_org = await _make_contract(db_session, subsidy_other.id, "SAME-ORG")
    contract_other_org = await _make_contract(db_session, subsidy_child.id, "OTHER-ORG")

    resp_all = await client.get(
        "/api/contracts/",
        params={"prefer_subsidy_id": subsidy_target.id},
        headers=admin_headers,
    )
    assert resp_all.status_code == 200, resp_all.text
    numbers_all = {r["number"] for r in resp_all.json()}
    assert {"OWN", "SAME-ORG", "OTHER-ORG"} <= numbers_all

    resp_scoped = await client.get(
        "/api/contracts/",
        params={"prefer_subsidy_id": subsidy_target.id, "only_subsidy_org": "true"},
        headers=admin_headers,
    )
    assert resp_scoped.status_code == 200, resp_scoped.text
    numbers_scoped = {r["number"] for r in resp_scoped.json()}
    assert "OWN" in numbers_scoped
    assert "SAME-ORG" in numbers_scoped
    assert "OTHER-ORG" not in numbers_scoped, (
        f"only_subsidy_org must drop group-3 (other org) contracts, got {numbers_scoped}"
    )


@pytest.mark.asyncio
async def test_create_wish_rejects_contract_of_other_org(db_session, make_user, test_org):
    """(b) POST-эквивалент (create_wish): договор чужой организации (другой
    субсидии того же аккаунта) → 400; договор своей организации → создаётся."""
    from app.models.organization import Organization

    owner = await make_user(role="account_owner", org_id=test_org.id)
    test_org.owner_user_id = owner.id
    db_session.add(test_org)
    await db_session.commit()

    child_org = Organization(name=f"ChildOrg-{uuid.uuid4().hex[:8]}", root_org_id=test_org.id)
    db_session.add(child_org)
    await db_session.commit()
    await db_session.refresh(child_org)

    subsidy_target = await _make_subsidy(db_session, test_org.id, "ХРО_2026")
    subsidy_other_org = await _make_subsidy(db_session, child_org.id, "ДРУГАЯ_ОРГ_2026")
    subsidy_same_org = await _make_subsidy(db_session, test_org.id, "ХРО_ДРУГАЯ_2026")

    contract_wrong_org = await _make_contract(db_session, subsidy_other_org.id, "WRONG-ORG")
    contract_right_org = await _make_contract(db_session, subsidy_same_org.id, "RIGHT-ORG")

    with pytest.raises(HTTPException) as exc_info:
        await create_wish(
            body=WishCreate(
                title="Заявка с чужим договором",
                subsidy_id=subsidy_target.id,
                contract_id=contract_wrong_org.id,
            ),
            db=db_session, current_user=owner,
        )
    assert exc_info.value.status_code == 400

    out = await create_wish(
        body=WishCreate(
            title="Заявка со своим договором (другая субсидия той же орг.)",
            subsidy_id=subsidy_target.id,
            contract_id=contract_right_org.id,
        ),
        db=db_session, current_user=owner,
    )
    assert out.contract_id == contract_right_org.id


@pytest.mark.asyncio
async def test_create_wish_rejects_non_framework_contract(db_session, make_user, test_org):
    """(d) договор не рамочного типа → 400, независимо от организации."""
    owner = await make_user(role="account_owner", org_id=test_org.id)
    test_org.owner_user_id = owner.id
    db_session.add(test_org)
    await db_session.commit()

    subsidy = await _make_subsidy(db_session, test_org.id, "ХРО_2026")
    non_framework = await _make_contract(
        db_session, subsidy.id, "SINGLE", contract_type="standard",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_wish(
            body=WishCreate(
                title="Заявка с нерамочным договором",
                subsidy_id=subsidy.id,
                contract_id=non_framework.id,
            ),
            db=db_session, current_user=owner,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_patch_execution_rejects_contract_of_other_org(db_session, make_user, test_org):
    """(c) PATCH /wishes/{id}/execution с договором чужой организации → 400."""
    from app.models.organization import Organization

    owner = await make_user(role="account_owner", org_id=test_org.id)
    test_org.owner_user_id = owner.id
    db_session.add(test_org)
    await db_session.commit()

    child_org = Organization(name=f"ChildOrg-{uuid.uuid4().hex[:8]}", root_org_id=test_org.id)
    db_session.add(child_org)
    await db_session.commit()
    await db_session.refresh(child_org)

    subsidy_target = await _make_subsidy(db_session, test_org.id, "ХРО_2026")
    subsidy_other_org = await _make_subsidy(db_session, child_org.id, "ДРУГАЯ_ОРГ_2026")
    contract_wrong_org = await _make_contract(db_session, subsidy_other_org.id, "WRONG-ORG-EXEC")

    created = await create_wish(
        body=WishCreate(title="Заявка на согласование", subsidy_id=subsidy_target.id),
        db=db_session, current_user=owner,
    )

    with pytest.raises(HTTPException) as exc_info:
        await patch_wish_execution(
            wish_id=created.id,
            body=WishExecutionPatch(contract_id=contract_wrong_org.id),
            db=db_session, current_user=owner,
        )
    assert exc_info.value.status_code == 400

    wish = await db_session.get(Wish, created.id)
    assert wish.contract_id is None
