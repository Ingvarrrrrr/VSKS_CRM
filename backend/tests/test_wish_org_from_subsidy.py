# -*- coding: utf-8 -*-
"""Прод-баг (заявка №209, 22.10.2026): org_id заявки с субсидией должен
совпадать с org_id этой субсидии, не с произвольным элементом get_org_filter.

Решение владельца: заявка с субсидией → org_id = subsidies.org_id. Без
субсидии → активная организация пользователя (прежний фолбэк). Единственный
источник — app/services/wish_org.py::resolve_wish_org_id, вызванный из
create_wish/update_wish (routers/wishes.py) и patch_wish_execution
(routers/wish_transitions.py); create_wish_from_plan (services/plan_to_wish.py)
наследует фикс, т.к. зовёт create_wish напрямую (Правило №6).

Приёмы — по образцу test_object_visibility.py (account_owner с контуром из
ДВУХ организаций через Organization.root_org_id-дерево) и test_plan_to_wish.py
(прямой вызов сервисных функций с db_session, без HTTP-клиента)."""
import uuid

import pytest
from fastapi import HTTPException

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.routers.wishes import create_wish, update_wish
from app.schemas.wishes import WishCreate, WishUpdate
from app.services.plan_to_wish import PlanToWishItemInput, create_wish_from_plan


async def _make_org(db_session, root_org_id=None, owner_user_id=None):
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    name = f"WishOrgTest-{uuid.uuid4().hex[:8]}"
    contractor = Contractor(name=name)
    db_session.add(contractor)
    await db_session.flush()
    org = Organization(contractor_id=contractor.id, root_org_id=root_org_id, owner_user_id=owner_user_id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _make_subsidy(db_session, org_id, name="WishOrgTest subsidy") -> Subsidy:
    s = Subsidy(name=f"{name}-{uuid.uuid4().hex[:8]}", year=2026, budget=0, org_id=org_id, status="approved")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_owner_with_two_orgs(db_session, make_user):
    """account_owner с контуром из ДВУХ организаций: owner_org (его "домашняя",
    создана первой — меньший id) и child_org (root_org_id=owner_org.id, создана
    позже — БОЛЬШИЙ id). _get_effective_simple даёт account_owner все ключи во
    всех оргах своего контура (app/auth/permissions.py) — ensure_subsidy_visible
    видит субсидию child_org без доп. грантов."""
    owner_org = await _make_org(db_session)
    owner = await make_user(role="account_owner", org_id=owner_org.id)
    owner_org.owner_user_id = owner.id
    db_session.add(owner_org)
    await db_session.commit()

    child_org = await _make_org(db_session, root_org_id=owner_org.id)
    assert child_org.id > owner_org.id  # не с наименьшим id — ровно случай бага
    return owner, owner_org, child_org


@pytest.mark.asyncio
async def test_create_wish_org_follows_subsidy_not_smallest_org(db_session, make_user):
    """(а) create_wish: субсидия во ВТОРОЙ (не наименьшей по id) организации
    контура → wish.org_id = org субсидии, не owner_org.id (его собственный/
    "первый" org_id, который раньше ошибочно попадал бы на верхушку
    list(set(get_org_filter(...)))."""
    owner, owner_org, child_org = await _make_owner_with_two_orgs(db_session, make_user)
    subsidy = await _make_subsidy(db_session, child_org.id)

    out = await create_wish(
        body=WishCreate(title="Заявка на основе плана ХРО", subsidy_id=subsidy.id),
        db=db_session, current_user=owner,
    )

    assert out.subsidy_id == subsidy.id
    wish = await db_session.get(Wish, out.id)
    assert wish.org_id == child_org.id
    assert wish.org_id != owner_org.id


@pytest.mark.asyncio
async def test_create_wish_from_plan_org_follows_subsidy(db_session, make_user):
    """(а) тот же сценарий, но через путь «Создать закупку на основе плана»
    (create_wish_from_plan → create_wish, ПРАВИЛО №6 — одна функция создания,
    не копия) — ровно путь из прод-бага (заявка №209)."""
    owner, owner_org, child_org = await _make_owner_with_two_orgs(db_session, make_user)
    subsidy = await _make_subsidy(db_session, child_org.id)
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Прочее")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    planned = FeoPlannedItem(
        feo_category_id=cat.id, name="Перчатки", quantity=10, unit_price=100, amount=1000,
        unit="шт", is_active=True,
    )
    db_session.add(planned)
    await db_session.commit()
    await db_session.refresh(planned)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=2, item_name="Перчатки", price_source="plan")]
    result = await create_wish_from_plan(db_session, owner, subsidy.id, "Закупка на основе плана", items)

    wish = await db_session.get(Wish, result["wish_id"])
    assert wish.org_id == child_org.id
    assert wish.org_id != owner_org.id


@pytest.mark.asyncio
async def test_create_wish_invisible_subsidy_404_no_wish_created(db_session, make_user, test_org):
    """(б) субсидия невидимая пользователю → 404 (ensure_subsidy_visible),
    заявка не создаётся вовсе — resolve_wish_org_id проверяет видимость ДО
    использования org_id субсидии (ПРАВИЛО №8 п.2: subsidy_id из тела запроса
    нельзя доверять без проверки)."""
    employee = await make_user(role="employee", org_id=test_org.id)

    foreign_org = await _make_org(db_session)
    foreign_subsidy = await _make_subsidy(db_session, foreign_org.id)

    from sqlalchemy import select, func
    before = (await db_session.execute(select(func.count()).select_from(Wish))).scalar()

    with pytest.raises(HTTPException) as exc_info:
        await create_wish(
            body=WishCreate(title="Заявка в чужую субсидию", subsidy_id=foreign_subsidy.id),
            db=db_session, current_user=employee,
        )
    assert exc_info.value.status_code == 404

    after = (await db_session.execute(select(func.count()).select_from(Wish))).scalar()
    assert after == before


@pytest.mark.asyncio
async def test_create_wish_without_subsidy_uses_active_org(db_session, test_user):
    """(в) без субсидии — прежний фолбэк: активная организация пользователя."""
    out = await create_wish(
        body=WishCreate(title="Заявка без субсидии"),
        db=db_session, current_user=test_user,
    )
    wish = await db_session.get(Wish, out.id)
    assert wish.org_id == test_user.org_id


@pytest.mark.asyncio
async def test_update_wish_subsidy_change_moves_org(db_session, make_user):
    """(г) смена субсидии правкой (PUT) переносит заявку в организацию новой
    субсидии — тот же хелпер, что при создании (ПРАВИЛО №6)."""
    owner, owner_org, child_org = await _make_owner_with_two_orgs(db_session, make_user)
    subsidy_old = await _make_subsidy(db_session, owner_org.id, name="Old")
    subsidy_new = await _make_subsidy(db_session, child_org.id, name="New")

    created = await create_wish(
        body=WishCreate(title="Заявка до смены субсидии", subsidy_id=subsidy_old.id),
        db=db_session, current_user=owner,
    )
    wish_before = await db_session.get(Wish, created.id)
    assert wish_before.org_id == owner_org.id

    await update_wish(
        wish_id=created.id,
        body=WishUpdate(subsidy_id=subsidy_new.id),
        db=db_session, current_user=owner,
    )

    await db_session.refresh(wish_before)
    assert wish_before.subsidy_id == subsidy_new.id
    assert wish_before.org_id == child_org.id


@pytest.mark.asyncio
async def test_update_wish_same_subsidy_resend_does_not_require_subsidy_visibility(
    db_session, make_user, test_org,
):
    """Доработка после ревью (22.10.2026): фронт (buildWishPayload) шлёт
    subsidy_id в КАЖДОМ PUT, даже без реальной правки субсидии. resolve_wish_org_id
    (а значит ensure_subsidy_visible) должен звать update_wish ТОЛЬКО когда
    body.subsidy_id != wish.subsidy_id — иначе участник заявки (WishMember),
    который видит саму заявку, но не карточку субсидии (у employee по
    умолчанию нет вкладки 'subsidies' — см. test_plan_to_wish.py), получал бы
    404 на обычное пересохранение без единой правки субсидии.

    member — сотрудник ТОЙ ЖЕ организации (иначе не пройдёт org-изоляцию в
    ensure_wish_read_access), но НЕ автор, НЕ согласующий — участник (WishMember)
    без грантов на субсидию."""
    from app.models.wish_member import WishMember

    creator = await make_user(role="employee", org_id=test_org.id)
    member = await make_user(role="employee", org_id=test_org.id)
    subsidy = await _make_subsidy(db_session, test_org.id)

    wish = Wish(
        org_id=test_org.id, title="Заявка без правки субсидии",
        subsidy_id=subsidy.id, status="draft", created_by=creator.id,
    )
    db_session.add(wish)
    await db_session.flush()
    db_session.add(WishMember(wish_id=wish.id, user_id=member.id))
    await db_session.commit()

    # Контроль посылки: member субсидию НЕ видит (нет org-дефолта/грантов) —
    # если бы update_wish звал resolve_wish_org_id безусловно, PUT упал бы 404.
    from app.auth.object_visibility import ensure_subsidy_visible
    with pytest.raises(HTTPException) as control_exc:
        await ensure_subsidy_visible(member, subsidy.id, db_session)
    assert control_exc.value.status_code == 404

    out = await update_wish(
        wish_id=wish.id,
        body=WishUpdate(subsidy_id=subsidy.id, title="Пересохранение без смены субсидии"),
        db=db_session, current_user=member,
    )

    assert out.title == "Пересохранение без смены субсидии"
    await db_session.refresh(wish)
    assert wish.subsidy_id == subsidy.id
    assert wish.org_id == test_org.id
