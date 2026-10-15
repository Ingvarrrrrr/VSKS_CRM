"""Задача владельца (15.10.2026): субсидия «ФАДМ 2026_3» — «Запланировано»
15 920 830 > «Бюджет (ФЭО)» 15 880 100, хотя жёсткий потолок субсидии
(PLAN_OVER_SUBSIDY_CEILING, app.services.subsidy_ceiling, перенесено из
app.services.feo_plan_excess.assert_no_unapproved_excess) по задумке «не
согласуется ни при каких обстоятельствах». Владелец в тот же день согласовал
превышение вида «услуги» 40 730 — ручная ручка согласования
(app.routers.plan_excess: POST "" и POST "/{id}/decide") потолок не
проверяла вовсе.

Проверяет:
  (а) план субсидии > потолка ФЭО -> POST /api/plan-excess (ручной запрос
      старого вида over_feo) -> 409 PLAN_OVER_SUBSIDY_CEILING;
  (б) перекос ОДНОЙ ветки (план узла > её ФЭО), но суммарно по субсидии ещё
      есть запас (другая ветка с большим ФЭО и малым планом) -> 201, запрос
      создаётся как раньше (жёсткий потолок не блокирует одиночный перекос
      ветки — решение владельца 2026-09-03, см. docstring
      assert_no_unapproved_excess);
  (в) decide approve по уже существующему pending-запросу, когда план
      субсидии (ПОСЛЕ создания запроса, другой веткой) стал выше потолка ->
      409 PLAN_OVER_SUBSIDY_CEILING — отклонение (reject) в этой же ситуации
      НЕ блокируется (план не растёт).

Вызываем роутер напрямую как async-функцию (current_user/db переданы явно,
минуя Depends) — тот же приём, что и tests/test_plan_excess_type_kinds.py.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ."""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride
from app.services import plan_excess_kinds as PEK
from app.routers.plan_excess import request_plan_excess_approval, decide_plan_excess_step


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"CeilingGate-Subsidy-{uuid.uuid4().hex[:8]}",
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
    from app.models.feo_planned_item import FeoPlannedItem
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


async def _make_approver(db_session, test_org, make_user):
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


@pytest.mark.asyncio
async def test_request_blocked_when_subsidy_plan_over_ceiling(db_session, test_org, test_admin_user, make_user):
    """(а) Одна категория, ФЭО-бюджет 100, план 150 (over_feo excess=50) —
    план субсидии (150) уже выше её единственного потолка (100). Ручной
    запрос согласования (kind=over_feo по умолчанию, приоритет) обязан
    получить 409 PLAN_OVER_SUBSIDY_CEILING ДО создания PlanExcessApproval."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_approver(db_session, test_org, make_user)
    cat = await _make_category(db_session, subsidy.id, name="Единственная категория", budget=Decimal("100"))
    await _make_planned_item(db_session, cat.id, amount=150)

    with pytest.raises(HTTPException) as exc_info:
        await request_plan_excess_approval(
            body={"feo_category_id": cat.id},
            db=db_session, current_user=test_admin_user,
        )
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict), detail
    assert detail["code"] == "PLAN_OVER_SUBSIDY_CEILING", detail


@pytest.mark.asyncio
async def test_request_allowed_when_branch_skewed_but_subsidy_has_room(db_session, test_org, test_admin_user, make_user):
    """(б) Две категории: «узкая» (ФЭО 100, план 150 — перекос 50) и
    «широкая» (ФЭО 1000, план 0 — запас). Суммарно по субсидии план (150) <=
    потолок (1100) — перекос ОДНОЙ ветки не блокирует, запрос создаётся
    (201), как и до этой правки (решение владельца 2026-09-03)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_approver(db_session, test_org, make_user)
    cat_narrow = await _make_category(db_session, subsidy.id, name="Узкая ветка", budget=Decimal("100"))
    await _make_planned_item(db_session, cat_narrow.id, amount=150)
    await _make_category(db_session, subsidy.id, name="Широкая ветка (запас)", budget=Decimal("1000"))

    resp = await request_plan_excess_approval(
        body={"feo_category_id": cat_narrow.id},
        db=db_session, current_user=test_admin_user,
    )
    assert resp["excess_kind"] == PEK.OVER_FEO
    assert resp["feo_category_id"] == cat_narrow.id
    assert resp["status"] == "pending"


@pytest.mark.asyncio
async def test_decide_approve_blocked_when_subsidy_plan_over_ceiling(db_session, test_org, test_admin_user, make_user):
    """(в) Запрос создаётся, пока субсидия ЕЩЁ в пределах потолка (как в
    тесте (б)), но ДО решения другая ветка догружается планом так, что
    субсидия в целом выходит за потолок. decide(approved) по уже
    существующему pending-запросу обязан получить 409
    PLAN_OVER_SUBSIDY_CEILING (план не должен «тихо» согласоваться, пока
    субсидия над потолком — ровно сценарий владельца 15.10.2026: согласовал
    превышение «услуги», хотя план субсидии уже был выше ФЭО)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    approver = await _make_approver(db_session, test_org, make_user)
    cat_narrow = await _make_category(db_session, subsidy.id, name="Узкая ветка", budget=Decimal("100"))
    await _make_planned_item(db_session, cat_narrow.id, amount=150)
    cat_wide = await _make_category(db_session, subsidy.id, name="Широкая ветка", budget=Decimal("1000"))

    resp = await request_plan_excess_approval(
        body={"feo_category_id": cat_narrow.id},
        db=db_session, current_user=test_admin_user,
    )
    approval_id = resp["id"]

    # Догружаем «широкую» ветку планом так, что субсидия в целом выходит за
    # потолок (100 + 1000 = 1100; план становится 150 + 1000 = 1150 > 1100).
    await _make_planned_item(db_session, cat_wide.id, amount=1000)

    with pytest.raises(HTTPException) as exc_info:
        await decide_plan_excess_step(
            approval_id=approval_id,
            body={"decision": "approved"},
            db=db_session, current_user=approver,
        )
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict), detail
    assert detail["code"] == "PLAN_OVER_SUBSIDY_CEILING", detail

    # Отклонение (reject) в ЭТОЙ ЖЕ ситуации НЕ блокируется — план не растёт
    # от отказа, только approve проходит жёсткий потолок (см. docstring).
    reject_result = await decide_plan_excess_step(
        approval_id=approval_id,
        body={"decision": "rejected"},
        db=db_session, current_user=approver,
    )
    assert reject_result["status"] == "rejected", reject_result
