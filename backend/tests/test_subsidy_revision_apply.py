# -*- coding: utf-8 -*-
"""Корректировка утверждённой субсидии через проверку, волна 3A (02.10.2026):
тесты subsidy_revision_apply.decide_and_apply — применение решения
проверяющего. Вызывает сервисы НАПРЯМУЮ (минуя HTTP/роутер — права доступа
проверяет роутер, см. test_subsidy_revision_ops.py).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.entity_change import EntityChange
from app.models.plan_graph_version import PlanGraphVersion
from app.services import subsidy_revision_ops as ops_svc
from app.services.subsidy_revision_apply import decide_and_apply


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    subsidy = Subsidy(
        name=f"RevApplyTest-{uuid.uuid4().hex[:8]}", year=2026,
        org_id=org_id, status="approved", budget=budget,
    )
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def _make_category(db_session, subsidy_id, name="Категория", **kw):
    cat = FeoCategory(subsidy_id=subsidy_id, level=1, name=name, **kw)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_item(db_session, cat_id, name="Позиция", amount=1000, quantity=1, unit_price=1000):
    item = FeoPlannedItem(
        feo_category_id=cat_id, name=name, amount=amount, quantity=quantity,
        unit_price=unit_price, unit="шт", is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.fixture
def revision_user(test_user):
    return test_user


@pytest.fixture
def reviewer_user(test_admin_user):
    return test_admin_user


async def _submit(db_session, revision):
    from datetime import datetime, timezone
    revision.status = "submitted"
    revision.submitted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(revision)


# ── Отклонение статьи -> её строки auto_rejected ────────────────────────────

@pytest.mark.asyncio
async def test_reject_category_auto_rejects_dependent_item(db_session, test_org, revision_user, reviewer_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    cat_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "create", "after": {"name": "Новая статья"},
    })
    item_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "create", "parent_ref": "c1",
        "after": {"name": "Новая позиция", "amount": 500},
    })
    await _submit(db_session, revision)

    result = await decide_and_apply(
        db_session, revision, reviewer_user,
        decisions={cat_op.id: {"decision": "reject", "comment": "не нужно"}},
    )
    assert cat_op.id in result["rejected"]
    assert item_op.id in result["auto_rejected"]

    await db_session.refresh(item_op)
    assert item_op.status == "auto_rejected"
    assert "№" in (item_op.review_comment or "")


# ── Частичное утверждение: source='revision' + ОДНА новая PlanGraphVersion ──

@pytest.mark.asyncio
async def test_partial_accept_writes_revision_source_and_one_plan_version(
    db_session, test_org, revision_user, reviewer_user,
):
    from sqlalchemy import select, func

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=10000)
    item = await _make_item(db_session, cat.id, amount=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    op_budget = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 20000},
    })
    op_item = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "field_group": "qty_price", "after": {"amount": 2000},
    })
    await _submit(db_session, revision)

    version_count_before = (await db_session.execute(
        select(func.count()).select_from(PlanGraphVersion).where(PlanGraphVersion.subsidy_id == subsidy.id)
    )).scalar()

    # Решаем ТОЛЬКО одну строку — корректировка должна остаться partially_decided.
    result = await decide_and_apply(
        db_session, revision, reviewer_user,
        decisions={op_budget.id: {"decision": "accept"}},
    )
    assert result["revision_status"] == "partially_decided"

    await db_session.refresh(cat)
    assert float(cat.budget) == 20000

    changes = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == "feo_category", EntityChange.entity_id == cat.id,
            EntityChange.source == "revision",
        )
    )).scalars().all()
    assert len(changes) >= 1

    version_count_after = (await db_session.execute(
        select(func.count()).select_from(PlanGraphVersion).where(PlanGraphVersion.subsidy_id == subsidy.id)
    )).scalar()
    assert version_count_after == version_count_before + 1

    # Решаем оставшуюся строку — корректировка закрывается.
    await db_session.refresh(revision)
    result2 = await decide_and_apply(
        db_session, revision, reviewer_user,
        decisions={op_item.id: {"decision": "accept"}},
    )
    assert result2["revision_status"] == "closed"

    version_count_final = (await db_session.execute(
        select(func.count()).select_from(PlanGraphVersion).where(PlanGraphVersion.subsidy_id == subsidy.id)
    )).scalar()
    assert version_count_final == version_count_before + 2  # по одной версии на КАЖДЫЙ проход apply


# ── Stale -> 409, force -> применяется ──────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_before_blocks_apply_unless_forced(db_session, test_org, revision_user, reviewer_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=10000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 20000},
    })
    await _submit(db_session, revision)

    # Кто-то другой поменял budget напрямую ПОСЛЕ того, как строка была
    # добавлена (before снимок устарел).
    cat.budget = 15000
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await decide_and_apply(db_session, revision, reviewer_user, decisions={op.id: {"decision": "accept"}})
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "stale"

    await db_session.refresh(revision)
    result = await decide_and_apply(
        db_session, revision, reviewer_user,
        decisions={op.id: {"decision": "accept"}}, force=True,
    )
    assert result["revision_status"] == "closed"
    await db_session.refresh(cat)
    assert float(cat.budget) == 20000


# ── Предпросмотр «after» после применения совпадает с живым деревом ────────

@pytest.mark.asyncio
async def test_preview_after_matches_live_tree_post_apply(db_session, test_org, revision_user, reviewer_user):
    from app.services.subsidy_revision_preview import preview
    from app.services.feo_plan_tree import compute_feo_plan_tree

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=10000)
    item = await _make_item(db_session, cat.id, amount=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "field_group": "qty_price", "after": {"amount": 4000},
    })

    preview_result = await preview(db_session, revision)
    predicted_display = preview_result["after"]["nodes"][cat.id]["display"]

    await _submit(db_session, revision)
    await decide_and_apply(db_session, revision, reviewer_user, decisions={op.id: {"decision": "accept"}})

    live_tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    assert live_tree[cat.id]["display"] == pytest.approx(predicted_display, abs=0.01)
    assert live_tree[cat.id]["display"] == pytest.approx(4000, abs=0.01)


# ── include_before=False: "before" отдаётся null, "after"/balance те же ────

@pytest.mark.asyncio
async def test_preview_include_before_false_skips_before_block(db_session, test_org, revision_user):
    from app.services.subsidy_revision_preview import preview

    subsidy = await _make_subsidy(db_session, test_org.id, budget=10000)
    cat = await _make_category(db_session, subsidy.id, budget=10000)
    item = await _make_item(db_session, cat.id, amount=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "field_group": "qty_price", "after": {"amount": 4000},
    })

    full = await preview(db_session, revision, include_before=True)
    fast = await preview(db_session, revision, include_before=False)

    assert full["before"] is not None
    assert fast["before"] is None
    # "after"/баланс не зависят от include_before — одно и то же решение.
    assert fast["after"]["nodes"][cat.id]["display"] == pytest.approx(
        full["after"]["nodes"][cat.id]["display"], abs=0.01
    )
    assert fast["balance"]["free_before"] == pytest.approx(full["balance"]["free_before"], abs=0.01)
    assert fast["can_apply"] == full["can_apply"]


# ── Принять дочернюю без принятого родителя -> 422 ──────────────────────────

@pytest.mark.asyncio
async def test_accept_child_without_parent_is_422(db_session, test_org, revision_user, reviewer_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    cat_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "create", "after": {"name": "Статья"},
    })
    item_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "create", "parent_ref": "c1",
        "after": {"name": "Позиция", "amount": 500},
    })
    await _submit(db_session, revision)

    with pytest.raises(HTTPException) as exc_info:
        await decide_and_apply(
            db_session, revision, reviewer_user,
            decisions={item_op.id: {"decision": "accept"}},  # без cat_op
        )
    assert exc_info.value.status_code == 422


# ── IDOR: extra_ops проверяющего не смеет трогать сущность чужой субсидии ───

@pytest.mark.asyncio
async def test_reviewer_extra_op_targeting_other_subsidy_item_is_404(
    db_session, test_org, revision_user, reviewer_user,
):
    """Проверяющий во время разбора корректировки субсидии A добавляет
    extra_op с target_id плановой позиции из субсидии B (например подставив
    чужой id вручную) — 404 entity_not_in_subsidy, позиция B не меняется."""
    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    cat_b = await _make_category(db_session, subsidy_b.id)
    item_b = await _make_item(db_session, cat_b.id, amount=1000)

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy_a.id)
    await _submit(db_session, revision)

    with pytest.raises(HTTPException) as exc_info:
        await decide_and_apply(
            db_session, revision, reviewer_user,
            decisions={},
            extra_ops=[{
                "entity_type": "feo_item", "op_type": "update", "target_id": item_b.id,
                "field_group": "qty_price", "after": {"amount": 9999},
            }],
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "entity_not_in_subsidy"

    await db_session.refresh(item_b)
    assert float(item_b.amount) == 1000  # не тронута


@pytest.mark.asyncio
async def test_apply_ops_rejects_target_id_moved_out_of_subsidy_between_add_and_apply(
    db_session, test_org, revision_user,
):
    """Повторная проверка в apply_ops: категория была В субсидии в момент
    add_op, но к моменту apply переехала в другую субсидию (например другой
    корректировкой) — apply_ops обязан отказать, а не переписать чужую
    категорию по старому target_id."""
    from app.services.subsidy_revision_apply import apply_ops

    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy_a.id, budget=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy_a.id)

    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 5000},
    })

    # Категорию "перенесли" в другую субсидию между добавлением строки и apply.
    cat.subsidy_id = subsidy_b.id
    await db_session.commit()

    result = await apply_ops(db_session, revision_user, subsidy_a.id, [op])
    assert result["problems"] and result["problems"][0]["code"] == "entity_not_in_subsidy"

    await db_session.refresh(cat)
    assert float(cat.budget) == 1000  # не перезаписана
