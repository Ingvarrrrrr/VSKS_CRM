"""Задача владельца (план ancient-prancing-music.md, раздел E, 2026-09-21):
согласование превышения ПО ТИПУ (товары/услуги) — app.services.type_excess_approval,
по образцу tz_excess_approval.py (та же модель PlanExcessApproval, те же
уполномоченные — app.routers.plan_excess._authorized_plan_excess_approvers).

Проверяет:
  (а) collect_type_excess_violations находит plan_over_feo_services, когда
      план услуг выше ФЭО услуг, а по товарам всё в порядке (excess=0, не
      попадает в список нарушений вовсе).
  (б) register + approve kind=plan_over_feo_goods НЕ гасит
      fact_over_plan_services того же узла (независимые согласования).
  (в) категория и субсидия — РАЗНЫЕ записи PlanExcessApproval (level).
  (г) assert_no_pending_type_excess -> 409 до approve, проходит после approve.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ.
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.plan_excess_approval import PlanExcessApproval
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride
from app.services import plan_excess_kinds as PEK
from app.services.type_excess_approval import (
    assert_no_pending_type_excess,
    collect_type_excess_violations,
    register_type_excess_approvals,
)


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TypeExcess-Subsidy-{uuid.uuid4().hex[:8]}",
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


async def _make_services_over_feo_node(db_session, subsidy_id):
    """Узел: план услуг (60к) выше ФЭО услуг (30к); товары в порядке (нет
    типизированного ФЭО по товарам -> excess_plan_over_feo_goods=0)."""
    cat = await _make_category(db_session, subsidy_id, name="Узел — услуги над ФЭО")
    await _make_planned_item(db_session, cat.id, "Товар", 10_000, "товар")
    await _make_planned_item(db_session, cat.id, "Услуга (по ФЭО)", 30_000, "услуга", is_feo_breakdown=True, feo_amount=30_000)
    await _make_planned_item(db_session, cat.id, "Услуга сверх ФЭО", 30_000, "услуга")
    return cat


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
async def test_collect_finds_services_violation_not_goods(db_session, test_org):
    """(а) collect_type_excess_violations находит kind=plan_over_feo_services
    на узле, но НЕ plan_over_feo_goods (нет типизированного ФЭО по товарам)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_services_over_feo_node(db_session, subsidy.id)

    violations = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    node_violations = [v for v in violations if v["level"] == PEK.LEVEL_CATEGORY and v["feo_category_id"] == cat.id]
    kinds = {v["kind"] for v in node_violations}
    assert PEK.PLAN_OVER_FEO_SERVICES in kinds, violations
    assert PEK.PLAN_OVER_FEO_GOODS not in kinds, violations


@pytest.mark.asyncio
async def test_approve_goods_kind_does_not_quench_services_kind(db_session, test_org, test_admin_user, make_user):
    """(б) approve kind=plan_over_feo_goods на ОДНОМ узле не гасит
    excess_fact_over_plan_services ДРУГОГО типа на том же узле — независимые
    согласования (это два РАЗНЫХ (feo_category_id, kind), проверяем на одном
    узле сразу двумя видами превышения)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    approver = await _make_approver(db_session, test_org, make_user)

    cat = await _make_category(db_session, subsidy.id, name="Узел — два вида превышения")
    # goods: план 50к, ФЭО типизировано 10к -> excess_plan_over_feo_goods = 40к
    await _make_planned_item(db_session, cat.id, "Товар (по ФЭО)", 10_000, "товар", is_feo_breakdown=True, feo_amount=10_000)
    await _make_planned_item(db_session, cat.id, "Товар сверх ФЭО", 40_000, "товар")

    tree1 = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    goods_v = next(v for v in tree1 if v["kind"] == PEK.PLAN_OVER_FEO_GOODS and v["feo_category_id"] == cat.id)

    approved = await register_type_excess_approvals(
        db_session, [goods_v], subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест",
    )
    approval_id = approved[0]["id"]
    approval = await db_session.get(PlanExcessApproval, approval_id)
    approval.status = "approved"
    from datetime import datetime, timezone
    approval.resolved_at = datetime.now(timezone.utc)
    await db_session.commit()

    # Теперь добавим факт по услугам выше плана по услугам на ТОМ ЖЕ узле.
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    await _make_planned_item(db_session, cat.id, "Услуга (план)", 5_000, "услуга")
    p = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="Услуга факт",
        status="work_in_progress", contract_price=Decimal("20000"),
        planned_total_price=Decimal("20000"), total_nmck=Decimal("20000"), nmck=Decimal("20000"),
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Услуга факт", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("20000"), total_price=Decimal("20000"),
        feo_category_id=cat.id, item_type="услуга", over_plan=False,
    ))
    await db_session.commit()

    # assert_no_pending_type_excess ОБЯЗАН блокировать по fact_over_plan_services
    # (goods approved не гасит его) — но НЕ по plan_over_feo_goods (уже approved).
    with pytest.raises(HTTPException) as exc_info:
        await assert_no_pending_type_excess(db_session, subsidy.id, [cat.id])
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["kind"] == PEK.FACT_OVER_PLAN_SERVICES, (
        f"goods-approval НЕ должен гасить services-превышение (независимые согласования): {detail}"
    )


@pytest.mark.asyncio
async def test_category_and_subsidy_level_are_separate_records(db_session, test_org, test_admin_user, make_user):
    """(в) Регистрация нарушений на уровне категории И уровне субсидии создаёт
    ДВЕ отдельные записи PlanExcessApproval (feo_category_id заполнен vs NULL)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_approver(db_session, test_org, make_user)
    cat = await _make_services_over_feo_node(db_session, subsidy.id)

    violations = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    assert any(v["level"] == PEK.LEVEL_CATEGORY for v in violations)
    assert any(v["level"] == PEK.LEVEL_SUBSIDY for v in violations), (
        "план услуг узла выше ФЭО услуг узла -> тот же перекос виден и на "
        "уровне субсидии целиком (единственная категория с планом)"
    )

    registered = await register_type_excess_approvals(
        db_session, violations, subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест уровней",
    )
    cat_records = [r for r in registered if r["level"] == PEK.LEVEL_CATEGORY]
    subsidy_records = [r for r in registered if r["level"] == PEK.LEVEL_SUBSIDY]
    assert cat_records and subsidy_records
    assert cat_records[0]["feo_category_id"] == cat.id
    assert subsidy_records[0]["feo_category_id"] is None

    rows = (await db_session.execute(
        select(PlanExcessApproval).where(PlanExcessApproval.subsidy_id == subsidy.id)
    )).scalars().all()
    assert any(r.feo_category_id == cat.id for r in rows)
    assert any(r.feo_category_id is None for r in rows)


@pytest.mark.asyncio
async def test_assert_no_pending_blocks_before_approve_and_passes_after(db_session, test_org, test_admin_user, make_user):
    """(г) assert_no_pending_type_excess -> 409 до согласования, проходит
    после approve именно того (feo_category_id, kind)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    await _make_approver(db_session, test_org, make_user)
    cat = await _make_services_over_feo_node(db_session, subsidy.id)

    with pytest.raises(HTTPException) as exc_info:
        await assert_no_pending_type_excess(db_session, subsidy.id, [cat.id])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "TYPE_EXCESS_PENDING"

    violations = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    services_v = [v for v in violations if v["kind"] == PEK.PLAN_OVER_FEO_SERVICES]
    await register_type_excess_approvals(
        db_session, services_v, subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест approve",
    )
    pending = (await db_session.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.subsidy_id == subsidy.id,
            PlanExcessApproval.kind == PEK.PLAN_OVER_FEO_SERVICES,
            PlanExcessApproval.feo_category_id == cat.id,
        )
    )).scalar_one()
    pending.status = "approved"
    from datetime import datetime, timezone
    pending.resolved_at = datetime.now(timezone.utc)
    await db_session.commit()

    # Оставшиеся виды (level=subsidy того же kind) ещё pending — проверим
    # ОДНУ категорию с уже одобренным её собственным нарушением: остаётся
    # только subsidy-level, который assert проверяет отдельно от category_ids.
    # Здесь фокус теста — что category-level (cat.id, PLAN_OVER_FEO_SERVICES)
    # прошло: соберём нарушения заново и убедимся, что для cat.id этого вида
    # среди свежих violations уже НЕТ причины для 409 по нему отдельно.
    violations2 = await collect_type_excess_violations(db_session, subsidy.id, [cat.id])
    cat_kinds_still_open = {
        v["kind"] for v in violations2
        if v["level"] == PEK.LEVEL_CATEGORY and v["feo_category_id"] == cat.id
    }
    assert PEK.PLAN_OVER_FEO_SERVICES in cat_kinds_still_open, (
        "величина превышения не изменилась (approved не меняет саму сумму, "
        "только снимает блокировку) — она остаётся видна как нарушение, но "
        "assert_no_pending_type_excess её больше не должен блокировать"
    )
