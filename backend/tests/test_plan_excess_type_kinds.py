"""Задача владельца (2026-09-21): POST /api/plan-excess принимает НОВЫЕ 4 вида
превышения по типу (plan_over_feo_goods/services, fact_over_plan_goods/services,
см. app.services.plan_excess_kinds) вручную — на уровне категории ФЭО
(feo_category_id задан) и на уровне субсидии целиком (feo_category_id=None +
subsidy_id). Роутер НЕ считает суммы сам (ПРАВИЛО №6) — переиспользует
app.services.type_excess_approval.collect_type_excess_violations/
register_type_excess_approvals (см. app.routers.plan_excess._request_type_excess_approval).

Проверяет сценарий владельца:
  категория с ФЭО-строкой услуг 100 и плановой позицией услуг 150 (excess=50):
  (1) POST kind=plan_over_feo_services (feo_category_id=cat.id) -> level=category;
  (2) POST kind=plan_over_feo_goods (тот же узел, товаров нет) -> 409;
  (3) POST kind=plan_over_feo_services, feo_category_id=None + subsidy_id -> level=subsidy;
  (4) повторный такой же POST -> та же запись (pending переиспользуется);
  (5) decide approve по subsidy-level записи не падает (db.get(FeoCategory, None)
      guard, см. decide_plan_excess_step).

Вызываем роутер напрямую как async-функцию (current_user/db переданы явно,
минуя Depends) — тот же приём, что и в tests/test_contract_excess_approval.py,
без настройки HTTP auth headers.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ, как и соседние test_plan_excess_kind.py/test_type_excess_approval.py.
"""
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
        name=f"TypeKindManual-Subsidy-{uuid.uuid4().hex[:8]}",
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


async def _make_planned_item(db_session, feo_category_id, name, amount, item_type, is_feo_breakdown=False, feo_amount=None):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal("1"),
        unit="шт",
        amount=Decimal(str(amount)),
        item_type=item_type,
        is_feo_breakdown=is_feo_breakdown,
        feo_amount=Decimal(str(feo_amount)) if feo_amount is not None else None,
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


async def _make_services_over_feo_node(db_session, subsidy_id):
    """Узел владельца: ФЭО-строка услуг 100, плановая позиция услуг ещё 50
    сверху -> plan_services=150, feo_services=100, excess_plan_over_feo_services=50.
    Товаров на узле нет вовсе -> excess_plan_over_feo_goods=0 (нет нарушения)."""
    cat = await _make_category(db_session, subsidy_id, name="Узел — услуги 150 над ФЭО 100")
    await _make_planned_item(db_session, cat.id, "Услуга (по ФЭО)", 100, "услуга", is_feo_breakdown=True, feo_amount=100)
    await _make_planned_item(db_session, cat.id, "Услуга сверх ФЭО", 50, "услуга")
    return cat


@pytest.mark.asyncio
async def test_manual_request_type_kinds_category_and_subsidy_level(db_session, test_org, test_admin_user, make_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    approver = await _make_approver(db_session, test_org, make_user)
    cat = await _make_services_over_feo_node(db_session, subsidy.id)

    # (1) уровень категории: plan_over_feo_services -> 201, level=category.
    resp = await request_plan_excess_approval(
        body={"kind": PEK.PLAN_OVER_FEO_SERVICES, "feo_category_id": cat.id},
        db=db_session, current_user=test_admin_user,
    )
    assert resp["kind"] == PEK.PLAN_OVER_FEO_SERVICES
    assert resp["kind_label"] == PEK.kind_label(PEK.PLAN_OVER_FEO_SERVICES)
    assert resp["level"] == PEK.LEVEL_CATEGORY
    assert resp["feo_category_id"] == cat.id
    assert resp["excess_kind"] == PEK.PLAN_OVER_FEO_SERVICES
    assert resp["excess_kind_label"] == PEK.kind_label(PEK.PLAN_OVER_FEO_SERVICES)
    assert resp["excess_amount"] == pytest.approx(50.0), resp
    approval_id_cat = resp["id"]

    # (2) тот же узел, вид "товары" — нет типизированного ФЭО по товарам ->
    # collect_type_excess_violations не находит нарушения -> 409.
    with pytest.raises(HTTPException) as exc_info:
        await request_plan_excess_approval(
            body={"kind": PEK.PLAN_OVER_FEO_GOODS, "feo_category_id": cat.id},
            db=db_session, current_user=test_admin_user,
        )
    assert exc_info.value.status_code == 409

    # (3) уровень субсидии целиком: feo_category_id=None + subsidy_id ->
    # level=subsidy (тот же перекос виден в compute_subsidy_type_summary,
    # единственная категория с планом на субсидии).
    resp_subsidy = await request_plan_excess_approval(
        body={"kind": PEK.PLAN_OVER_FEO_SERVICES, "feo_category_id": None, "subsidy_id": subsidy.id},
        db=db_session, current_user=test_admin_user,
    )
    assert resp_subsidy["level"] == PEK.LEVEL_SUBSIDY
    assert resp_subsidy["feo_category_id"] is None
    assert resp_subsidy["id"] != approval_id_cat, "уровень категории и уровень субсидии — РАЗНЫЕ записи"
    approval_id_subsidy = resp_subsidy["id"]

    # (4) повторный такой же запрос -> та же pending-запись, не дубликат.
    resp_subsidy_again = await request_plan_excess_approval(
        body={"kind": PEK.PLAN_OVER_FEO_SERVICES, "feo_category_id": None, "subsidy_id": subsidy.id},
        db=db_session, current_user=test_admin_user,
    )
    assert resp_subsidy_again["id"] == approval_id_subsidy

    # (5) decide approve по subsidy-level записи не должен падать на
    # db.get(FeoCategory, None) (approver — единственный уполномоченный в
    # цепочке, requester test_admin_user исключён как автор запроса).
    decide_result = await decide_plan_excess_step(
        approval_id=approval_id_subsidy,
        body={"decision": "approved"},
        db=db_session,
        current_user=approver,
    )
    assert decide_result["status"] == "approved", decide_result
    assert decide_result["feo_category_id"] is None
    assert decide_result["level"] == PEK.LEVEL_SUBSIDY
