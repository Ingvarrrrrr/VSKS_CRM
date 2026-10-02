# -*- coding: utf-8 -*-
"""Корректировка утверждённой субсидии через проверку, волна 3A (02.10.2026):
сервис-уровневые тесты subsidy_revision_ops.py (сбор/склейка строк, simulate)
и subsidy_revision_floor.py (порог «не ниже законтрактованного», баланс
связок). Вызывает сервисы НАПРЯМУЮ (минуя HTTP/роутер — права доступа
проверяет роутер, это не предмет этого файла, по образцу
test_feo_item_write_wish_path.py).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services import subsidy_revision_ops as ops_svc
from app.services.subsidy_revision_apply import apply_ops
from app.services.subsidy_revision_floor import check_floor, compute_balance


async def _make_subsidy(db_session, org_id, budget=0):
    subsidy = Subsidy(
        name=f"RevOpsTest-{uuid.uuid4().hex[:8]}", year=2026,
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


async def _commit_item(db_session, subsidy_id, item, amount, quantity=1):
    """Делает плановую позицию «законтрактованной» на `amount` — закупка в
    статусе 'contracted' (committed_status_predicate), contract_price = amount,
    одна позиция total_price = amount -> committed_by_planned_item вернёт
    ровно {amount, quantity} (ratio=1, items_count=1, не framework)."""
    purchase = Purchase(subsidy_id=subsidy_id, status="contracted", contract_price=amount)
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    pi = PurchaseItem(
        purchase_id=purchase.id, item_name=item.name, quantity=quantity,
        total_price=amount, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    return purchase


@pytest.fixture
def revision_user(test_user):
    return test_user


@pytest.fixture
def reviewer_user(test_admin_user):
    return test_admin_user


# ── Склейка повторной правки ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_repeated_edit_same_field_group_merges_into_one_row(db_session, test_org, revision_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=1000)

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op1 = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 2000},
    })
    assert op1 is not None
    op2 = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 3000},
    })
    assert op2.id == op1.id  # слито в ту же строку
    assert op2.after["budget"] == 3000
    assert op2.before["budget"] == 1000  # before — исходное значение, не промежуточное

    await db_session.refresh(revision)
    assert len(await ops_svc.load_ops(db_session, revision.id)) == 1


@pytest.mark.asyncio
async def test_edit_back_to_original_value_removes_row(db_session, test_org, revision_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 2000},
    })
    assert op is not None
    back = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "update", "target_id": cat.id,
        "field_group": "funding", "after": {"budget": 1000},
    })
    assert back is None
    await db_session.refresh(revision)
    assert len(await ops_svc.load_ops(db_session, revision.id)) == 0


# ── Приёмка 02.10.2026, п.1: паразитная строка 'meta' на каждую правку суммы ─

@pytest.mark.asyncio
async def test_edit_only_amount_full_after_creates_single_qty_price_row(db_session, test_org, revision_user):
    """Диалог правки позиции шлёт ПОЛНЫЙ набор полей (как при прямой правке —
    см. useFeoPlannedItemEditDialog.ts::saveEditPlannedItem), из которых
    реально изменилась только сумма. Раньше это рождало ещё и строку 'meta'
    вида "Наименование: X → —; Активна: да → —; is_feo_breakdown: да → —"
    (before грузился ЦЕЛИКОМ по группе, after нёс лишь часть полей) — теперь
    строка ровно одна (qty_price), before/after несут ТОЛЬКО amount."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_item(db_session, cat.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    full_after = {
        "feo_category_id": item.feo_category_id,
        "name": item.name,
        "quantity": float(item.quantity),
        "unit": item.unit,
        "amount": 2000,  # единственное реально меняющееся поле
        "unit_price": float(item.unit_price),
        "notes": item.notes,
        "is_active": item.is_active,
        "payment_mode": item.payment_mode,
        "planned_date": item.planned_date,
        "monthly_start_date": item.monthly_start_date,
        "monthly_end_date": item.monthly_end_date,
        "months_count": item.months_count,
        "monthly_amount": item.monthly_amount,
        "item_type": item.item_type,
        "is_feo_breakdown": item.is_feo_breakdown,
        "is_internal_plan": item.is_internal_plan,
        "is_composite": item.is_composite,
        "feo_quantity": item.feo_quantity,
        "feo_unit_price": item.feo_unit_price,
        "feo_amount": item.feo_amount,
        "sort_order": item.sort_order,
    }

    result = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "after": full_after,
    })

    assert result is not None and not isinstance(result, list)
    assert result.field_group == "qty_price"
    assert list(result.after.keys()) == ["amount"]
    assert result.after["amount"] == 2000
    assert list(result.before.keys()) == ["amount"]
    assert float(result.before["amount"]) == pytest.approx(1000)

    await db_session.refresh(revision)
    all_ops = await ops_svc.load_ops(db_session, revision.id)
    assert len(all_ops) == 1  # НЕ ещё и 'meta'/'structure'


# ── Новая позиция внутри новой статьи (метки) ───────────────────────────────

@pytest.mark.asyncio
async def test_new_item_inside_new_category_applies_via_refs(db_session, test_org, revision_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    cat_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "create",
        "after": {"name": "Новая статья", "budget": 5000},
    })
    assert cat_op.target_ref == "c1"

    item_op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "create", "parent_ref": "c1",
        "after": {"name": "Новая позиция", "amount": 4000, "quantity": 2, "unit_price": 2000},
    })
    assert item_op.target_ref == "i1"
    assert item_op.depends_on_op_id == cat_op.id

    await db_session.refresh(revision)
    all_ops = await ops_svc.load_ops(db_session, revision.id)
    result = await apply_ops(db_session, revision_user, subsidy.id, all_ops)
    assert result["problems"] == []
    new_cat_id = result["ref_map"]["c1"]
    new_item_id = result["ref_map"]["i1"]

    created_cat = await db_session.get(FeoCategory, new_cat_id)
    created_item = await db_session.get(FeoPlannedItem, new_item_id)
    assert created_cat is not None and created_cat.name == "Новая статья"
    assert created_item is not None and created_item.feo_category_id == new_cat_id
    assert float(created_item.amount) == 4000


# ── Удаление созданной в этой же корректировке сущности — каскад ───────────

@pytest.mark.asyncio
async def test_delete_created_category_cascades_dependents(db_session, test_org, revision_user):
    subsidy = await _make_subsidy(db_session, test_org.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "create", "after": {"name": "Статья"},
    })
    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "create", "parent_ref": "c1",
        "after": {"name": "Позиция", "amount": 100},
    })
    await db_session.refresh(revision)
    assert len(await ops_svc.load_ops(db_session, revision.id)) == 2

    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "delete", "target_ref": "c1",
    })
    await db_session.refresh(revision)
    assert len(await ops_svc.load_ops(db_session, revision.id)) == 0


# ── simulate() ничего не пишет в БД ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_simulate_does_not_persist_changes(db_session, test_org, revision_user):
    from sqlalchemy import select, func

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, budget=1000)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_category", "op_type": "create", "parent_ref": None,
        "after": {"name": "Новая статья от simulate"},
    })
    await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "create", "parent_ref": "c1",
        "after": {"name": "Позиция от simulate", "amount": 500},
    })

    cat_count_before = (await db_session.execute(
        select(func.count()).select_from(FeoCategory).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalar()
    item_count_before = (await db_session.execute(
        select(func.count()).select_from(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy.id)
    )).scalar()

    await db_session.refresh(revision)
    sim = await ops_svc.simulate(db_session, revision)
    assert sim["problems"] == []
    assert "c1" in sim["ref_map"]

    cat_count_after = (await db_session.execute(
        select(func.count()).select_from(FeoCategory).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalar()
    item_count_after = (await db_session.execute(
        select(func.count()).select_from(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy.id)
    )).scalar()

    assert cat_count_before == cat_count_after
    assert item_count_before == item_count_after


# ── check_floor: ниже законтрактованного ────────────────────────────────────

@pytest.mark.asyncio
async def test_check_floor_flags_amount_below_committed(db_session, test_org, revision_user):
    from app.services.feo_plan_tree import compute_feo_plan_tree

    subsidy = await _make_subsidy(db_session, test_org.id, budget=200000)
    cat = await _make_category(db_session, subsidy.id, budget=100000)
    item = await _make_item(db_session, cat.id, amount=100000, quantity=10, unit_price=10000)
    await _commit_item(db_session, subsidy.id, item, amount=85000, quantity=8)

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "field_group": "qty_price", "after": {"amount": 50000},
    })
    assert op is not None

    tree_after = await compute_feo_plan_tree(db_session, [subsidy.id])
    problems = await check_floor(db_session, subsidy.id, [op], tree_after)
    assert any(p["code"] == "below_committed" and p["field"] == "amount" for p in problems)
    below = next(p for p in problems if p["field"] == "amount")
    assert below["committed"] == pytest.approx(85000, abs=1)
    assert "законтрактован" in below["message"].lower()


# ── compute_balance: контрольный сценарий владельца (ложки/чашки/вилки/ножи) ─
#
# Ложки +100000 (в одной связке с чашками/вилками), чашки -50000, вилки -50000.
# "Ножи -50000" из формулировки владельца — третья позиция, уменьшающая план на
# ту же сумму, что и вилки здесь (роль эквивалентна: ещё одна строка связки,
# высвобождающая 50000) — используем уже заведённую `forks`, вторую такую же
# позицию не заводим (ПРАВИЛО №6, не плодить эквивалентные фикстуры).

@pytest.mark.asyncio
async def test_balance_bundle_scenario_free_zero(db_session, test_org, revision_user):
    from app.services.feo_plan_tree import compute_feo_plan_tree

    subsidy = await _make_subsidy(db_session, test_org.id, budget=300000)
    cat = await _make_category(db_session, subsidy.id)
    spoons = await _make_item(db_session, cat.id, name="Ложки", amount=100000, quantity=1, unit_price=100000)
    cups = await _make_item(db_session, cat.id, name="Чашки", amount=100000, quantity=1, unit_price=100000)
    forks = await _make_item(db_session, cat.id, name="Вилки", amount=100000, quantity=1, unit_price=100000)
    # Бюджет (300000) == план (100000×3 = 300000) -> free = 0.

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op_spoons = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": spoons.id,
        "field_group": "qty_price", "after": {"amount": 200000}, "bundle_no": 1,
    })
    op_cups = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": cups.id,
        "field_group": "qty_price", "after": {"amount": 50000}, "bundle_no": 1,
    })
    op_forks = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": forks.id,
        "field_group": "qty_price", "after": {"amount": 50000}, "bundle_no": 1,
    })

    tree_before = await compute_feo_plan_tree(db_session, [subsidy.id])

    async def _balance_for(ops, reviewer_overrides=None):
        nested = await db_session.begin_nested()
        try:
            await apply_ops(
                db_session, revision_user, subsidy.id, ops,
                reviewer_overrides=reviewer_overrides, create_version=False,
            )
            tree_after = await compute_feo_plan_tree(db_session, [subsidy.id])
            return await compute_balance(db_session, subsidy.id, ops, tree_before, tree_after)
        finally:
            await nested.rollback()

    # Приняты только ложки (+100000) и чашки (-50000): net = +50000, free=0 -> дефицит.
    balance = await _balance_for([op_spoons, op_cups])
    assert balance["can_apply"] is False
    assert balance["shortfall"] == pytest.approx(50000, abs=1)

    # Добавлена третья строка связки (вилки, -50000) — закрывает дефицит целиком.
    balance2 = await _balance_for([op_spoons, op_cups, op_forks])
    assert balance2["can_apply"] is True
    assert balance2["shortfall"] == pytest.approx(0, abs=1)

    # Ложки исправлены проверяющим на +50000 (reviewer_after) — тоже закрывает,
    # без третьей строки.
    balance3 = await _balance_for(
        [op_spoons, op_cups], reviewer_overrides={op_spoons.id: {"amount": 50000}},
    )
    assert balance3["can_apply"] is True


@pytest.mark.asyncio
async def test_balance_bundle_scenario_free_fifty_thousand(db_session, test_org, revision_user):
    """При свободных 50000 ложки (+100000) и чашки (-50000) проходят БЕЗ
    третьей строки связки (net=+50000 == free, shortfall=0)."""
    from app.services.feo_plan_tree import compute_feo_plan_tree

    subsidy = await _make_subsidy(db_session, test_org.id, budget=350000)
    cat = await _make_category(db_session, subsidy.id)
    spoons = await _make_item(db_session, cat.id, name="Ложки", amount=100000, quantity=1, unit_price=100000)
    cups = await _make_item(db_session, cat.id, name="Чашки", amount=100000, quantity=1, unit_price=100000)
    forks = await _make_item(db_session, cat.id, name="Вилки", amount=100000, quantity=1, unit_price=100000)
    # Бюджет 350000, план 300000 -> free = 50000.

    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)
    op_spoons = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": spoons.id,
        "field_group": "qty_price", "after": {"amount": 200000}, "bundle_no": 1,
    })
    op_cups = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": cups.id,
        "field_group": "qty_price", "after": {"amount": 50000}, "bundle_no": 1,
    })

    tree_before = await compute_feo_plan_tree(db_session, [subsidy.id])
    nested = await db_session.begin_nested()
    try:
        await apply_ops(db_session, revision_user, subsidy.id, [op_spoons, op_cups], create_version=False)
        tree_after = await compute_feo_plan_tree(db_session, [subsidy.id])
        balance = await compute_balance(db_session, subsidy.id, [op_spoons, op_cups], tree_before, tree_after)
    finally:
        await nested.rollback()

    assert balance["can_apply"] is True
    assert balance["shortfall"] == pytest.approx(0, abs=1)


# ── Приёмка 02.10.2026: field_group опционален, мусорная группа — 422, а не
# 500; bundle_no принимает и строку, и число, нечисловую строку — 422. ──────

@pytest.mark.asyncio
async def test_add_op_without_field_group_splits_into_two_rows(db_session, test_org, revision_user):
    """POST /ops без field_group с amount (qty_price) + feo_amount (meta) —
    ДВЕ строки, не KeyError/500 на FIELD_GROUPS[entity][None]."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_item(db_session, cat.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    result = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "after": {"amount": 2000, "feo_amount": 2000},
    })
    assert isinstance(result, list)
    assert len(result) == 2
    groups = {op.field_group for op in result}
    assert groups == {"qty_price", "meta"}

    await db_session.refresh(revision)
    assert len(await ops_svc.load_ops(db_session, revision.id)) == 2


@pytest.mark.asyncio
async def test_add_op_unknown_field_group_is_422_not_500(db_session, test_org, revision_user):
    """Фронт прислал несуществующую группу (например склеенную строку полей
    через запятую) — явная 422, а не KeyError/500."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_item(db_session, cat.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    with pytest.raises(HTTPException) as exc_info:
        await ops_svc.add_op(db_session, revision, revision_user, {
            "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
            "field_group": "amount,feo_amount", "after": {"amount": 2000},
        })
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_add_op_unknown_field_without_group_is_422(db_session, test_org, revision_user):
    """Поле, которое не входит ни в одну группу и не является известным
    служебным флагом запроса, — тоже 422, не тихая потеря значения."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_item(db_session, cat.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    with pytest.raises(HTTPException) as exc_info:
        await ops_svc.add_op(db_session, revision, revision_user, {
            "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
            "after": {"totally_unknown_field": 1},
        })
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "unknown_field"


@pytest.mark.asyncio
async def test_add_op_drops_known_service_field_silently(db_session, test_org, revision_user):
    """sync_product_kind — флаг запроса фронта, не колонка FeoPlannedItem —
    не должен валить правку, когда идёт вперемешку с настоящим полем."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_item(db_session, cat.id)
    revision = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy.id)

    op = await ops_svc.add_op(db_session, revision, revision_user, {
        "entity_type": "feo_item", "op_type": "update", "target_id": item.id,
        "after": {"item_type": "goods", "sync_product_kind": True},
    })
    assert op is not None and not isinstance(op, list)
    assert op.field_group == "meta"
    assert "sync_product_kind" not in op.after


def test_parse_bundle_no_digit_string_becomes_int():
    assert ops_svc.parse_bundle_no("1") == 1
    assert ops_svc.parse_bundle_no(2) == 2
    assert ops_svc.parse_bundle_no(None) is None
    assert ops_svc.parse_bundle_no("") is None


def test_parse_bundle_no_non_digit_string_is_422():
    with pytest.raises(HTTPException) as exc_info:
        ops_svc.parse_bundle_no("B1")
    assert exc_info.value.status_code == 422


# ── IDOR: строка корректировки не смеет ссылаться на чужую субсидию ─────────

@pytest.mark.asyncio
async def test_update_target_id_from_other_subsidy_is_404(db_session, test_org, revision_user):
    """Корректировка субсидии A с target_id плановой позиции из субсидии B —
    404 entity_not_in_subsidy, строка не заводится."""
    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    cat_b = await _make_category(db_session, subsidy_b.id)
    item_b = await _make_item(db_session, cat_b.id, amount=1000)

    revision_a = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy_a.id)

    with pytest.raises(HTTPException) as exc_info:
        await ops_svc.add_op(db_session, revision_a, revision_user, {
            "entity_type": "feo_item", "op_type": "update", "target_id": item_b.id,
            "field_group": "qty_price", "after": {"amount": 9999},
        })
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "entity_not_in_subsidy"
    assert len(await ops_svc.load_ops(db_session, revision_a.id)) == 0

    await db_session.refresh(item_b)
    assert float(item_b.amount) == 1000  # не тронута


@pytest.mark.asyncio
async def test_delete_target_id_from_other_subsidy_is_404(db_session, test_org, revision_user):
    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    cat_b = await _make_category(db_session, subsidy_b.id)

    revision_a = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy_a.id)

    with pytest.raises(HTTPException) as exc_info:
        await ops_svc.add_op(db_session, revision_a, revision_user, {
            "entity_type": "feo_category", "op_type": "delete", "target_id": cat_b.id,
        })
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "entity_not_in_subsidy"


@pytest.mark.asyncio
async def test_create_with_parent_id_from_other_subsidy_is_404(db_session, test_org, revision_user):
    """create новой плановой позиции с feo_category_id, указывающим на живую
    категорию ЧУЖОЙ субсидии — 404, а не create под чужим деревом."""
    subsidy_a = await _make_subsidy(db_session, test_org.id)
    subsidy_b = await _make_subsidy(db_session, test_org.id)
    cat_b = await _make_category(db_session, subsidy_b.id)

    revision_a = await ops_svc.get_or_create_draft(db_session, revision_user, subsidy_a.id)

    with pytest.raises(HTTPException) as exc_info:
        await ops_svc.add_op(db_session, revision_a, revision_user, {
            "entity_type": "feo_item", "op_type": "create",
            "after": {"name": "Чужая позиция", "amount": 500, "feo_category_id": cat_b.id},
        })
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "entity_not_in_subsidy"
    assert len(await ops_svc.load_ops(db_session, revision_a.id)) == 0
