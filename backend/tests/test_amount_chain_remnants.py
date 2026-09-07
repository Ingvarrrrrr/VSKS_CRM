"""test_amount_chain_remnants.py — ПРАВИЛО №6, волна 4b-2c (2026-09-07):
остатки старых truthy-цепочек «сумма закупки» вне app.services.purchase_amounts,
найденные QA в contracts.py / reports.py / subsidy_plan_graph_export.py.

Общий сценарий регрессии для всех трёх мест: contract_price=0 (легитимный
НОЛЬ, не «пусто») + planned_total_price=1000. Старый код (`x or y or 0`,
Python truthy) молча проваливал 0 дальше по цепочке и показывал 1000. Новый
код (contract_amount()/purchase_amounts()/load_purchase_amounts() —
единственный источник, `is not None`) обязан вернуть 0.

Волна 4b-2d (2026-09-07) добавляет остальные места из того же аудита:
documents (contexts_build.py/stages_amounts.py/fabrikant_package.py),
publications.py, subsidy_finance.py, feo_plan_reads.py (unassigned),
purchase_lists.py (my-tasks), reports.py (/api/reports/summary active_sum).
purchase_receipts.py (авансовый Contract.max_amount) покрыт кодом, идентичным
уже протестированному contracts.py::_enrich_contract_from_purchases (тот же
паттерн contract_amount() + фолбэк на purchase_amounts().plan) — отдельным
тестом не дублируется. wish_convert.py D5-долг (contractor через
set_item_contractor) покрыт в test_item_contractor_write_paths.py.
"""
import io
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session, org_id=None, **kwargs):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=1_000_000,
        require_planned_dates=False, org_id=org_id, **kwargs,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


# ---------------------------------------------------------------------------
# 1) contracts.py::_enrich_contract_from_purchases — было `total_nmck or
#    contract_price or planned_total_price`
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contracts_enrich_default_not_truthy_on_zero_contract_price(
    db_session, make_purchase,
):
    from app.models.contract import Contract
    from app.routers.contracts import _enrich_contract_from_purchases

    contract = Contract(number=f"C-{uuid.uuid4().hex[:8]}", contract_type="single", max_amount=None)
    db_session.add(contract)
    await db_session.commit()
    await db_session.refresh(contract)

    p = await make_purchase(
        contract_id=contract.id,
        contract_price=Decimal("0"),
        planned_total_price=Decimal("1000"),
        total_nmck=None,
    )

    filled = await _enrich_contract_from_purchases(contract, db_session)
    assert filled > 0
    # НЕ 1000 — старый `total_nmck or contract_price or planned_total_price`
    # (truthy) провалил бы легитимный 0 и подставил бы план.
    assert contract.max_amount == Decimal("0")


@pytest.mark.asyncio
async def test_contracts_enrich_falls_back_to_plan_when_no_contract_price(
    db_session, make_purchase,
):
    """Контроль: когда contract_price реально ПУСТ (None, не 0) — фолбэк на
    purchase_amounts(p).plan по-прежнему работает (не регресс в другую сторону)."""
    from app.models.contract import Contract
    from app.routers.contracts import _enrich_contract_from_purchases

    contract = Contract(number=f"C-{uuid.uuid4().hex[:8]}", contract_type="single", max_amount=None)
    db_session.add(contract)
    await db_session.commit()
    await db_session.refresh(contract)

    p = await make_purchase(
        contract_id=contract.id,
        contract_price=None,
        planned_total_price=Decimal("1000"),
        total_nmck=None,
    )

    filled = await _enrich_contract_from_purchases(contract, db_session)
    assert filled > 0
    assert contract.max_amount == Decimal("1000")


# ---------------------------------------------------------------------------
# 2) reports.py::export_subsidy_report_xlsx, колонка L «Сумма договора, руб.»
#    — было `contract_price or planned_total_price`
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reports_xlsx_contract_column_not_truthy_on_zero(
    client, db_session, make_purchase, auth_headers,
):
    from openpyxl import load_workbook
    from app.services.purchase_amounts import contract_amount

    subsidy = await _make_subsidy(db_session)
    p = await make_purchase(
        status="contracted",
        subsidy_id=subsidy.id,
        contract_price=Decimal("0"),
        planned_total_price=Decimal("1000"),
    )
    expected = contract_amount(p)
    assert expected == Decimal("0")  # sanity: сценарий действительно бьёт по truthy-багу

    resp = await client.get(f"/api/reports/subsidy/{subsidy.id}/xlsx", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    # reports.py: row = 6 — первая (и здесь единственная) строка данных, колонка L = 12.
    cell_val = ws.cell(row=6, column=12).value
    # НЕ "1 000.00" — contract_amount(), не подмена план-суммой.
    assert cell_val == "0.00", f"колонка L = {cell_val!r}, ожидалось '0.00' (не 1000 от плана)"


# ---------------------------------------------------------------------------
# 3) subsidy_plan_graph_export.py::export_plan_graph_excel, секция «закупки
#    без категории ФЭО» — было `final_total_amount or planned_total_price or 0`
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subsidy_plan_graph_export_matches_purchase_amounts(
    client, db_session, make_purchase, test_org, auth_headers,
):
    from openpyxl import load_workbook
    from app.services.purchase_amounts import purchase_amounts

    subsidy = await _make_subsidy(db_session, org_id=test_org.id)
    # make_purchase() хардкодит item_name="Test purchase" (не переопределяется через
    # kwargs — Purchase() падает на "multiple values for keyword argument"); эта
    # закупка — единственная итемлесс-закупка данной субсидии в изолированной
    # транзакции теста, так что фиксированное имя уникально идентифицирует строку.
    p = await make_purchase(
        status="contracted",
        subsidy_id=subsidy.id,
        contract_price=Decimal("0"),
        planned_total_price=Decimal("1000"),
        final_total_amount=None,
    )
    expected = purchase_amounts(p).effective
    assert expected == Decimal("0")  # sanity: тот же сценарий 0-vs-план

    resp = await client.get(f"/api/subsidies/{subsidy.id}/plan-graph/export", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    wb = load_workbook(io.BytesIO(resp.content))
    # wb.active — сводная сводка («Сводная»); строки закупок — на листе «План закупок».
    ws = wb["План закупок"]
    # Найти строку с нашей закупкой по имени (секция «без категории ФЭО» пишет
    # "    └ {name} — ...руб/ед." в колонку D) и прочитать колонку M
    # («Заказано/факт» — pi["total"], та самая сумма) на той же строке.
    found_row = None
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "Test purchase" in cell.value:
                found_row = cell.row
                break
        if found_row:
            break
    assert found_row is not None, "строка с тестовой закупкой не найдена в выгрузке"
    total_val = ws.cell(row=found_row, column=13).value  # column M
    # НЕ 1000 (planned_total_price) — final_total_amount убран из формулы,
    # эффективная сумма по стадии = contract_price = 0.
    assert float(total_val or 0) == 0.0, f"колонка M = {total_val!r}, ожидалось 0 (не 1000 от плана)"


# ---------------------------------------------------------------------------
# Волна 4b-2d
# ---------------------------------------------------------------------------
# 4) documents/stages_amounts.py::compute_amounts_and_vat — plan_amount_val
#    (total_nmcd/total_nmck/nmck в contexts_build.py) было `p.total_nmck or
#    p.nmck or p.planned_total_price or items_sum_val`; contract_amount_val
#    (contract_price/contract_price_num/contract_price_words) было
#    `p.contract_price or doc_amount_val`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stages_amounts_plan_not_truthy_on_stale_total_nmck(db_session, make_purchase):
    """planned_total_price=0 (актуальный план) при СТАРОМ, не пересинхронизированном
    total_nmck=9999 (легаси-зеркало, см. app.services.purchase_money_writer) — раньше
    total_nmck побеждал по truthy-приоритету цепочки, хотя plan уже 0."""
    from app.services.documents.stages_amounts import compute_amounts_and_vat

    p = await make_purchase(
        status="wishes", planned_total_price=Decimal("0"),
        total_nmck=Decimal("9999"), nmck=Decimal("9999"),
    )
    amounts = compute_amounts_and_vat(p, "order_purchase")
    assert amounts["plan_amount_val"] == 0.0, (
        f"plan_amount_val={amounts['plan_amount_val']!r}, ожидалось 0.0 "
        "(не устаревший total_nmck=9999)"
    )


@pytest.mark.asyncio
async def test_stages_amounts_contract_price_not_truthy_on_zero(db_session, make_purchase):
    """contract_price=0 (легитимный ноль) + planned_total_price=1000 на стадии
    ДО договора — doc_amount_val (сумма документа) в этом случае = 1000 (план).
    Старое `p.contract_price or doc_amount_val` подменяло 0 на 1000."""
    from app.services.documents.stages_amounts import compute_amounts_and_vat

    p = await make_purchase(
        status="plan_schedule", contract_price=Decimal("0"), planned_total_price=Decimal("1000"),
    )
    amounts = compute_amounts_and_vat(p, "order_purchase")
    assert amounts["doc_amount_val"] == 1000.0  # sanity: подтверждает, что фолбэк-цель реально другая
    assert amounts["contract_amount_val"] == 0.0, (
        f"contract_amount_val={amounts['contract_amount_val']!r}, ожидалось 0.0 (не doc_amount_val=1000)"
    )


# ---------------------------------------------------------------------------
# 5) publications.py::_build_publish_payload — было `float(p.total_nmck or
#    p.nmck or p.planned_total_price or 0) or sum(items...)`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publications_nmck_not_truthy_on_zero_plan(db_session, make_purchase):
    from app.models.purchase_item import PurchaseItem
    from app.routers.publications import _build_publish_payload

    p = await make_purchase(status="plan_schedule", planned_total_price=Decimal("0"), total_nmck=None, nmck=None)
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Item", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("500"), total_price=Decimal("500"),
    ))
    await db_session.commit()

    payload = await _build_publish_payload(p.id, db_session)
    # НЕ 500 (Σ items) — plan=0 легитимен и не должен маскироваться позициями.
    assert payload["nmck"] == 0.0, f"nmck={payload['nmck']!r}, ожидалось 0.0 (не Σ items=500)"


# ---------------------------------------------------------------------------
# 6) subsidy_finance.py::financial_plan — obligations_monthly было
#    `Decimal(str(p.contract_price or 0))`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subsidy_finance_obligations_not_truthy_on_zero(
    client, db_session, make_purchase, admin_headers, test_org,
):
    from datetime import date as _date

    # get_visible_subsidy_ids по умолчанию видит только субсидии СВОЕЙ орг —
    # subsidy без org_id ни у кого не видна (0 покрытия был бы дефектом, см.
    # feedback_autorule_needs_coverage_on_prod_data): привязываем к test_org,
    # admin_headers — org_admin с полной видимостью своей орг по умолчанию.
    subsidy = await _make_subsidy(db_session, org_id=test_org.id)
    target_year = _date.today().year
    p = await make_purchase(
        status="contracted", subsidy_id=subsidy.id,
        contract_price=Decimal("0"), planned_total_price=Decimal("1000"),
        execution_term=_date(target_year, 3, 15),
    )

    resp = await client.get(
        f"/api/subsidies/{subsidy.id}/financial-plan", params={"year": target_year}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    march = next(m for m in months if m["month"] == 3)
    # НЕ 1000 (planned_total_price) — contract_amount() = contract_price = 0.
    assert march["obligations"] == 0.0, f"obligations марта={march['obligations']!r}, ожидалось 0.0 (не 1000)"


# ---------------------------------------------------------------------------
# 7) feo_plan_reads.py::get_feo_plan_tree — секция "unassigned" читала голый
#    Purchase.planned_total_price, хотя PLANNED_STATUSES включает и стадии
#    ПОСЛЕ договора (work_in_progress/contracted/...).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feo_plan_tree_unassigned_uses_effective_amount(client, db_session, make_purchase, admin_headers, test_org):
    subsidy = await _make_subsidy(db_session, org_id=test_org.id)
    # work_in_progress — стадия ПОСЛЕ договора: contract_price должен
    # побеждать над planned_total_price, а не наоборот.
    await make_purchase(
        status="work_in_progress", subsidy_id=subsidy.id, feo_category_id=None,
        contract_price=Decimal("0"), planned_total_price=Decimal("1000"),
    )

    resp = await client.get(
        "/api/feo-categories/plan-tree", params={"subsidy_id": subsidy.id}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    unassigned = resp.json()["unassigned"]
    assert unassigned["purchase_count"] == 1
    # НЕ 1000 (planned_total_price) — effective_amount_expr() на стадии
    # work_in_progress = contract_price = 0.
    assert unassigned["amount"] == 0.0, f"unassigned.amount={unassigned['amount']!r}, ожидалось 0.0 (не 1000)"


# ---------------------------------------------------------------------------
# 8) purchase_lists.py::my_tasks — "contract_price" карточки канбана читала
#    голый p.contract_price, теряя Σ ContractItem, когда contract_price NULL.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purchase_lists_my_tasks_contract_price_uses_contract_items(
    client, db_session, make_purchase, test_user, auth_headers,
):
    from app.models.contract_item import ContractItem

    p = await make_purchase(
        status="contracted", contract_price=None, planned_total_price=Decimal("1000"),
        assigned_user_id=test_user.id,
    )
    db_session.add(ContractItem(
        purchase_id=p.id, name="Позиция договора", quantity=Decimal("1"),
        unit="шт", unit_price=Decimal("300"), total=Decimal("300"),
    ))
    await db_session.commit()

    resp = await client.get("/api/purchases/my-tasks", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["id"] == p.id)
    # НЕ 0.0 (голый p.contract_price=None → float(None or 0)) — contract_amount()
    # обязан подхватить Σ ContractItem.total, когда contract_price не задан.
    assert row["contract_price"] == 300.0, f"contract_price={row['contract_price']!r}, ожидалось 300.0 (Σ ContractItem)"


# ---------------------------------------------------------------------------
# 9) reports.py::report_summary — totals.active_sum было
#    `p["contract_price"] or p["planned_total_price"]` на уже сериализованных
#    dict (0.0 неотличим от «нет договора»).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reports_summary_active_sum_not_truthy_on_zero(client, db_session, make_purchase, admin_headers, test_org):
    subsidy = await _make_subsidy(db_session, org_id=test_org.id)
    await make_purchase(
        status="contracted", subsidy_id=subsidy.id,
        contract_price=Decimal("0"), planned_total_price=Decimal("1000"),
    )

    resp = await client.get("/api/reports/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    totals = resp.json()["totals"]
    assert totals["active_count"] >= 1
    # НЕ 1000 (planned_total_price) — contract_amount()=0 не должен подменяться планом.
    assert totals["active_sum"] == 0.0, f"active_sum={totals['active_sum']!r}, ожидалось 0.0 (не 1000)"
