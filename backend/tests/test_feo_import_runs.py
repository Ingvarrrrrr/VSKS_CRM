"""Журнал прогонов импорта ФЭО (волна 3, 26.09) — GET /api/feo-categories/
import-runs и GET /api/feo-categories/import-runs/{id}/changes (app/routers/
feo_import_runs.py, подключён как под-роутер feo_categories.router — см. её
докстринг про запрет трогать routes.py).

Запускать ПО ОДНОМУ файлу/тесту (флейк pytest-asyncio "different loop",
см. conftest.py и остальные test_feo_history*.py).
"""
from decimal import Decimal

import pytest

from app.models.entity_change import EntityChange
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_import_run import FeoImportRun
from app.services import feo_history


async def _make_subsidy_category_item(db_session, test_org):
    subsidy = Subsidy(name="Тестовая субсидия ImportRuns", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория теста ImportRuns")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    item = FeoPlannedItem(feo_category_id=cat.id, name="Позиция теста ImportRuns", quantity=Decimal("1"), amount=Decimal("100"))
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    return subsidy, cat, item


async def _make_run(db_session, subsidy_id, **kwargs):
    run = FeoImportRun(
        subsidy_id=subsidy_id,
        user_name=kwargs.get("user_name", "Иванов И.И."),
        filename=kwargs.get("filename", "smeta.xlsx"),
        sheet_name=kwargs.get("sheet_name", "Лист1"),
        created_count=kwargs.get("created_count", 1),
        updated_count=kwargs.get("updated_count", 0),
        skipped_count=kwargs.get("skipped_count", 0),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_list_import_runs_returns_newest_first(db_session, client, test_org, test_user, auth_headers, make_role_permission):
    await make_role_permission(role="employee", key="feo_categories", granted=True)
    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)

    run1 = await _make_run(db_session, subsidy.id, filename="first.xlsx")
    run2 = await _make_run(db_session, subsidy.id, filename="second.xlsx")

    resp = await client.get(f"/api/feo-categories/import-runs?subsidy_id={subsidy.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    ids = [r["id"] for r in data["items"]]
    # newest sorted first — тот же id run2 создан позже (started_at server_default now()).
    assert ids[0] == run2.id
    assert ids[1] == run1.id


@pytest.mark.asyncio
async def test_list_import_runs_forbidden_without_access(db_session, client, test_org, test_user, auth_headers):
    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)
    await _make_run(db_session, subsidy.id)

    resp = await client.get(f"/api/feo-categories/import-runs?subsidy_id={subsidy.id}", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_run_changes_returns_names_not_bare_ids(db_session, client, test_org, test_user, auth_headers, make_role_permission):
    """Владелец требует называть сущности именами — GET .../changes должен
    отдавать entity_name, а не только entity_id."""
    await make_role_permission(role="employee", key="feo_categories", granted=True)
    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)
    run = await _make_run(db_session, subsidy.id)

    await feo_history.record_created(
        db_session, feo_history.ENTITY_FEO_ITEM, item.id, None,
        source=feo_history.SOURCE_IMPORT, source_ref=run.id,
    )

    resp = await client.get(f"/api/feo-categories/import-runs/{run.id}/changes", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["entity_type"] == "feo_item"
    assert rows[0]["entity_id"] == item.id
    assert rows[0]["entity_name"] == item.name
    assert rows[0]["is_created"] is True


@pytest.mark.asyncio
async def test_get_run_changes_404_for_unknown_run(client, auth_headers):
    resp = await client.get("/api/feo-categories/import-runs/999999999/changes", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_single_run(db_session, client, test_org, auth_headers, make_role_permission):
    await make_role_permission(role="employee", key="feo_categories", granted=True)
    subsidy, cat, item = await _make_subsidy_category_item(db_session, test_org)
    run = await _make_run(db_session, subsidy.id, filename="detail.xlsx", user_name="Петров П.П.")

    resp = await client.get(f"/api/feo-categories/import-runs/{run.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["filename"] == "detail.xlsx"
    assert data["user_name"] == "Петров П.П."
