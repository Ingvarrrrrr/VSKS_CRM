"""Unit tests for CellMark model, schemas, router, and Alembic migration."""
import sys
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.cell_mark import CellMark
from app.models.user import User
from app.routers.cell_marks import (
    CellMarkTarget,
    CellMarkBatchIn,
    ClearColorTarget,
    ClearColorIn,
    CellMarkOut,
    BatchResultOut,
    ClearColorResultOut,
    ResolveResultOut,
    list_cell_marks,
    batch_upsert_cell_marks,
    clear_cell_mark_color,
    resolve_cell_marks_group,
)


@pytest.fixture
def mock_user():
    u = MagicMock(spec=User)
    u.id = 42
    u.role = "employee"
    u.org_id = 7
    u.full_name = "Иван Иванов"
    u.email = "ivan@example.com"
    return u


@pytest.fixture
def mock_superadmin():
    u = MagicMock(spec=User)
    u.id = 1
    u.role = "superadmin"
    u.org_id = None
    u.full_name = "Суперадмин"
    u.email = "admin@example.com"
    return u


# ── Model & Schema tests ─────────────────────────────────────────────────────

def test_cell_mark_model_columns_and_defaults():
    cols = {c.name: c for c in CellMark.__table__.columns}
    assert "group_id" in cols
    assert "entity_type" in cols
    assert "entity_id" in cols
    assert "field_name" in cols
    assert "color" in cols
    assert "comment" in cols
    assert "visibility" in cols
    assert "is_resolved" in cols
    assert "resolved_at" in cols
    assert "resolved_by_id" in cols
    assert "created_by_id" in cols

    mark = CellMark(
        group_id="grp-123",
        entity_type="feo_item",
        entity_id=10,
        field_name="quantity",
        color="yellow",
        comment="Проверить количество",
    )
    assert mark.field_name == "quantity"
    assert mark.visibility == "shared"
    assert mark.is_resolved is False


def test_cell_mark_pydantic_schemas_validation():
    batch = CellMarkBatchIn(
        targets=[
            CellMarkTarget(entity_type="task", entity_id=5, field_name="*"),
            CellMarkTarget(entity_type="task", entity_id=5, field_name="title"),
        ],
        color="red",
        comment="Важно",
        visibility="shared",
    )
    assert len(batch.targets) == 2
    assert batch.targets[0].field_name == "*"

    out = CellMarkOut(
        id=1,
        group_id="uuid-1",
        entity_type="task",
        entity_id=5,
        field_name="title",
        color="red",
        comment="Важно",
        visibility="shared",
        is_resolved=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert out.color == "red"
    assert out.is_resolved is False


# ── Alembic migration test ───────────────────────────────────────────────────

def test_alembic_migration_upgrade_and_downgrade():
    """Verify Alembic migration executes cleanly with zero duplicate index errors."""
    if "alembic" not in sys.modules:
        sys.modules["alembic"] = MagicMock()
        sys.modules["alembic.op"] = sys.modules["alembic"].op

    mig_path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "c3e5a7b9d1f3_add_cell_marks.py"
    spec = importlib.util.spec_from_file_location("mig_cell_marks", mig_path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    created_tables = []
    created_indexes = []

    def fake_create_table(name, *cols, **kw):
        assert name not in created_tables, f"Duplicate table name: {name}"
        created_tables.append(name)

    def fake_create_index(name, tname, cols, **kw):
        assert name not in created_indexes, f"Duplicate index name: {name}"
        created_indexes.append(name)

    fake_op = MagicMock()
    fake_op.create_table.side_effect = fake_create_table
    fake_op.create_index.side_effect = fake_create_index

    with patch.object(mig, "op", fake_op), \
         patch("sqlalchemy.inspect") as mock_inspect:
        insp_mock = MagicMock()
        insp_mock.get_table_names.side_effect = [
            [],              # for upgrade: table does not exist
            ["cell_marks"],  # for downgrade: table exists
        ]
        mock_inspect.return_value = insp_mock

        mig.upgrade()
        assert "cell_marks" in created_tables
        # Only ix_cell_marks_lookup is created explicitly (single-column indexes created by index=True)
        assert created_indexes == ["ix_cell_marks_lookup"]

        mig.downgrade()
        assert fake_op.drop_table.called
        assert fake_op.drop_table.call_args[0][0] == "cell_marks"


# ── Router tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_cell_marks_filters(mock_user):
    db = AsyncMock()
    mark = CellMark(
        id=1,
        group_id="g1",
        entity_type="purchase",
        entity_id=100,
        field_name="*",
        color="blue",
        comment="Строка",
        visibility="shared",
        is_resolved=False,
        created_by_id=mock_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mark]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute.return_value = execute_result

    with patch("app.routers.cell_marks.owner_scope_org_ids", new=AsyncMock(return_value={7})):
        res = await list_cell_marks(
            entity_type="purchase",
            entity_ids="100,101",
            include_resolved=False,
            db=db,
            current_user=mock_user,
        )

    assert len(res) == 1
    assert res[0].entity_id == 100
    assert res[0].color == "blue"


@pytest.mark.asyncio
async def test_batch_upsert_create_new(mock_user):
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None  # No existing mark
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute.return_value = execute_result

    async def mock_refresh(item):
        if item.id is None:
            item.id = 1
    db.refresh.side_effect = mock_refresh

    body = CellMarkBatchIn(
        targets=[CellMarkTarget(entity_type="wish", entity_id=15, field_name="*")],
        color="green",
        comment="Согласовано",
        visibility="shared",
    )

    with patch("app.routers.cell_marks.owner_scope_org_ids", new=AsyncMock(return_value=None)):
        res = await batch_upsert_cell_marks(body=body, db=db, current_user=mock_user)

    assert res.group_id is not None
    assert len(res.items) == 1
    assert res.items[0].color == "green"
    assert res.items[0].comment == "Согласовано"
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_batch_upsert_update_preserves_unspecified(mock_user):
    db = AsyncMock()
    existing_mark = CellMark(
        id=2,
        group_id="old-group",
        entity_type="task",
        entity_id=20,
        field_name="priority",
        color="orange",
        comment=None,
        visibility="shared",
        is_resolved=False,
        created_by_id=mock_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = existing_mark
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute.return_value = execute_result

    # Send only comment (color not in model_fields_set)
    body = CellMarkBatchIn.model_validate({
        "targets": [{"entity_type": "task", "entity_id": 20, "field_name": "priority"}],
        "comment": "Новый комментарий",
    })

    with patch("app.routers.cell_marks.owner_scope_org_ids", new=AsyncMock(return_value=None)):
        res = await batch_upsert_cell_marks(body=body, db=db, current_user=mock_user)

    assert existing_mark.color == "orange"  # Preserved!
    assert existing_mark.comment == "Новый комментарий"  # Updated!
    assert existing_mark.group_id == res.group_id


@pytest.mark.asyncio
async def test_clear_color_with_and_without_comment(mock_user):
    db = AsyncMock()
    mark_with_comment = CellMark(
        id=10,
        group_id="g1",
        entity_type="task",
        entity_id=5,
        field_name="title",
        color="red",
        comment="Останется с комментарием",
        visibility="shared",
        is_resolved=False,
        created_by_id=mock_user.id,
    )
    mark_without_comment = CellMark(
        id=11,
        group_id="g1",
        entity_type="task",
        entity_id=5,
        field_name="*",
        color="yellow",
        comment=None,
        visibility="shared",
        is_resolved=False,
        created_by_id=mock_user.id,
    )

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mark_with_comment, mark_without_comment]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute.return_value = execute_result

    body = ClearColorIn(
        targets=[ClearColorTarget(entity_type="task", entity_id=5, field_name=None)]
    )
    res = await clear_cell_mark_color(body=body, db=db, current_user=mock_user)

    assert res.cleared == 2
    # Mark with comment: color reset to None, stays unresolved
    assert mark_with_comment.color is None
    assert mark_with_comment.is_resolved is False
    assert mark_with_comment.comment == "Останется с комментарием"
    # Mark without comment: resolved
    assert mark_without_comment.is_resolved is True
    assert mark_without_comment.resolved_by_id == mock_user.id


@pytest.mark.asyncio
async def test_resolve_group_preserves_color_and_comment(mock_user):
    db = AsyncMock()
    mark1 = CellMark(
        id=1,
        group_id="target-grp",
        entity_type="purchase",
        entity_id=50,
        field_name="subject",
        color="purple",
        comment="Вопрос по закупке",
        visibility="shared",
        is_resolved=False,
        created_by_id=mock_user.id,
    )
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mark1]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute.return_value = execute_result

    with patch("app.routers.cell_marks.owner_scope_org_ids", new=AsyncMock(return_value=None)):
        res = await resolve_cell_marks_group(group_id="target-grp", db=db, current_user=mock_user)

    assert res.resolved == 1
    assert res.group_id == "target-grp"
    assert mark1.is_resolved is True
    assert mark1.color == "purple"  # Preserved in DB for history!
    assert mark1.comment == "Вопрос по закупке"  # Preserved!
    assert mark1.resolved_by_name == "Иван Иванов"


def test_http_endpoints_snake_and_camel_case(mock_user):
    from fastapi.testclient import TestClient
    from app import app
    from app.auth.jwt import get_current_user
    from app.database import get_db

    mock_db = AsyncMock()
    scalars_mock = MagicMock()
    mark = CellMark(
        id=1, group_id="g-100", entity_type="task", entity_id=10, field_name="title",
        color="red", comment="Test", visibility="shared", is_resolved=False,
        created_by_id=mock_user.id, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
    )
    scalars_mock.first.return_value = mark
    scalars_mock.all.return_value = [mark]
    res_mock = MagicMock()
    res_mock.scalars.return_value = scalars_mock
    mock_db.execute.return_value = res_mock

    async def mock_refresh(item):
        if item.id is None:
            item.id = 1
    mock_db.refresh.side_effect = mock_refresh

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("app.routers.cell_marks.owner_scope_org_ids", new=AsyncMock(return_value=None)), \
             TestClient(app) as tc:
            # 1. POST /api/cell-marks/batch (snake_case)
            r1 = tc.post("/api/cell-marks/batch", json={
                "targets": [{"entity_type": "task", "entity_id": 10, "field_name": "title"}],
                "color": "red",
                "comment": "Test",
                "visibility": "shared",
            })
            assert r1.status_code == 200, r1.text

            # 2. POST /api/cell-marks/batch (camelCase)
            r2 = tc.post("/api/cell-marks/batch", json={
                "targets": [{"entityType": "task", "entityId": 10, "fieldName": "title", "subsidyId": 2, "orgId": 1}],
                "color": None,
                "comment": "CamelCase comment",
                "visibility": "shared",
                "subsidyId": 2,
                "orgId": 1,
            })
            assert r2.status_code == 200, r2.text

            # 3. POST /api/cell-marks/clear-color (camelCase)
            r3 = tc.post("/api/cell-marks/clear-color", json={
                "targets": [{"entityType": "task", "entityId": 10, "fieldName": "title"}]
            })
            assert r3.status_code == 200, r3.text

            # 4. GET /api/cell-marks
            r4 = tc.get("/api/cell-marks", params={"entity_type": "task", "entity_ids": "10"})
            assert r4.status_code == 200, r4.text

            # 5. POST /api/cell-marks/{group_id}/resolve
            r5 = tc.post("/api/cell-marks/g-100/resolve")
            assert r5.status_code == 200, r5.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

