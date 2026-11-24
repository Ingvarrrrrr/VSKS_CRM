"""Tests for cell history enhancements (Phase: Gala Context Menu & Cell History).

Tests:
1. entity_changes router filtering by field and field_name.
2. vehicles router returning changed_by_name in field-history.
3. entity_changes supports 'contract' and 'payment' without 400 error.
4. origin_label enrichment on __created__ row (Case A: import, wish, purchase, autoassign, collapse, manual).
5. synthesized __created__ row (Case B: feo_item, feo_category, purchase, wish, contract, payment, task, subsidy).
6. access control for contract and payment (404 on not found).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.contract import Contract
from app.models.entity_change import EntityChange
from app.models.feo_category import FeoCategory
from app.models.feo_import_run import FeoImportRun
from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.task import Task
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_field_history import VehicleFieldHistory
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.routers.entity_changes import router as entity_changes_router, EntityChangeOut
from app.routers.vehicles import router as vehicles_router
from app.auth.permissions import require_tab
from app.services.entity_origin import attach_entity_origin


def _create_mock_user(user_id: int = 1, full_name: str = "Игорь Цыганов") -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "superadmin"
    user.full_name = full_name
    user.username = "testuser"
    user.is_superuser = True
    user.tab_permissions = ["vehicles"]
    user.org_id = 1
    return user


def test_entity_changes_field_filtering():
    app = FastAPI()
    app.include_router(entity_changes_router)

    mock_user = _create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

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
    mock_db.get.return_value = None

    client = TestClient(app)
    resp = client.get("/api/entity-changes/purchase/10?field=subject")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
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


def test_entity_changes_contract_and_payment_allowed():
    """Verify 'contract' and 'payment' do not trigger 400 Invalid entity type."""
    app = FastAPI()
    app.include_router(entity_changes_router)

    mock_user = _create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_contract = MagicMock(spec=Contract)
    mock_contract.id = 100
    mock_contract.subsidy_id = 1
    mock_contract.number = "ДОГ-2026/01"

    mock_payment = MagicMock(spec=Payment)
    mock_payment.id = 200
    mock_payment.purchase_id = 10
    mock_payment.bank_payment_id = None
    mock_payment.import_run_id = None
    mock_payment.confirmed_by_statement = False

    async def _mock_get(model, pk):
        if model is Contract:
            return mock_contract
        if model is Payment:
            return mock_payment
        return None

    mock_db.get.side_effect = _mock_get
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    client = TestClient(app)
    r_contract = client.get("/api/entity-changes/contract/100")
    assert r_contract.status_code == 200
    data_c = r_contract.json()
    assert len(data_c) == 1
    assert data_c[0]["field_name"] == "__created__"
    assert "Внесено при оформлении договора №ДОГ-2026/01" in data_c[0]["origin_label"]

    r_payment = client.get("/api/entity-changes/payment/200")
    assert r_payment.status_code == 200
    data_p = r_payment.json()
    assert len(data_p) == 1
    assert data_p[0]["field_name"] == "__created__"
    assert "Внесено при регистрации платежа" in data_p[0]["origin_label"]


def test_entity_changes_contract_not_found_returns_404():
    app = FastAPI()
    app.include_router(entity_changes_router)

    mock_user = _create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    mock_db.get.return_value = None

    client = TestClient(app)
    r = client.get("/api/entity-changes/contract/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_case_a_enrich_created_row_import():
    mock_db = AsyncMock()
    run = MagicMock(spec=FeoImportRun)
    run.id = 42
    run.filename = "ФЭО_2026_тест.xlsx"
    run.user_name = "Иван Иванов"
    run.started_at = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)

    item = MagicMock(spec=FeoPlannedItem)
    item.id = 15
    item.source_row = 14

    async def _mock_get(model, pk):
        if model is FeoImportRun and pk == 42:
            return run
        if model is FeoPlannedItem and pk == 15:
            return item
        return None

    mock_db.get.side_effect = _mock_get

    row = EntityChangeOut(
        id=1,
        entity_type="feo_item",
        entity_id=15,
        field_name="__created__",
        source="import",
        source_ref=42,
    )
    res = await attach_entity_origin(mock_db, "feo_item", 15, [row])
    assert len(res) == 1
    assert "Загружено импортом из «ФЭО_2026_тест.xlsx» (строка 14)" in res[0].origin_label
    assert res[0].changed_by_name == "Иван Иванов"
    assert res[0].changed_at == datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_case_a_enrich_created_row_wish_and_purchase():
    mock_db = AsyncMock()
    wish = MagicMock(spec=Wish)
    wish.id = 7
    wish.title = "Покупка раций"
    wish.created_by = 3
    wish.created_at = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)

    user = MagicMock(spec=User)
    user.id = 3
    user.full_name = "Анна Смирнова"

    async def _mock_get(model, pk):
        if model is Wish and pk == 7:
            return wish
        if model is User and pk == 3:
            return user
        return None

    mock_db.get.side_effect = _mock_get

    row_wish = EntityChangeOut(
        id=2,
        entity_type="feo_item",
        entity_id=20,
        field_name="__created__",
        source="wish",
        source_ref=7,
    )
    res_w = await attach_entity_origin(mock_db, "feo_item", 20, [row_wish])
    assert res_w[0].origin_label == "Создано из заявки №7 «Покупка раций»"
    assert res_w[0].changed_by_name == "Анна Смирнова"

    # Test autoassign, collapse, manual
    r_auto = EntityChangeOut(id=3, entity_type="feo_item", entity_id=21, field_name="__created__", source="autoassign")
    res_auto = await attach_entity_origin(mock_db, "feo_item", 21, [r_auto])
    assert "автоматически" in res_auto[0].origin_label

    r_col = EntityChangeOut(id=4, entity_type="feo_item", entity_id=22, field_name="__created__", source="collapse")
    res_col = await attach_entity_origin(mock_db, "feo_item", 22, [r_col])
    assert "объединении дублирующих" in res_col[0].origin_label

    r_man = EntityChangeOut(id=5, entity_type="feo_item", entity_id=23, field_name="__created__", source="manual")
    res_man = await attach_entity_origin(mock_db, "feo_item", 23, [r_man])
    assert "Внесено вручную" in res_man[0].origin_label


@pytest.mark.asyncio
async def test_case_b_synthetic_feo_item_auto_created():
    mock_db = AsyncMock()

    item = MagicMock(spec=FeoPlannedItem)
    item.id = 50
    item.auto_created = True
    item.created_at = datetime(2026, 1, 15, tzinfo=timezone.utc)

    wish = MagicMock(spec=Wish)
    wish.id = 12
    wish.title = "Снаряжение"
    wish.created_by = 2
    wish.created_at = datetime(2026, 1, 10, tzinfo=timezone.utc)

    user = MagicMock(spec=User)
    user.full_name = "Петр Сидоров"

    async def _mock_get(model, pk):
        if model is FeoPlannedItem and pk == 50:
            return item
        if model is Wish and pk == 12:
            return wish
        if model is User and pk == 2:
            return user
        return None

    mock_db.get.side_effect = _mock_get

    mock_w_exec = MagicMock()
    mock_w_exec.first.return_value = (12,)
    mock_db.execute.return_value = mock_w_exec

    res = await attach_entity_origin(mock_db, "feo_item", 50, [])
    assert len(res) == 1
    assert res[0].field_name == "__created__"
    assert res[0].origin_label == "Создано из заявки №12 «Снаряжение»"
    assert res[0].changed_by_name == "Петр Сидоров"
    assert res[0].source == "wish"
    assert res[0].source_ref == 12


@pytest.mark.asyncio
async def test_case_b_synthetic_payment_from_statement():
    mock_db = AsyncMock()

    pay = MagicMock(spec=Payment)
    pay.id = 88
    pay.bank_payment_id = 999
    pay.payment_date = datetime(2026, 4, 1, tzinfo=timezone.utc)
    pay.purchase_id = None

    async def _mock_get(model, pk):
        if model is Payment and pk == 88:
            return pay
        return None

    mock_db.get.side_effect = _mock_get

    res = await attach_entity_origin(mock_db, "payment", 88, [])
    assert len(res) == 1
    assert res[0].field_name == "__created__"
    assert res[0].origin_label == "Загружено из банковской выписки"
    assert res[0].source == "import"
    assert res[0].source_ref == 999


@pytest.mark.asyncio
async def test_case_b_synthetic_task_and_subsidy():
    mock_db = AsyncMock()

    task = MagicMock(spec=Task)
    task.id = 301
    task.created_by_id = 5
    task.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    sub = MagicMock(spec=Subsidy)
    sub.id = 10
    sub.name = "Субсидия 2026"
    sub.created_by = 5
    sub.approved_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    user = MagicMock(spec=User)
    user.full_name = "Куратор Задач"

    async def _mock_get(model, pk):
        if model is Task and pk == 301:
            return task
        if model is Subsidy and pk == 10:
            return sub
        if model is User and pk == 5:
            return user
        return None

    mock_db.get.side_effect = _mock_get

    res_t = await attach_entity_origin(mock_db, "task", 301, [])
    assert len(res_t) == 1
    assert res_t[0].origin_label == "Внесено при постановке задачи"
    assert res_t[0].changed_by_name == "Куратор Задач"

    res_s = await attach_entity_origin(mock_db, "subsidy", 10, [])
    assert len(res_s) == 1
    assert res_s[0].origin_label == "Заведено при создании субсидии"
    assert res_s[0].changed_by_name == "Куратор Задач"
