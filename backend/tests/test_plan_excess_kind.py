"""Задача владельца (план ancient-prancing-music.md, раздел D, 2026-09-21):
согласования превышения плана по РАЗНЫМ видам (kind) и уровням (level) теперь
независимы — раньше ОДНО approved-решение по категории (latest_approval_by_cat
в app.services.feo_plan_tree, ДО этой задачи) гасило все три старых вида узла
(over_feo/fact_over_plan/plan_over_manual) сразу.

Проверяет:
  (1) старая (legacy, kind='legacy' по умолчанию) approved-запись ПРОДОЛЖАЕТ
      гасить любой из трёх старых видов узла — обратная совместимость с
      записями, заведёнными до миграции g5h7j9k1m3n5.
  (2) approved-запись kind='fact_over_plan' НЕ гасит kind='over_feo' того же
      узла (та же логика для plan_over_manual, не проверяется отдельным
      тестом — общий код app.services.feo_plan_tree._latest_approval).
  (3) запись уровня субсидии (feo_category_id=NULL, level='subsidy')
      создаётся и читается через app.routers.plan_excess._load_approval/
      _approval_dict — level/kind_label в ответе соответствуют
      app.services.plan_excess_kinds.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ (pytest tests/test_plan_excess_kind.py::<name>), как и
соседние test_excess_total_not_per_branch.py/test_plan_excess_approvers.py.
"""
import uuid
from decimal import Decimal

import pytest

from app.models.plan_excess_approval import PlanExcessApproval
from app.services import plan_excess_kinds as PEK
from app.services.feo_plan_tree import compute_feo_plan_tree


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"PlanExcessKind-Subsidy-{uuid.uuid4().hex[:8]}",
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


async def _make_planned_item(db_session, feo_category_id, amount, quantity=1, name="Позиция плана", is_active=True):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        is_active=is_active,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_over_feo_and_fact_node(db_session, subsidy_id):
    """Узел (plan_source='planned_items', умолчание — БЕЗ ручного переключателя,
    чтобы plan_over_manual не участвовал и не мешал формуле full_display) с ДВУМЯ
    ОДНОВРЕМЕННЫМИ видами превышения: over_feo (план 50 > бюджет 30) и
    fact_over_plan (факт 80 > план 50)."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    cat = await _make_category(
        db_session, subsidy_id, name="Узел — over_feo + fact_over_plan",
        budget=Decimal("30"),
    )
    fpi = await _make_planned_item(db_session, cat.id, amount=50)

    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=cat.id,
        item_name="Факт дороже плана",
        status="work_in_progress",
        contract_price=Decimal("80"),
        planned_total_price=Decimal("50"),
        total_nmck=Decimal("50"),
        nmck=Decimal("50"),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Факт дороже плана",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal("50"),
        total_price=Decimal("50"),
        feo_category_id=cat.id,
        feo_planned_item_id=fpi.id,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    return cat


async def _make_plan_over_manual_node(db_session, subsidy_id):
    """Узел (plan_source='manual_sum') с ЕДИНСТВЕННЫМ видом превышения —
    plan_over_manual (Σ позиций 200 > ручной план 50). budget заведомо большой,
    чтобы over_feo не поднимался и не мешал изолированной проверке."""
    cat = await _make_category(
        db_session, subsidy_id, name="Узел — только plan_over_manual",
        budget=Decimal("1000000"),
        plan_source="manual_sum",
        manual_plan_amount=Decimal("50"),
    )
    await _make_planned_item(db_session, cat.id, amount=200)
    return cat


@pytest.mark.asyncio
async def test_legacy_approved_quenches_all_three_old_kinds(db_session, test_org):
    """(1) ОДНА legacy approved-запись (kind не передан → default 'legacy')
    гасит любой из трёх старых видов узла — как и раньше, ДО разделения по
    видам. Проверено на ДВУХ узлах: (а) over_feo + fact_over_plan
    одновременно на одном узле, (б) plan_over_manual изолированно (его
    approve меняет саму формулу plan_manual, поэтому проверяется отдельным
    узлом, чтобы не исказить (а))."""
    subsidy = await _make_subsidy(db_session, test_org.id)

    # (а) over_feo + fact_over_plan.
    cat_ab = await _make_over_feo_and_fact_node(db_session, subsidy.id)
    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat_ab.id]
    assert node["excess_amount"] == pytest.approx(20.0), node
    assert node["excess_fact_over_plan"] == pytest.approx(30.0), node
    assert not node["excess_approved"]
    assert not node["excess_fact_approved"]

    approval_ab = PlanExcessApproval(
        feo_category_id=cat_ab.id,
        subsidy_id=subsidy.id,
        excess_amount=Decimal("20"),
        status="approved",
        mode="sequential",
    )
    db_session.add(approval_ab)
    await db_session.commit()
    assert approval_ab.kind == PEK.LEGACY, "kind обязан выставиться по умолчанию в 'legacy'"

    tree2 = await compute_feo_plan_tree(db_session, [subsidy.id])
    node2 = tree2[cat_ab.id]
    assert node2["excess_approved"], "legacy approved обязана гасить over_feo"
    assert node2["excess_fact_approved"], "legacy approved обязана гасить fact_over_plan"

    # (б) plan_over_manual, отдельный узел.
    cat_c = await _make_plan_over_manual_node(db_session, subsidy.id)
    tree_c = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_c = tree_c[cat_c.id]
    assert node_c["excess_plan_over_manual"] == pytest.approx(150.0), node_c
    assert not node_c["excess_plan_approved"]

    approval_c = PlanExcessApproval(
        feo_category_id=cat_c.id,
        subsidy_id=subsidy.id,
        excess_amount=Decimal("150"),
        status="approved",
        mode="sequential",
    )
    db_session.add(approval_c)
    await db_session.commit()
    assert approval_c.kind == PEK.LEGACY

    tree_c2 = await compute_feo_plan_tree(db_session, [subsidy.id])
    node_c2 = tree_c2[cat_c.id]
    assert node_c2["excess_plan_approved"], "legacy approved обязана гасить plan_over_manual"


@pytest.mark.asyncio
async def test_approved_fact_over_plan_does_not_quench_over_feo(db_session, test_org):
    """(2) approved-запись kind='fact_over_plan' на узле с ОБОИМИ видами
    превышения (over_feo и fact_over_plan) гасит ТОЛЬКО fact_over_plan —
    over_feo остаётся неодобренным (независимые согласования по видам)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_over_feo_and_fact_node(db_session, subsidy.id)

    approval = PlanExcessApproval(
        feo_category_id=cat.id,
        subsidy_id=subsidy.id,
        kind=PEK.FACT_OVER_PLAN,
        excess_amount=Decimal("30"),
        status="approved",
        mode="sequential",
    )
    db_session.add(approval)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["excess_fact_approved"], "kind='fact_over_plan' approved обязана гасить именно fact_over_plan"
    assert not node["excess_approved"], "over_feo НЕ должен гаситься чужим kind — независимые согласования"
    assert not node["excess_plan_approved"], "plan_over_manual НЕ должен гаситься чужим kind"


@pytest.mark.asyncio
async def test_subsidy_level_record_created_and_read(db_session, test_org):
    """(3) Запись уровня субсидии (feo_category_id=NULL) — создаётся,
    level_for_category_id распознаёт её как 'subsidy', и GET-путь
    (_load_approval + _approval_dict, тот же код, что использует роутер)
    отдаёт kind/kind_label/level корректно."""
    from app.routers.plan_excess import _load_approval, _approval_dict

    subsidy = await _make_subsidy(db_session, test_org.id)

    approval = PlanExcessApproval(
        feo_category_id=None,
        subsidy_id=subsidy.id,
        kind=PEK.OVER_FEO,
        excess_amount=Decimal("1000"),
        status="pending",
        mode="sequential",
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    assert PEK.level_for_category_id(approval.feo_category_id) == PEK.LEVEL_SUBSIDY

    full = await _load_approval(approval.id, db_session)
    assert full.feo_category_id is None
    assert full.subsidy_id == subsidy.id

    d = _approval_dict(full)
    assert d["feo_category_id"] is None
    assert d["level"] == "subsidy"
    assert d["kind"] == PEK.OVER_FEO
    assert d["kind_label"] == PEK.kind_label(PEK.OVER_FEO)
