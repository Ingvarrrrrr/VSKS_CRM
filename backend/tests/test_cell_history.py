"""Tests for cell history enhancements (Phase: Gala Context Menu & Cell History).

Tests:
1. entity_changes router filtering by field and field_name.
2. vehicles router returning changed_by_name in field-history.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.entity_change import EntityChange
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_field_history import VehicleFieldHistory
from app.routers.entity_changes import router as entity_changes_router
from app.routers.vehicles import router as vehicles_router
from app.auth.permissions import require_tab


def _create_mock_user(user_id: int = 1, full_name: str = "Игорь Цыганов") -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "superadmin"
    user.full_name = full_name
    user.username = "testuser"
    user.is_superuser = True
    user.tab_permissions = ["vehicles"]
    return user


def test_entity_changes_field_filtering():
    app = FastAPI()
    app.include_router(entity_changes_router)

    mock_user = _create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock execute result
    c1 = EntityChange(
        id=1,
        entity_type="purchase",
        entity_id=10,
        field_name="subject",
        old_value="Старая закупка",
        new_value="Новая закупка",
        changed_by_id=1,
        changed_by_name="Игорь Цыганов",
        changed_at=datetime.now(timezone.utc),
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [c1]
    mock_db.execute.return_value = mock_res

    client = TestClient(app)
    resp = client.get("/api/entity-changes/purchase/10?field=subject")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["field_name"] == "subject"
    assert data[0]["changed_by_name"] == "Игорь Цыганов"

    # Also test field_name query param
    resp2 = client.get("/api/entity-changes/purchase/10?field_name=subject")
    assert resp2.status_code == 200


def test_vehicle_field_history_returns_changed_by_name():
    app = FastAPI()
    app.include_router(vehicles_router)

    mock_user = _create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[require_tab("vehicles")] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_vehicle = MagicMock(spec=Vehicle)
    mock_vehicle.id = 5
    mock_vehicle.owner_org_id = 1
    mock_vehicle.assigned_org_id = 1
    mock_db.get.return_value = mock_vehicle

    # Field history item with author
    history_user = MagicMock(spec=User)
    history_user.full_name = "Игорь Цыганов"
    history_user.username = "icyganov"

    fh = VehicleFieldHistory(
        id=101,
        vehicle_id=5,
        field_key="mileage",
        old_value="1000",
        new_value="1500",
        changed_at=datetime.now(timezone.utc),
        changed_by_user_id=1,
    )
    fh.changed_by = history_user

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [fh]
    mock_db.execute.return_value = mock_res

    client = TestClient(app)
    resp = client.get("/api/vehicles/5/field-history?field_key=mileage")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["field_key"] == "mileage"
    assert data[0]["changed_by_name"] == "Игорь Цыганов"
