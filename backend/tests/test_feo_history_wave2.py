"""Журнал изменений ФЭО, волна 2 (26.09) — расстановка вызовов feo_history во
всех точках изменения FeoPlannedItem/FeoCategory.

Покрывает (см. задание волны 2):
  - создание плановой позиции через POST /feo-planned-items/ пишет
    source='manual';
  - правка полей (PUT) пишет дифф старое→новое;
  - удаление (DELETE) пишет запись __deleted__;
  - боевой импорт ФЭО создаёт РОВНО один FeoImportRun со счётчиками и
    историю со ссылкой на него (source='import', source_ref=id прогона);
    предпросмотр (dry_run=True) того же файла НЕ создаёт ни прогона, ни
    записей истории;
  - позиция, рождённая автозаведением из заявки (plan_autoassign.py),
    получает source='wish' + id этой заявки.

Вызывает роутеры НАПРЯМУЮ (минуя FastAPI DI), как test_item_types.py/
test_feo_comments.py — current_user передаётся явным keyword-аргументом.

Флейк pytest-asyncio «different loop» — гонять КАЖДЫЙ тест ПО ОТДЕЛЬНОСТИ:
pytest tests/test_feo_history_wave2.py::<name>.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.entity_change import EntityChange
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_import_run import FeoImportRun
from app.services import feo_history


async def _make_subsidy_category(db_session, org_id=None):
    subsidy = Subsidy(name=f"TestFeoHistory-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория теста истории")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return subsidy, cat


async def _history_rows(db_session, entity_type, entity_id):
    rows = (await db_session.execute(
        select(EntityChange)
        .where(EntityChange.entity_type == entity_type, EntityChange.entity_id == entity_id)
        .order_by(EntityChange.id)
    )).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_create_planned_item_via_api_writes_manual_history(db_session, superadmin_user):
    from app.routers.feo_planned_items import create_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session, org_id=superadmin_user.org_id)
    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name="Новая позиция", quantity=Decimal("2"),
        unit="шт", amount=Decimal("500"), is_active=True,
    )
    item = await create_planned_item(data=data, db=db_session, current_user=superadmin_user)

    rows = await _history_rows(db_session, feo_history.ENTITY_FEO_ITEM, item.id)
    created_rows = [r for r in rows if r.field_name == feo_history.FIELD_CREATED_MARKER]
    assert len(created_rows) == 1
    assert created_rows[0].source == "manual"
    assert created_rows[0].changed_by_id == superadmin_user.id


@pytest.mark.asyncio
async def test_update_planned_item_writes_field_diff(db_session, superadmin_user):
    from app.routers.feo_planned_items import update_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session, org_id=superadmin_user.org_id)
    item = FeoPlannedItem(
        feo_category_id=cat.id, name="Позиция до правки", quantity=Decimal("1"),
        unit="шт", amount=Decimal("100"), is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name="Позиция после правки", quantity=Decimal("3"),
        unit="шт", amount=Decimal("300"), is_active=True,
    )
    await update_planned_item(item_id=item.id, data=data, db=db_session, current_user=superadmin_user)

    rows = await _history_rows(db_session, feo_history.ENTITY_FEO_ITEM, item.id)
    by_field = {r.field_name: r for r in rows}
    assert by_field["name"].old_value == "Позиция до правки"
    assert by_field["name"].new_value == "Позиция после правки"
    assert Decimal(by_field["quantity"].old_value) == Decimal("1")
    assert Decimal(by_field["quantity"].new_value) == Decimal("3")
    assert all(r.source == "manual" for r in rows)


@pytest.mark.asyncio
async def test_delete_planned_item_writes_deleted_marker(db_session, superadmin_user):
    from app.routers.feo_planned_items import delete_planned_item

    _subsidy, cat = await _make_subsidy_category(db_session, org_id=superadmin_user.org_id)
    item = FeoPlannedItem(
        feo_category_id=cat.id, name="Позиция на удаление", quantity=Decimal("1"),
        unit="шт", amount=Decimal("100"), is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    item_id = item.id

    await delete_planned_item(
        item_id=item_id, purchase_id=None, wish_id=None,
        db=db_session, current_user=superadmin_user,
    )

    rows = await _history_rows(db_session, feo_history.ENTITY_FEO_ITEM, item_id)
    deleted_rows = [r for r in rows if r.field_name == feo_history.FIELD_DELETED_MARKER]
    assert len(deleted_rows) == 1
    assert deleted_rows[0].source == "manual"


@pytest.mark.asyncio
async def test_real_import_creates_one_run_with_counters_and_history(db_session):
    """Боевой прогон (dry_run=False) создаёт ровно один FeoImportRun со
    счётчиками, совпадающими с ответом импорта, и историю созданных позиций
    со ссылкой на него (source='import', source_ref=run.id)."""
    from app.routers.feo_categories import _do_feo_import

    subsidy = Subsidy(name=f"TestFeoHistoryImport-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    rows = [[None] * 5 for _ in range(1)]
    # ROW_FIELDS локальные — минимальный макет: lvl2/lvl3/item_name/plan_qty/plan_sum
    rows = [["Направление А", "Категория Б", "Позиция В", "1", "1000"]]

    result = await _do_feo_import(
        rows=rows,
        c_subsidy=None, c_lvl2=0, c_lvl3=1, c_lvl4=None, c_lvl5=2,
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=None, c_appendix=None, c_budget=None, c_active=None,
        c_row_plan_qty=3, c_row_plan_sum=4,
        default_subsidy_id=subsidy.id,
        db=db_session, dry_run=False,
        filename="test_import.xlsx", sheet_name="Лист1",
    )
    assert result["errors"] == []
    assert result["created"] >= 1

    runs = (await db_session.execute(
        select(FeoImportRun).where(FeoImportRun.subsidy_id == subsidy.id)
    )).scalars().all()
    assert len(runs) == 1
    run = runs[0]
    assert run.filename == "test_import.xlsx"
    assert run.sheet_name == "Лист1"
    assert run.created_count == result["created"]
    assert run.updated_count == result["updated"]
    assert run.skipped_count == result["skipped"]
    assert run.finished_at is not None

    history_rows = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.source == "import",
            EntityChange.source_ref == run.id,
        )
    )).scalars().all()
    assert len(history_rows) >= 1


@pytest.mark.asyncio
async def test_dry_run_import_creates_no_run_and_no_history(db_session):
    """Предпросмотр (dry_run=True) откатывает транзакцию целиком — не должно
    остаться ни FeoImportRun, ни записей истории (задание волны 2: dry_run не
    пишет ни прогон, ни историю)."""
    from app.routers.feo_categories import _do_feo_import

    subsidy = Subsidy(name=f"TestFeoHistoryDryRun-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    subsidy_id = subsidy.id

    rows = [["Направление А", "Категория Б", "Позиция В", "1", "1000"]]

    result = await _do_feo_import(
        rows=rows,
        c_subsidy=None, c_lvl2=0, c_lvl3=1, c_lvl4=None, c_lvl5=2,
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=None, c_appendix=None, c_budget=None, c_active=None,
        c_row_plan_qty=3, c_row_plan_sum=4,
        default_subsidy_id=subsidy_id,
        db=db_session, dry_run=True,
        filename="test_dry_run.xlsx", sheet_name="Лист1",
    )
    assert result["errors"] == []
    assert result["dry_run"] is True

    runs = (await db_session.execute(
        select(FeoImportRun).where(FeoImportRun.subsidy_id == subsidy_id)
    )).scalars().all()
    assert runs == []

    history_rows = (await db_session.execute(
        select(EntityChange).where(EntityChange.source == "import")
    )).scalars().all()
    # dry_run в этом же тесте не должен был написать ничего с source='import'
    # (другие тесты этого файла коммитят свои строки в отдельных транзакциях
    # и не видны здесь — db_session переиспользует одну транзакцию с
    # savepoint-откатом на тест, см. conftest.py).
    assert history_rows == []


@pytest.mark.asyncio
async def test_wish_born_planned_item_gets_wish_source(db_session, test_org):
    """auto_assign_planned_items (plan_autoassign.py) — позиция, рождённая из
    WishItem, получает source='wish' + id этой заявки (владелец: «если
    плановая появилась из заявки, то пишется, на основании какой»)."""
    from app.services.plan_autoassign import auto_assign_planned_items
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    subsidy = Subsidy(name=f"TestFeoHistoryWish-{uuid.uuid4().hex[:8]}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория для заявки")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    wish = Wish(title="Тестовая заявка", status="draft", org_id=subsidy.org_id)
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    wi = WishItem(
        wish_id=wish.id, item_name="Бумага А4", quantity=Decimal("10"),
        unit="шт", total_price=Decimal("1000"), feo_category_id=cat.id,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)

    await auto_assign_planned_items([wi], cat.id, db_session, note="тестом")
    await db_session.commit()

    assert wi.feo_planned_item_id is not None
    rows = await _history_rows(db_session, feo_history.ENTITY_FEO_ITEM, wi.feo_planned_item_id)
    created_rows = [r for r in rows if r.field_name == feo_history.FIELD_CREATED_MARKER]
    assert len(created_rows) == 1
    assert created_rows[0].source == "wish"
    assert created_rows[0].source_ref == wish.id
