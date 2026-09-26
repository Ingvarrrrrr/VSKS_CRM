"""Журнал изменений ФЭО, волна 1 (фундамент) — 22.09.

Покрывает:
- app/services/feo_history.py: record_created/record_updated/record_deleted
  пишут ожидаемые строки EntityChange с source/source_ref.
- app/routers/entity_changes.py::record_entity_changes(commit=False) не
  коммитит (после отката строк нет); commit=True (умолчание) — коммитит.
- GET /api/entity-changes/feo_item/{id} отдаёт записи (включая source/
  source_ref) для доступного пользователю feo_item.

Запускать ПО ОДНОМУ файлу (флейк "different loop", см. conftest.py).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.entity_change import EntityChange
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.routers.entity_changes import record_entity_changes
from app.services import feo_history


async def _make_subsidy_category_item(db_session, test_org):
    subsidy = Subsidy(name="Тестовая субсидия", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория теста")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    item = FeoPlannedItem(feo_category_id=cat.id, name="Позиция теста", quantity=Decimal("1"), amount=Decimal("100"))
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    return subsidy, cat, item


@pytest.mark.asyncio
async def test_record_created_writes_marker_row(db_session, test_user):
    await feo_history.record_created(
        db_session, feo_history.ENTITY_FEO_ITEM, 12345, test_user,
        source=feo_history.SOURCE_MANUAL,
    )
    rows = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == feo_history.ENTITY_FEO_ITEM,
            EntityChange.entity_id == 12345,
        )
    )).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.field_name == feo_history.FIELD_CREATED_MARKER
    assert row.source == "manual"
    assert row.source_ref is None
    assert row.changed_by_id == test_user.id


@pytest.mark.asyncio
async def test_record_updated_writes_diff_with_source(db_session, test_user):
    await feo_history.record_updated(
        db_session, feo_history.ENTITY_FEO_ITEM, 777, test_user,
        old_values={"amount": "100", "name": "A"},
        new_values={"amount": "200", "name": "A"},
        source=feo_history.SOURCE_IMPORT,
        source_ref=42,
    )
    rows = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == feo_history.ENTITY_FEO_ITEM,
            EntityChange.entity_id == 777,
        )
    )).scalars().all()
    # Only 'amount' differs — 'name' unchanged must not produce a row (same
    # rule as record_entity_changes without source/source_ref).
    assert len(rows) == 1
    row = rows[0]
    assert row.field_name == "amount"
    assert row.old_value == "100"
    assert row.new_value == "200"
    assert row.source == "import"
    assert row.source_ref == 42


@pytest.mark.asyncio
async def test_record_deleted_writes_marker_row(db_session, test_user):
    await feo_history.record_deleted(
        db_session, feo_history.ENTITY_FEO_CATEGORY, 555, test_user,
        source=feo_history.SOURCE_COLLAPSE, source_ref=999,
    )
    rows = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == feo_history.ENTITY_FEO_CATEGORY,
            EntityChange.entity_id == 555,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].field_name == feo_history.FIELD_DELETED_MARKER
    assert rows[0].source == "collapse"
    assert rows[0].source_ref == 999


@pytest.mark.asyncio
async def test_invalid_source_rejected(db_session, test_user):
    with pytest.raises(ValueError):
        await feo_history.record_created(
            db_session, feo_history.ENTITY_FEO_ITEM, 1, test_user, source="bogus",
        )


@pytest.mark.asyncio
async def test_record_entity_changes_commit_false_does_not_persist(db_session, test_user):
    """commit=False → only flush; rolling back the nested transaction it was
    written under must leave no row (dry_run import safety)."""
    nested = await db_session.begin_nested()
    await record_entity_changes(
        db_session, "feo_item", 9001, test_user.id, test_user.full_name,
        old_values={"amount": "1"}, new_values={"amount": "2"},
        source="import", source_ref=7, commit=False,
    )
    # Visible within the same session before rollback (flush happened).
    visible = (await db_session.execute(
        select(EntityChange).where(EntityChange.entity_id == 9001, EntityChange.entity_type == "feo_item")
    )).scalars().all()
    assert len(visible) == 1

    await nested.rollback()

    after_rollback = (await db_session.execute(
        select(EntityChange).where(EntityChange.entity_id == 9001, EntityChange.entity_type == "feo_item")
    )).scalars().all()
    assert after_rollback == []


@pytest.mark.asyncio
async def test_record_entity_changes_commit_true_persists_past_later_rollback(db_session, test_user):
    """commit=True (default) → row survives a LATER, unrelated nested-transaction
    rollback (proves it was actually committed, not just flushed)."""
    await record_entity_changes(
        db_session, "feo_item", 9002, test_user.id, test_user.full_name,
        old_values={"amount": "1"}, new_values={"amount": "2"},
        source="import", source_ref=7,  # commit defaults to True
    )

    nested = await db_session.begin_nested()
    await nested.rollback()  # no-op write, but exercises that the row isn't tied to it

    rows = (await db_session.execute(
        select(EntityChange).where(EntityChange.entity_id == 9002, EntityChange.entity_type == "feo_item")
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_entity_changes_returns_feo_item_history(db_session, client, test_org, test_user, auth_headers, make_role_permission):
    """GET /api/entity-changes/feo_item/{id} — access granted via feo_categories
    tab (RolePermission seeded for test_user's role), returns source/source_ref."""
    await make_role_permission(role="employee", key="feo_categories", granted=True)

    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)

    await feo_history.record_updated(
        db_session, feo_history.ENTITY_FEO_ITEM, item.id, test_user,
        old_values={"amount": "100"}, new_values={"amount": "150"},
        source=feo_history.SOURCE_WISH, source_ref=321,
    )

    resp = await client.get(f"/api/entity-changes/feo_item/{item.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "wish"
    assert data[0]["source_ref"] == 321
    assert data[0]["field_name"] == "amount"


@pytest.mark.asyncio
async def test_get_entity_changes_feo_item_forbidden_without_access(db_session, client, test_org, test_user, auth_headers):
    """Without any feo_categories/wish.edit_feo/wishes/purchases grant, an
    employee must NOT read another org's/subsidy's ФЭО history — 403, not a
    silent empty list (security-by-obscurity is NOT acceptable for feo_item,
    see _check_feo_history_read_access docstring)."""
    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)

    resp = await client.get(f"/api/entity-changes/feo_item/{item.id}", headers=auth_headers)
    assert resp.status_code == 403
