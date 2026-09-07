"""ПРАВИЛО №6, группа D7: шапка договора закупки — один источник истины.

Покрывает:
  1. contract_header() — чистая функция, offline (SimpleNamespace, без БД):
     с договором / без договора / у договора пустое поле (fallback+warning).
  2. PUT /api/purchases/{id} с заданным contract_id игнорирует входящие
     contract_number/contract_date/purchase_contract_type/contractor_id
     (contract_fields_ignored в ответе), без 422.
  3. PATCH /api/purchases/{id} — та же защита.
  4. PUT /api/contracts/{id} каскадирует новый number/date в связанные
     закупки ЧЕРЕЗ _sync_purchase_from_contract (единственный писатель).
  5. Сериализатор списка закупок не даёт N+1 на contract relationship —
     тот же query-паттерн, что list_purchases (selectinload(Purchase.contract)).
  6. Прод-ревизия 2026-09-07 (5 закупок с contract_date, а contracts.date
     NULL): _sync_purchase_from_contract НЕ затирает непустой кэш пустым
     полем Contract; миграция y7a9c1e3g5i7 сначала дозаполняет Contract.date
     из СОГЛАСНЫХ закупок, а при конфликте (разные значения) не трогает
     Contract вообще.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select, event, text
from sqlalchemy.orm import selectinload

from app.services.purchase_contract_header import contract_header


def _load_migration_module():
    """Загружает alembic/versions/y7a9c1e3g5i7_...py по пути файла (не через
    `import alembic.versions.xxx` — локальный каталог backend/alembic и
    установленный pip-пакет `alembic` (см. `from alembic import op` внутри
    самих миграций) делят одно и то же top-level имя; dotted-import по пакету
    рисковал бы коллизией. importlib по пути — как это делает сам alembic
    ScriptDirectory внутри, без риска затенить настоящий пакет."""
    import importlib.util
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(
        here, "..", "alembic", "versions",
        "y7a9c1e3g5i7_sync_purchase_contract_header_from_contract.py",
    ))
    spec = importlib.util.spec_from_file_location("_y7a9c1e3g5i7_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. contract_header() — offline, no DB
# ---------------------------------------------------------------------------

def _mk_purchase(contract_id=1, contract_number="CACHE-1", contract_date_=date(2020, 1, 1),
                  purchase_contract_type="single", contractor_id=5):
    return SimpleNamespace(
        id=42, contract_id=contract_id, contract_number=contract_number,
        contract_date=contract_date_, purchase_contract_type=purchase_contract_type,
        contractor_id=contractor_id,
    )


def _mk_contract(id_=1, number="REAL-1", date_=date(2026, 3, 1), contract_type="framework_cumulative",
                  contractor_id=99):
    return SimpleNamespace(id=id_, number=number, date=date_, contract_type=contract_type,
                            contractor_id=contractor_id)


def test_contract_header_with_contract_overrides_cache():
    """contract_id задан, Contract загружен и полностью заполнен — значения ИЗ Contract, не из кэша."""
    p = _mk_purchase()
    c = _mk_contract()
    hdr = contract_header(p, c)
    assert hdr.contract_number == "REAL-1"
    assert hdr.contract_date == date(2026, 3, 1)
    assert hdr.purchase_contract_type == "framework_cumulative"
    assert hdr.contractor_id == 99
    assert hdr.source == "contract"


def test_contract_header_without_contract_id_uses_cache():
    """Нет contract_id (чек/авансовый/ручной ввод) — как раньше, из колонок закупки."""
    p = _mk_purchase(contract_id=None)
    hdr = contract_header(p, contract=None)
    assert hdr.contract_number == "CACHE-1"
    assert hdr.contract_date == date(2020, 1, 1)
    assert hdr.purchase_contract_type == "single"
    assert hdr.contractor_id == 5
    assert hdr.source == "purchase"


def test_contract_header_contract_not_loaded_falls_back_to_cache():
    """contract_id задан, но вызывающий не передал Contract (не выбрал relationship) — кэш, не падаем."""
    p = _mk_purchase()
    hdr = contract_header(p, contract=None)
    assert hdr.contract_number == "CACHE-1"
    assert hdr.source == "purchase"


def test_contract_header_empty_contract_field_falls_back_with_warning(caplog):
    """У Contract пустое number/date/type — fallback на кэш ПОЛЕ-ЗА-ПОЛЕМ, contractor_id берётся из Contract если есть."""
    p = _mk_purchase(contract_number="OLD-77", contract_date_=date(2019, 5, 5),
                      purchase_contract_type="competitive")
    c = _mk_contract(number="", date_=None, contract_type=None, contractor_id=None)
    import logging
    with caplog.at_level(logging.WARNING):
        hdr = contract_header(p, c)
    assert hdr.contract_number == "OLD-77"
    assert hdr.contract_date == date(2019, 5, 5)
    assert hdr.purchase_contract_type == "competitive"
    # contractor_id: Contract.contractor_id is None -> fallback на p.contractor_id (5)
    assert hdr.contractor_id == 5
    assert hdr.source == "contract"
    assert "falling back" in caplog.text


def test_contract_header_mismatched_contract_id_ignored():
    """Переданный Contract с другим id (не тот, на который указывает p.contract_id) — не используется."""
    p = _mk_purchase(contract_id=1)
    c = _mk_contract(id_=999)
    hdr = contract_header(p, c)
    assert hdr.source == "purchase"
    assert hdr.contract_number == "CACHE-1"


# ---------------------------------------------------------------------------
# 2-4. PUT/PATCH purchases + PUT contracts — real DB via db_session/client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_purchase_with_contract_id_ignores_incoming_header_fields(
    db_session, client, admin_headers, test_admin_user,
):
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="Д-100", date=date(2026, 1, 10), contract_type="single")
    db_session.add(contract)
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Test",
        contract_id=contract.id, contract_number="Д-100", contract_date=date(2026, 1, 10),
        purchase_contract_type="single", assigned_user_id=test_admin_user.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    body = {
        "contract_id": contract.id,
        "contract_number": "ПОДДЕЛКА-999",
        "contract_date": "2099-01-01",
        "purchase_contract_type": "framework_cumulative",
        "contractor_id": 123456,
        "status": "planned",
        "assigned_user_id": test_admin_user.id,
        "items": [],
    }
    resp = await client.put(
        f"/api/purchases/{p.id}?admin_override=true", json=body, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.get("contract_fields_ignored", [])) == {
        "contract_number", "contract_date", "purchase_contract_type", "contractor_id",
    }
    await db_session.refresh(p)
    # Кэш на закупке остался прежним (из договора), подделка из payload'а не записана.
    assert p.contract_number == "Д-100"
    assert p.contractor_id != 123456


@pytest.mark.asyncio
async def test_patch_purchase_with_contract_id_ignores_incoming_header_fields(
    db_session, client, auth_headers, test_user,
):
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="Д-200", date=date(2026, 2, 20), contract_type="single")
    db_session.add(contract)
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Test patch",
        contract_id=contract.id, contract_number="Д-200",
        assigned_user_id=test_user.id,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.patch(
        f"/api/purchases/{p.id}",
        json={"contract_number": "ПОДМЕНА"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "contract_number" in data["contract_fields_ignored"]
    assert "contract_number" not in data["changed"]
    await db_session.refresh(p)
    assert p.contract_number == "Д-200"


@pytest.mark.asyncio
async def test_put_contract_cascades_via_single_sync_writer(db_session, client, admin_headers):
    """PUT /api/contracts/{id} меняет number/date — связанные закупки подтягивают их
    ЧЕРЕЗ _sync_purchase_from_contract (единый писатель), не отдельную копией логики."""
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="СТАРЫЙ-1", date=date(2025, 1, 1), contract_type="single")
    db_session.add(contract)
    await db_session.flush()

    p1 = Purchase(status="planned", item_type="goods", item_name="A",
                   contract_id=contract.id, contract_number="СТАРЫЙ-1", contract_date=date(2025, 1, 1))
    p2 = Purchase(status="planned", item_type="goods", item_name="B",
                   contract_id=contract.id, contract_number="СТАРЫЙ-1", contract_date=date(2025, 1, 1))
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    body = {
        "number": "НОВЫЙ-2", "date": "2026-06-06", "contract_type": "single",
    }
    resp = await client.put(f"/api/contracts/{contract.id}", json=body, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["n_updated_purchases"] == 2

    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.contract_number == "НОВЫЙ-2"
    assert p1.contract_date == date(2026, 6, 6)
    assert p2.contract_number == "НОВЫЙ-2"
    assert p2.contract_date == date(2026, 6, 6)


# ---------------------------------------------------------------------------
# 5. No N+1: same query pattern list_purchases uses (selectinload(Purchase.contract))
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purchase_list_query_pattern_avoids_n_plus_1_on_contract(db_session):
    """20 закупок с общим Contract — тот же select+selectinload(Purchase.contract),
    что использует list_purchases, должен грузить контракт(ы) ОДНИМ доп. запросом,
    а не одним на закупку (раньше сериализатор читал только кэш-колонки — contract
    не грузился вовсе; теперь читает связанный Contract, обязан оставаться bulk).

    Не идёт через HTTP/visibility (org-иерархия не относится к этой волне) —
    напрямую воспроизводит query+сериализатор из routers/purchases.py::list_purchases
    и services/purchase_serializers.py::_purchase_to_full.
    """
    from app.models.contract import Contract
    from app.models.purchase import Purchase
    from app.services.purchase_serializers import _purchase_to_full

    contract = Contract(number="BULK-1", date=date(2026, 4, 1), contract_type="single")
    db_session.add(contract)
    await db_session.flush()

    purchases = []
    for i in range(20):
        p = Purchase(
            status="planned", item_type="goods", item_name=f"Bulk {i}",
            contract_id=contract.id, contract_number="BULK-1",
        )
        db_session.add(p)
        purchases.append(p)
    await db_session.commit()

    queries: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    from app.database import engine
    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        result = await db_session.execute(
            select(Purchase)
            .options(selectinload(Purchase.contractor), selectinload(Purchase.items),
                     selectinload(Purchase.files), selectinload(Purchase.event),
                     selectinload(Purchase.contract))
            .where(Purchase.id.in_([p.id for p in purchases]))
        )
        loaded = result.scalars().all()
        assert len(loaded) == 20

        queries.clear()  # count only the serialization pass below
        for p in loaded:
            _purchase_to_full(p, contractors={}, subsidies={}, contract=p.contract)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    # Serializer itself must not issue any SQL per-row (contract already
    # loaded via selectinload) — 0 queries expected, well under 20.
    assert len(queries) == 0, f"expected 0 queries during serialization, got {len(queries)}: {queries[:3]}"


# ---------------------------------------------------------------------------
# 6. Прод-ревизия 2026-09-07: пустое поле Contract НЕ затирает непустой кэш
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_purchase_from_contract_does_not_null_out_cache(db_session):
    """Contract.date is NULL, purchase.contract_date уже заполнена (легаси/импорт) —
    _sync_purchase_from_contract НЕ должна затереть её NULL'ом (ровно баг с прода:
    id 799/797/910/846/840 — contract_date есть, contracts.date = NULL)."""
    from app.models.contract import Contract
    from app.models.purchase import Purchase
    from app.routers.purchases import _sync_purchase_from_contract

    contract = Contract(number="Д-НЕТДАТЫ", date=None, contract_type="single")
    db_session.add(contract)
    await db_session.flush()

    p = Purchase(
        status="planned", item_type="goods", item_name="Legacy",
        contract_id=contract.id, contract_number="Д-НЕТДАТЫ", contract_date=date(2019, 3, 3),
    )
    db_session.add(p)
    await db_session.flush()

    await _sync_purchase_from_contract(p, db_session)

    assert p.contract_date == date(2019, 3, 3)


@pytest.mark.asyncio
async def test_migration_backfills_contract_date_when_purchases_agree(db_session):
    """Миграция y7a9c1e3g5i7: Contract.date=NULL, ЕДИНСТВЕННАЯ связанная закупка
    имеет contract_date — договор дозаполняется этим значением (шаг 0a)."""
    mig = _load_migration_module()
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="Д-ОДНА", date=None, contract_type="single")
    db_session.add(contract)
    await db_session.flush()
    p = Purchase(
        status="planned", item_type="goods", item_name="Solo",
        contract_id=contract.id, contract_number="Д-ОДНА", contract_date=date(2021, 7, 15),
    )
    db_session.add(p)
    await db_session.commit()

    await db_session.execute(text(mig.BACKFILL_CONTRACT_DATE_FROM_PURCHASES))
    await db_session.commit()

    await db_session.refresh(contract)
    assert contract.date == date(2021, 7, 15)


@pytest.mark.asyncio
async def test_migration_does_not_backfill_contract_date_on_conflict(db_session):
    """Contract.date=NULL, ДВЕ закупки этого договора с РАЗНЫМИ contract_date —
    настоящий конфликт, миграция НЕ трогает Contract (только отчёт), и не трогает
    ни одну из закупок (обе сохраняют свои значения)."""
    mig = _load_migration_module()
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="Д-КОНФЛИКТ", date=None, contract_type="single")
    db_session.add(contract)
    await db_session.flush()
    p1 = Purchase(status="planned", item_type="goods", item_name="A",
                   contract_id=contract.id, contract_number="Д-КОНФЛИКТ", contract_date=date(2020, 1, 1))
    p2 = Purchase(status="planned", item_type="goods", item_name="B",
                   contract_id=contract.id, contract_number="Д-КОНФЛИКТ", contract_date=date(2022, 2, 2))
    db_session.add_all([p1, p2])
    await db_session.commit()

    await db_session.execute(text(mig.BACKFILL_CONTRACT_DATE_FROM_PURCHASES))
    await db_session.commit()

    await db_session.refresh(contract)
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert contract.date is None
    assert p1.contract_date == date(2020, 1, 1)
    assert p2.contract_date == date(2022, 2, 2)


@pytest.mark.asyncio
async def test_migration_full_upgrade_sql_fixes_prod_scenario_end_to_end(db_session):
    """Полный прогон миграции (0a + forward-sync) на точном прод-сценарии:
    Contract.date=NULL, одна закупка с contract_date — после апгрейда и Contract,
    и Purchase несут одну и ту же (не потерянную) дату."""
    mig = _load_migration_module()
    from app.models.contract import Contract
    from app.models.purchase import Purchase

    contract = Contract(number="Д-ПРОД", date=None, contract_type="single")
    db_session.add(contract)
    await db_session.flush()
    p = Purchase(
        status="planned", item_type="goods", item_name="ProdLike",
        contract_id=contract.id, contract_number="Д-ПРОД", contract_date=date(2018, 9, 9),
    )
    db_session.add(p)
    await db_session.commit()

    await db_session.execute(text(mig.BACKFILL_CONTRACT_DATE_FROM_PURCHASES))
    await db_session.execute(text(mig.BACKFILL_CONTRACT_CONTRACTOR_FROM_PURCHASES))
    await db_session.execute(text(mig.SYNC_PURCHASES_FROM_CONTRACT))
    await db_session.commit()

    await db_session.refresh(contract)
    await db_session.refresh(p)
    assert contract.date == date(2018, 9, 9)
    assert p.contract_date == date(2018, 9, 9)
