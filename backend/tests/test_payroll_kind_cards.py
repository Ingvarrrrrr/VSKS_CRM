"""Задача владельца 21.10.2026 (ХРО_2026, прод): карточка «Оплачено» несла
13 786 384,35 — тов. 3 222 378,00 + усл. 1 555 342,28 = 4 777 720,28, а
оставшиеся 9 008 664,07 (3 закупки на статье ФОТ, item_type=NULL) нигде в
разбивке не показывались и горели «сверх поставленного» (status=work_in_progress,
contract_id=NULL, payment_amount_declared=planned_total_price).

Эта правка: 1) is_payroll_name знает «заработная/заробатная плата»/«зарплата»
(feo_payroll.py); 2) ИмпортФакта/миграция ставят такие закупки в status='paid';
3) 4-я корзина `payroll` (app.services.item_type_split.ALL_KINDS) протянута
через dashboard_type_split/paid_over_delivered/delivered_unpaid_residual/
subsidy_paid_breakdown/metric_drill_rows (ПРАВИЛО №6 — единственный резолвер
«закупка — ФОТ» — app.services.feo_payroll.purchase_payroll_map).

Тесты ниже — закупка в статье ФОТ (feo_categories.is_payroll=True, категория
ПРЯМО на purchases.feo_category_id — как у прод-кейса, НЕ на позиции), status
='paid', payment_amount_declared>0, одна позиция item_type=NULL:
  - paid_over_delivered = 0 (статус 'paid' → effective_amount_expr() берёт
    ТОТ ЖЕ payment_amount_declared, что и «оплачено» — excess=0 по построению);
  - paid_declared_by_kind.payroll == сумма (не "unspecified");
  - стадийная разбивка «Поставлено» (delivered) содержит payroll той же
    суммой (компания 'paid' засчитывается и в "delivered" этапе, см.
    _stage_contributions в dashboard_type_split.py).
"""
import uuid
from decimal import Decimal

import pytest


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"PayrollCardSubsidy-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_payroll_category(db_session, subsidy_id):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(subsidy_id=subsidy_id, level=3, name="ФОТ и иные выплаты", is_payroll=True)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_payroll_purchase(db_session, subsidy_id, category_id, amount: Decimal):
    """Воспроизводит прод-кейс ХРО_2026: категория ФОТ стоит НА ЗАКУПКЕ
    (purchases.feo_category_id), позиция без item_type и без своей
    feo_category_id — именно так создаёт закупки «Импорт факта»."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    p = Purchase(
        subsidy_id=subsidy_id, status="paid", item_name=f"Payroll-{uuid.uuid4().hex[:6]}",
        feo_category_id=category_id,
        planned_total_price=amount, payment_amount_declared=amount,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="ФОТ строка", item_type=None,
        quantity=Decimal("1"), unit_price=amount, total_price=amount,
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


@pytest.mark.asyncio
class TestPayrollKindOnCards:
    async def test_paid_payroll_purchase_has_no_excess(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_payroll_category(db_session, subsidy.id)
        await _make_payroll_purchase(db_session, subsidy.id, cat.id, Decimal("100000"))

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        assert charts.status_code == 200
        row = _find_subsidy_row(charts.json(), subsidy.id)
        assert row["paid_over_delivered"] == pytest.approx(0.0, abs=0.01)

    async def test_paid_declared_by_kind_shows_payroll_not_unspecified(self, client, superadmin_headers, db_session):
        subsidy = await _make_subsidy(db_session)
        cat = await _make_payroll_category(db_session, subsidy.id)
        await _make_payroll_purchase(db_session, subsidy.id, cat.id, Decimal("100000"))

        charts = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row = _find_subsidy_row(charts.json(), subsidy.id)
        by_kind = row["paid_declared_by_kind"]
        assert by_kind["payroll"] == pytest.approx(100000.0, abs=0.01)
        assert by_kind["goods"] == pytest.approx(0.0, abs=0.01)
        assert by_kind["services"] == pytest.approx(0.0, abs=0.01)
        assert by_kind["unspecified"] == pytest.approx(0.0, abs=0.01)
        assert row["paid_declared"] == pytest.approx(100000.0, abs=0.01)

    async def test_delivered_stage_split_contains_payroll(self, client, superadmin_headers, db_session):
        """status='paid' засчитывается и в накопительный этап "delivered"
        (_stage_contributions) — его товары/услуги/ФОТ разбивка через
        /api/dashboard/type-drill обязана видеть ту же закупку как payroll."""
        subsidy = await _make_subsidy(db_session)
        cat = await _make_payroll_category(db_session, subsidy.id)
        p = await _make_payroll_purchase(db_session, subsidy.id, cat.id, Decimal("100000"))

        drill = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered", "kind": "payroll", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill.status_code == 200
        body = drill.json()
        assert body["total"] == pytest.approx(100000.0, abs=0.01)
        assert {r["purchase_id"] for r in body["rows"]} == {p.id}

        # kind=unspecified для этой же закупки/этапа — пусто (сумма ВСЯ в payroll).
        drill_unspec = await client.get(
            "/api/dashboard/type-drill",
            params={"stage": "delivered", "kind": "unspecified", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        assert drill_unspec.json()["total"] == pytest.approx(0.0, abs=0.01)
