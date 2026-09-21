"""Задача владельца (план ancient-prancing-music.md, раздел E, 2026-09-21):
контроль превышения ПО ТИПУ (товары/услуги) блокирует forward-переход закупки
ЖЁСТКО — тот же принцип, что и assert_no_pending_tz_excess (см.
test_tz_over_plan_goes_to_approval.py), но для другого вида превышения
(app.services.type_excess_approval.assert_no_pending_type_excess, вызывается
из app.routers.purchase_transitions рядом с ТЗ-гейтом).

Сценарий: категория ФЭО с типизированным ФЭО по услугам (30 000 ₽) и планом
услуг выше этого (60 000 ₽, за счёт позиции ВНЕ ФЭО-разбивки) — узел не
блокирует создание закупки (мягкий контроль), но переход «План закупок» →
«Ведётся работа» заблокирован 409 TYPE_EXCESS_PENDING, пока превышение
plan_over_feo_services не согласовано.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ (pytest tests/test_purchase_transitions_type_gate.py::<name>).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.plan_excess_approval import PlanExcessApproval
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride
from app.services import plan_excess_kinds as PEK
from app.auth.jwt import create_access_token
from app.services.type_excess_approval import collect_type_excess_violations, register_type_excess_approvals


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TypeGate-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=None):
    from app.models.feo_category import FeoCategory
    # budget УЗЛА намеренно НЕ задан (None) — явная FeoCategory.budget узла
    # была бы «нетипизированным бюджетом» (идёт целиком в feo_unspecified, см.
    # app.services.feo_plan_tree._feo_by_kind) и перекрыла бы типизированные
    # is_feo_breakdown-позиции ниже, из-за чего feo_services остался бы 0 и
    # excess_plan_over_feo_services никогда бы не поднялся — контроль по
    # определению требует именно типизированного ФЭО.
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name="Категория — превышение по услугам (тест)",
        budget=budget,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_ceiling_headroom_category(db_session, subsidy_id):
    """Соседняя категория с большим явным бюджетом — поднимает жёсткий
    потолок субсидии (calculate_budget_from_categories, PLAN_OVER_SUBSIDY_
    CEILING в assert_no_unapproved_excess, вызывается ПЕРЕД гейтом по типу в
    purchase_transitions.py) выше суммы плана тестовой категории, чтобы тест
    проверял ИМЕННО контроль по типу, а не жёсткий потолок субсидии (другой,
    уже покрытый вид, см. test_excess_total_not_per_branch.py)."""
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id, parent_id=None, level=1,
        name="Соседняя категория — запас потолка субсидии (тест)",
        budget=Decimal("5000000"),
    )
    db_session.add(cat)
    await db_session.commit()


async def _make_planned_items(db_session, feo_category_id):
    from app.models.feo_planned_item import FeoPlannedItem
    # Типизированное ФЭО по услугам — 30 000 ₽.
    db_session.add(FeoPlannedItem(
        feo_category_id=feo_category_id, name="Услуга (по ФЭО)",
        quantity=Decimal("1"), unit="усл", amount=Decimal("30000"),
        item_type="услуга", is_feo_breakdown=True, feo_amount=Decimal("30000"),
        is_active=True,
    ))
    # Ещё план услуг сверх ФЭО-разбивки — 30 000 ₽ (итого план услуг 60 000 ₽).
    db_session.add(FeoPlannedItem(
        feo_category_id=feo_category_id, name="Услуга сверх ФЭО-разбивки",
        quantity=Decimal("1"), unit="усл", amount=Decimal("30000"),
        item_type="услуга", is_active=True,
    ))
    await db_session.commit()


async def _make_purchase_in_plan_schedule(db_session, subsidy_id, feo_category_id, amount=Decimal("30000")):
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Услуга (закупка, тест типового гейта)",
        status="plan_schedule",
        planned_total_price=amount,
        total_nmck=amount,
        nmck=amount,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Услуга", quantity=Decimal("1"), unit="усл",
        unit_price=amount, total_price=amount,
        feo_category_id=feo_category_id, item_type="услуга", over_plan=False,
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _make_type_excess_approver(db_session, test_org, make_user):
    approver = await make_user(role="manager", org_id=test_org.id)
    uoa = UserOrgAccess(user_id=approver.id, org_id=test_org.id, role="manager")
    db_session.add(uoa)
    await db_session.commit()
    await db_session.refresh(uoa)
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="plan_excess.decide", granted=True,
    ))
    await db_session.commit()
    return approver


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_forward_transition_blocked_by_type_excess_until_approved(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """Переход «План закупок» → «Ведётся работа» заблокирован 409
    TYPE_EXCESS_PENDING, пока превышение plan_over_feo_services не
    согласовано; после approve — переход разрешён."""
    approver = await _make_type_excess_approver(db_session, test_org, make_user)
    approver_headers = _headers_for(approver)

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    await _make_planned_items(db_session, cat.id)
    await _make_ceiling_headroom_category(db_session, subsidy.id)
    purchase = await _make_purchase_in_plan_schedule(db_session, subsidy.id, cat.id)

    # Мягкий путь (create_purchase/PUT) уже собрал бы и зарегистрировал этот
    # запрос — здесь закупка заведена напрямую через ORM (без прохождения
    # эндпоинта), поэтому регистрируем явно тем же сервисом, что и они
    # (app.services.type_excess_approval), чтобы у ЖЁСТКОГО гейта transition
    # было что согласовывать.
    # У этой субсидии единственная типизированная категория — значит нарушение
    # plan_over_feo_services поднимается СРАЗУ на ДВУХ независимых уровнях
    # (category И subsidy, level='subsidy' — собственный контроль, см.
    # collect_type_excess_violations) — оба надо согласовать по отдельности,
    # гейт transition проверяет category_ids (жёстко) И субсидию целиком
    # безусловно (независимые записи — независимые approve).
    violations = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    services_v = [v for v in violations if v["kind"] == PEK.PLAN_OVER_FEO_SERVICES]
    assert any(v["level"] == PEK.LEVEL_CATEGORY for v in services_v), violations
    assert any(v["level"] == PEK.LEVEL_SUBSIDY for v in services_v), violations
    await register_type_excess_approvals(
        db_session, services_v, subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="подготовка теста",
    )
    await db_session.commit()

    blocked = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert blocked.status_code == 409, (
        f"Движение закупки ОБЯЗАНО быть заблокировано, пока превышение по типу "
        f"(услуги) не согласовано: {blocked.status_code} {blocked.text}"
    )
    body = blocked.json()
    assert body.get("code") == "TYPE_EXCESS_PENDING", body
    assert "услуг" in body.get("message", "").lower(), body

    purchase_after = await db_session.get(Purchase, purchase.id)
    assert purchase_after.status == "plan_schedule", "Статус не должен был сдвинуться при 409"

    # Одобряем ОБА независимых запроса (категория + субсидия целиком) через
    # реальный эндпоинт /decide уполномоченным пользователем.
    pending_rows = (await db_session.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.subsidy_id == subsidy.id,
            PlanExcessApproval.kind == PEK.PLAN_OVER_FEO_SERVICES,
            PlanExcessApproval.status == "pending",
        )
    )).scalars().all()
    assert len(pending_rows) == 2, (
        f"Ожидались ДВЕ независимые записи (категория + субсидия), получено {len(pending_rows)}"
    )
    for _appr in pending_rows:
        decide_resp = await client.post(
            f"/api/plan-excess/{_appr.id}/decide",
            json={"decision": "approved"},
            headers=approver_headers,
        )
        assert decide_resp.status_code == 200, decide_resp.text
        assert decide_resp.json()["status"] == "approved"

    allowed = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert allowed.status_code == 200, (
        f"После одобрения ОБОИХ превышений по типу движение закупки обязано быть "
        f"разрешено: {allowed.status_code} {allowed.text}"
    )
    purchase_final = await db_session.get(Purchase, purchase.id)
    assert purchase_final.status == "work_in_progress"


@pytest.mark.asyncio
async def test_no_approver_falls_back_to_hard_block_not_silent_pass(
    client, db_session, test_org, test_admin_user, admin_headers,
):
    """Без единого уполномоченного ('plan_excess.decide') — переход остаётся
    заблокирован 409 (превышение по типу не проходит молча)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    await _make_planned_items(db_session, cat.id)
    await _make_ceiling_headroom_category(db_session, subsidy.id)
    purchase = await _make_purchase_in_plan_schedule(db_session, subsidy.id, cat.id)

    resp = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert resp.status_code == 409, (
        f"Без уполномоченного согласовать превышение по типу некому — переход "
        f"ОБЯЗАН остаться заблокированным: {resp.status_code} {resp.text}"
    )
