"""Владелец продукта (2026-09-03), дословно: «я просил не с отдельной
категорией жёсткий предел делать, который требовал перераспределения, а со
всем ФЭО суммарно». Уточнение: «Суммарно, но с предупреждением: перебор в
ветке не блокирует, но виден как пометка».

До этой правки app.services.feo_plan.assert_no_unapproved_excess бросала 409
(PLAN_EXCESS_OVER_FEO), если у ЛЮБОГО узла цепочки предков план превышал ЕГО
СОБСТВЕННОЕ финансирование по ФЭО (excess_amount), даже когда суммарно по
всей субсидии есть место в других ветках. Теперь эта проверка ТОЛЬКО собирает
предупреждение (возвращает списком) и не блокирует; единственный оставшийся
безусловный контроль — жёсткий потолок субсидии целиком (PLAN_OVER_SUBSIDY_
CEILING, п.3 задачи владельца от 2026-08-12, «не согласуется ни при каких
обстоятельствах»). Контроль «факт дороже плана» (excess_fact_over_plan) — про
другое (договор дороже плана закупки) и НЕ затронут этой правкой.

Сценарии:
  (а) план ОДНОЙ ветки выше её бюджета, суммарно по ФЭО в пределах потолка →
      действие проходит (409 нет), предупреждение возвращено.
  (б) суммарный план (обе ветки) выше потолка ФЭО → 409 остаётся
      (PLAN_OVER_SUBSIDY_CEILING), даже если у КОНКРЕТНОЙ ветки, для которой
      вызван гейт, собственного excess_amount нет.
  (в) «факт дороже плана» по-прежнему блокирует — эта правка её не задела.
  (г) задача 6 (тот же сеанс, отчёт): assert_tz_not_over_plan (категория в
      режиме plan_source='manual_sum') и compute_feo_plan_tree берут ОДИН и
      тот же план категории — после согласованного excess_plan_over_manual
      обе точки видят выросший Σ FeoPlannedItem, а не застрявшее старое
      ручное число.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ (pytest tests/test_excess_total_not_per_branch.py::<name>).
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.feo_plan import (
    assert_no_unapproved_excess,
    assert_tz_not_over_plan,
    compute_feo_plan_tree,
)


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"ExcessTotal-Subsidy-{uuid.uuid4().hex[:8]}",
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
    """Категория-корень (level=1, без родителя) — так её budget напрямую
    попадает в calculate_budget_from_categories._budget_from_tree (roots)."""
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


@pytest.mark.asyncio
async def test_a_branch_over_budget_alone_does_not_block_within_ceiling(db_session, test_org):
    """(а) catA: план 150 000 против бюджета 100 000 (перекос 50 000). catB: план
    50 000 против бюджета 100 000 (свободно). Суммарно по субсидии: план
    200 000 <= потолок 200 000 (100 000+100 000) — действие ОБЯЗАНО пройти без
    409, а перекос catA обязан вернуться предупреждением."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Ветка A (перебор)", budget=Decimal("100000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Ветка B (свободно)", budget=Decimal("100000"))
    await _make_planned_item(db_session, cat_a.id, amount=150_000)
    await _make_planned_item(db_session, cat_b.id, amount=50_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree[cat_a.id]["excess_amount"] == pytest.approx(50_000.0)
    assert tree[cat_b.id]["excess_amount"] == 0.0

    warnings = await assert_no_unapproved_excess(db_session, cat_a.id)

    assert warnings, "Перекос ветки A обязан вернуться предупреждением"
    w = warnings[0]
    assert w["code"] == "PLAN_EXCESS_OVER_FEO"
    assert w["feo_category_id"] == cat_a.id
    assert w["excess_amount"] == pytest.approx(50_000.0)

    # Ветка B (свободная) без превышения — предупреждений нет, 409 тоже нет.
    warnings_b = await assert_no_unapproved_excess(db_session, cat_b.id)
    assert warnings_b == []


@pytest.mark.asyncio
async def test_b_ceiling_over_total_still_blocks(db_session, test_org):
    """(б) catA план 150 000 (бюджет 100 000, перекос 50 000), catB план
    100 000 (РОВНО в рамках своего бюджета 100 000, у неё самой excess_amount
    == 0). Суммарно 250 000 > потолок 200 000 — 409 PLAN_OVER_SUBSIDY_CEILING
    ОБЯЗАН сработать, даже если вызван для catB, у которой своего перекоса нет."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Ветка A (перебор)", budget=Decimal("100000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Ветка B (в рамках)", budget=Decimal("100000"))
    await _make_planned_item(db_session, cat_a.id, amount=150_000)
    await _make_planned_item(db_session, cat_b.id, amount=100_000)

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert tree[cat_b.id]["excess_amount"] == 0.0, "У catB не должно быть собственного перекоса"

    with pytest.raises(HTTPException) as exc_info:
        await assert_no_unapproved_excess(db_session, cat_b.id)
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "PLAN_OVER_SUBSIDY_CEILING", detail

    # То же самое, если вызвать со стороны catA (обе точки входа видят один
    # и тот же суммарный потолок).
    with pytest.raises(HTTPException) as exc_info_a:
        await assert_no_unapproved_excess(db_session, cat_a.id)
    assert exc_info_a.value.status_code == 409
    assert exc_info_a.value.detail.get("code") == "PLAN_OVER_SUBSIDY_CEILING"


@pytest.mark.asyncio
async def test_c_fact_over_plan_still_blocks(db_session, test_org):
    """(в) «Факт дороже плана» (excess_fact_over_plan) — про другое (договор
    дороже плана закупки), эта правка её НЕ трогала. Плановая позиция
    100 000, закупка на «Ведётся работа» с contract_price 150 000 → 409 с тем
    же текстом/семантикой, что и раньше."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(
        db_session, subsidy.id, name="Ветка — факт дороже плана", budget=Decimal("1000000"),
    )
    fpi = await _make_planned_item(db_session, cat.id, amount=100_000)

    p = Purchase(
        subsidy_id=subsidy.id,
        feo_category_id=cat.id,
        item_name="Договор дороже плана",
        status="work_in_progress",
        contract_price=Decimal("150000"),
        planned_total_price=Decimal("100000"),
        total_nmck=Decimal("100000"),
        nmck=Decimal("100000"),
    )
    db_session.add(p)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=p.id,
        item_name="Договор дороже плана",
        quantity=Decimal("1"),
        unit="шт",
        unit_price=Decimal("100000"),
        total_price=Decimal("100000"),
        feo_category_id=cat.id,
        feo_planned_item_id=fpi.id,
        over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["excess_amount"] == 0.0, "План (100 000) в рамках бюджета (1 000 000) — не должно быть excess_amount"
    assert node["excess_fact_over_plan"] == pytest.approx(50_000.0), (
        f"Факт (150 000 по contract_price) обязан превышать план (100 000): узел={node}"
    )

    with pytest.raises(HTTPException) as exc_info:
        await assert_no_unapproved_excess(db_session, cat.id)
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    text = detail if isinstance(detail, str) else str(detail)
    assert "факт" in text.lower() or "план" in text.lower(), detail


@pytest.mark.asyncio
async def test_d_tz_not_over_plan_matches_compute_feo_plan_tree_for_manual_sum(db_session, test_org):
    """(г) Задача 6: категория plan_source='manual_sum', ручной план 100 000,
    Σ активных FeoPlannedItem 180 000 (превышение 80 000), превышение УЖЕ
    согласовано (PlanExcessApproval.status='approved') → compute_feo_plan_tree
    считает plan_manual==180 000 (Σ позиций, т.к. согласовано). ДО задачи 6
    assert_tz_not_over_plan игнорировал plan_source/manual_plan_amount и брал
    planned_quantity×planned_amount == 100 000 НАВСЕГДА — здесь эти поля
    намеренно выставлены РАВНЫМИ старому ручному числу (100 000), чтобы
    показать: если бы формула не поменялась, 150 000 упёрлось бы в 100 000 и
    бросило 409. После задачи 6 обе точки видят 180 000."""
    from app.models.plan_excess_approval import PlanExcessApproval

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(
        db_session, subsidy.id, name="Категория manual_sum — согласованное превышение",
        budget=Decimal("1000000"),
        plan_source="manual_sum",
        manual_plan_amount=Decimal("100000"),
        planned_quantity=Decimal("1"),
        planned_amount=Decimal("100000"),  # СТАРОЕ поведение держалось бы именно на этом произведении
    )
    await _make_planned_item(db_session, cat.id, amount=180_000)

    approval = PlanExcessApproval(
        feo_category_id=cat.id,
        subsidy_id=subsidy.id,
        excess_amount=Decimal("80000"),
        status="approved",
        mode="sequential",
    )
    db_session.add(approval)
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[cat.id]
    assert node["plan_manual"] == pytest.approx(180_000.0), (
        f"compute_feo_plan_tree обязан видеть согласованное превышение (Σ позиций 180 000), узел={node}"
    )

    # quantity/unit_price ниже переданы РОВНО на границе СТАРЫХ (legacy)
    # planned_quantity=1/planned_amount=100 000 — эти два лимита задача 6
    # СОЗНАТЕЛЬНО не трогала (см. комментарий в feo_plan.py), поэтому тест
    # держит их «непревышенными», чтобы изолированно проверить ИМЕННО СУММУ
    # (total_price передан независимым параметром — assert_tz_not_over_plan
    # принимает quantity/unit_price/total_price как три раздельных аргумента,
    # ровно так их передаёт _tz_check_units из PurchaseItem.total_price,
    # которая не обязана быть произведением qty×price).

    # На границе нового согласованного плана (== 180 000) — ПРОХОДИТ.
    await assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=None,
        feo_category_id=cat.id,
        quantity=Decimal("1"),
        unit_price=Decimal("100000"),
        total_price=Decimal("180000"),
        item_name="ТЗ ровно на границе согласованного плана",
    )

    # Чуть выше согласованного плана (180 000,01) — 409.
    with pytest.raises(HTTPException) as exc_info:
        await assert_tz_not_over_plan(
            db_session,
            feo_planned_item_id=None,
            feo_category_id=cat.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100000"),
            total_price=Decimal("180000.01"),
            item_name="ТЗ чуть выше согласованного плана",
        )
    assert exc_info.value.status_code == 409

    # КЛЮЧЕВОЕ доказательство фикса: сумма 150 000 — выше СТАРОГО потолка
    # (100 000 = planned_quantity×planned_amount старой формулы), но НИЖЕ
    # НОВОГО согласованного плана (180 000 = Σ FeoPlannedItem после approved).
    # ДО задачи 6 это бросило бы 409 (старая формула игнорировала plan_source/
    # approval и держала потолок на 100 000 навсегда); теперь — проходит.
    await assert_tz_not_over_plan(
        db_session,
        feo_planned_item_id=None,
        feo_category_id=cat.id,
        quantity=Decimal("1"),
        unit_price=Decimal("100000"),
        total_price=Decimal("150000"),
        item_name="ТЗ между старым и новым планом — раньше блокировало, теперь нет",
    )
