"""Тест GET /api/purchases/?search= находит закупку по составу (позициям),
не только по полям её шапки (item_name/subject/registry_number/…).

Владелец (2026-09-20): «Поиск» не находил ни одной закупки, в которой лежит
«Рукав пожарный» — сама закупка называлась иначе, товар был только позицией
внутри неё. См. app/services/purchase_search.py (единая сборка условия,
переиспользуется GET /purchases, GlobalSearch.vue, TaskEditDialog.vue,
VehicleRepairsTab.vue — Правило №6).

Видимость (app/auth/visibility.py): у org_admin без явной orgId-привязки
список закупок INNER JOIN’ится на Subsidy (needs_subsidy_join) — закупка без
subsidy_id из своей организации в выдачу не попадёт вовсе, ДО применения
search. Поэтому каждая тестовая закупка ниже висит на Subsidy её организации,
и assigned_user_id=test_admin_user.id (иначе build_visibility_clause отфильтрует
её как «не мою» — у org_admin без иерархии видимость сведена к «только свои»).
"""
import pytest
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract_item import ContractItem
from app.models.subsidy import Subsidy


async def _mk_subsidy(db_session, org_id):
    s = Subsidy(name="TestSubsidy", year=2026, budget=0, org_id=org_id, require_planned_dates=False)
    db_session.add(s)
    await db_session.flush()
    return s


@pytest.mark.asyncio
async def test_search_finds_purchase_by_item_name(client, db_session, admin_headers, test_admin_user, test_org):
    subsidy = await _mk_subsidy(db_session, test_org.id)
    # Закупка называется нейтрально — совпадения со строкой поиска в шапке нет.
    p = Purchase(
        item_name="Закупка хозтоваров", subject="Поставка расходных материалов",
        status="planned", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Рукав пожарный", quantity=2, unit="шт",
        unit_price=1000, total_price=2000,
    ))
    # Другая закупка — никак не связана с рукавом, не должна попасть в выдачу.
    other = Purchase(
        item_name="Закупка канцтоваров", subject="Бумага и ручки",
        status="planned", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(PurchaseItem(purchase_id=other.id, item_name="Бумага А4", quantity=10, unit="уп"))
    await db_session.commit()

    resp = await client.get("/api/purchases/?search=рукав", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert p.id in ids, f"Закупка с позицией «Рукав пожарный» не найдена: {resp.json()}"
    assert other.id not in ids, "Несвязанная закупка не должна попадать в выдачу по этому запросу"


@pytest.mark.asyncio
async def test_search_finds_purchase_by_contract_item_name(client, db_session, admin_headers, test_admin_user, test_org):
    """То же самое, но совпадение только в contract_items.name (Phase 27.1 —
    «фактически заказано по договору», своё поле name, не item_name)."""
    subsidy = await _mk_subsidy(db_session, test_org.id)
    p = Purchase(
        item_name="Прочая закупка", subject="Прочее",
        status="planned", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(ContractItem(purchase_id=p.id, name="Рукав пожарный Ф51"))
    await db_session.commit()

    resp = await client.get("/api/purchases/?search=пожарный", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert p.id in ids, f"Закупка с contract_item «Рукав пожарный Ф51» не найдена: {resp.json()}"


@pytest.mark.asyncio
async def test_search_still_matches_purchase_header_fields(client, db_session, admin_headers, test_admin_user, test_org):
    """Регресс: старое поведение (поиск по item_name/subject самой закупки) не сломано."""
    subsidy = await _mk_subsidy(db_session, test_org.id)
    p = Purchase(
        item_name="Закупка светового оборудования", subject="Поставка прожекторов",
        status="planned", assigned_user_id=test_admin_user.id, subsidy_id=subsidy.id,
    )
    db_session.add(p)
    await db_session.commit()

    resp = await client.get("/api/purchases/?search=прожектор", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert p.id in ids
