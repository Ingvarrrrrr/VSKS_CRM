"""Задача 05.10.2026 («ФАДМ 2026_2» из листа GoodsService) — тест загрузчика
v2 (scripts/fadm_sheet_load/sheet_v2_parse.py + sheet_v2_build.py) на
маленьком синтетическом CSV, покрывающем:
  - Разовый договор;
  - Рамочный накопительный (2 заказа);
  - Рамочный с суммой (служебная строка-лимит + 1 заказ);
  - авансовую закупку (контрагент = ФИО живого сотрудника);
  - привязку платежа по номеру п/п + ИНН + сумма + дата.

Run: docker compose -p vsks_crm exec -T backend_a pytest tests/test_fadm_goodsservice_load.py -q
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bank_statement import BankPayment
from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.organization import Organization
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User

from scripts.fadm_sheet_load.sheet_v2_parse import parse_goodsservice_csv
from scripts.fadm_sheet_load.sheet_v2_build import run_build_v2, find_existing_target_subsidy

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid.uuid4().hex[:8]


# 74 колонок A..BV — индексы см. sheet_v2_parse.py. Заполняем только то, что
# нужно тесту, хвост колонок (X..AC, BH..) — пустые строки.
HEADER = [""] * 74


def _row(**kw) -> list[str]:
    r = [""] * 74
    defaults = {
        0: "1", 8: "1", 9: "шт.", 12: "True",
    }
    for idx, val in defaults.items():
        r[idx] = val
    mapping = {
        "purchase_no": 3, "order_no": 4, "subject": 5, "item_name": 6,
        "contractor": 7, "plan_price": 10, "plan_sum": 11, "confirmed": 12,
        "final_price": 13, "final_sum": 14, "sum_to_pay_delivery": 15,
        "sum_to_pay_contract": 16, "inn": 17, "contract_number": 18,
        "contract_date": 19, "payment_doc": 20, "payment_purpose": 21,
        "payment_date": 22, "goods_services": 29, "feo_direction": 30,
        "feo_type": 31, "purchase_done": 44, "contract_signed": 45,
        "ordered": 46, "delivered": 47, "paid": 48,
    }
    r[2] = kw.pop("contract_kind", "Разовый")
    for key, val in kw.items():
        r[mapping[key]] = val
    return r


def _write_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(HEADER)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


async def _source_subsidy(db_session) -> Subsidy:
    org = Organization(name=f"Org-{_uid()}")
    db_session.add(org)
    await db_session.flush()
    s = Subsidy(name=f"ФАДМ_2026-test-{_uid()}", year=2026, require_planned_dates=False, org_id=org.id)
    db_session.add(s)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=s.id, name="Прочее", level=1, parent_id=None)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _employee(db_session, org_id) -> User:
    u = User(
        email=f"emp-{_uid()}@gala.local", username=f"emp-{_uid()}",
        full_name="Петрова Анна Ивановна", role="employee",
        org_id=org_id, password_hash="x", exclude_from_directory=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _admin_user(db_session) -> User:
    u = User(
        email=f"admin-{_uid()}@gala.local", username=f"admin-{_uid()}",
        full_name="Админ Тестовый", role="superadmin", password_hash="x",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def test_goodsservice_loader_three_contract_types(db_session, tmp_path):
    source = await _source_subsidy(db_session)
    employee = await _employee(db_session, source.org_id)
    current_user = await _admin_user(db_session)

    bp = BankPayment(
        payment_number="555", payment_date=date(2026, 3, 1), status="ИСПОЛНЕН",
        amount=Decimal("1000.00"), payee_inn="7700000001",
        basis_doc_text="№ 091-10-2026-008 от 28.01.2026",
        parsed_contract_number="850000713106", parsed_contract_date=date(2023, 11, 24),
    )
    db_session.add(bp)
    await db_session.commit()

    rows_raw = [
        # Разовый, с платежом
        _row(purchase_no="1", order_no="1", subject="Разовая закупка", item_name="Товар А",
             contractor="ООО Ромашка", plan_price="1000", plan_sum="1000", confirmed="True",
             final_price="1000", final_sum="1000", sum_to_pay_delivery="1000",
             inn="7700000001", contract_number="Д-1", contract_date="2026-01-01",
             payment_doc="555", payment_purpose="оплата", payment_date="2026-03-02",
             goods_services="Товары", contract_signed="True", delivered="True",
             contract_kind="Разовый"),
        # Рамочный накопительный — голова неявная, 2 заказа
        _row(purchase_no="2", order_no="1", subject="Заказ 1", item_name="Услуга Б",
             contractor="ООО Рамка", inn="7700000002", plan_price="500", plan_sum="500",
             final_sum="500", contract_number="Р-2", contract_date="2026-01-05",
             goods_services="Услуги", contract_signed="True", ordered="True",
             contract_kind="Рамочный накопительный"),
        _row(purchase_no="2", order_no="2", subject="Заказ 2", item_name="Услуга Б2",
             contractor="ООО Рамка", inn="7700000002", plan_price="700", plan_sum="700",
             final_sum="700", contract_number="Р-2", contract_date="2026-01-05",
             goods_services="Услуги", contract_signed="True", ordered="True",
             contract_kind="Рамочный накопительный"),
        # Рамочный с суммой — служебная строка-лимит + 1 заказ
        _row(purchase_no="3", order_no="Установка предельной суммы договора",
             subject="Лимит", item_name="Лимит", contractor="ООО Лимит",
             inn="7700000003", plan_sum="5000", final_sum="5000",
             contract_number="Л-3", contract_date="2026-01-10",
             contract_kind="Рамочный с суммой"),
        _row(purchase_no="3", order_no="1", subject="Заказ лимита 1", item_name="Товар В",
             contractor="ООО Лимит", inn="7700000003", plan_sum="300", final_sum="300",
             contract_number="Л-3", contract_date="2026-01-10",
             goods_services="Товары", contract_signed="True",
             contract_kind="Рамочный с суммой"),
        # Авансовая — контрагент = ФИО сотрудника
        _row(purchase_no="4", order_no="1", subject="Авансовый отчёт", item_name="Канцтовары",
             contractor="Петрова Анна Ивановна", plan_sum="200", final_sum="200",
             contract_number="АВАНСОВЫЙ ОТЧЕТ 7", goods_services="Товары",
             contract_signed="True", ordered="True", contract_kind="Разовый"),
    ]
    csv_text = _write_csv(rows_raw)
    csv_path = tmp_path / "goodsservice.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    rows = parse_goodsservice_csv(csv_path)
    assert len(rows) == 6

    target_name = f"ФАДМ 2026_2-test-{_uid()}"
    subsidy, counters = await run_build_v2(
        db_session, rows=rows, source_name=source.name, target_name=target_name,
        budget=Decimal("10000"), agreement_number="091-10-2026-008",
        current_user=current_user, replace=False,
    )
    await db_session.commit()

    assert counters.single_purchases == 2   # разовая + авансовая
    assert counters.framework_heads == 2    # накопительный + с суммой
    assert counters.framework_orders == 3   # 2 + 1

    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()
    assert len(purchases) == 2 + 2 + 3  # разовая, авансовая, 2 головы, 3 заказа

    advance = next(p for p in purchases if p.purchase_method == "advance")
    assert advance.assigned_user_id == employee.id
    assert advance.reimbursement_user_id == employee.id

    # Лимит рамки — Contract.max_amount головы «Рамочный с суммой»
    limit_head = next(p for p in purchases if p.purchase_contract_type == "framework_cumulative"
                      and p.parent_purchase_id is None and p.contract_price and p.contract_price > 0
                      and any(o.parent_purchase_id == p.id for o in purchases if o.contract_price == Decimal("300")))
    contract = await db_session.get(Contract, limit_head.contract_id)
    assert contract is not None
    assert contract.max_amount == Decimal("5000")

    # Платёж привязан к разовой закупке по номеру+ИНН+сумме+дате
    assert counters.payments_attached == 1
    single = next(p for p in purchases if p.purchase_method == "single" and p.parent_purchase_id is None
                  and p.purchase_contract_type != "framework_cumulative")
    from app.models.payment import Payment
    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == single.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].bank_payment_id == bp.id

    # Доп. задание 05.10.2026 («Бюджет (ФЭО)» карточка показывала бюджет
    # источника вместо целевых 15 880 100): явный FeoCategory.budget,
    # скопированный из source, обязан быть снят на ВСЕХ узлах нового дерева,
    # а две агрегатные FeoPlannedItem (feo_amount, is_feo_breakdown=True)
    # должны дать ровно товары/услуги/итого из листа GoodsService — не из
    # дерева source.
    from app.services.subsidy_budget import calculate_budgets_bulk
    from app.services.type_totals import subsidy_type_totals

    categories = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalars().all()
    assert all(c.budget is None for c in categories), "budget скопированных узлов не снят"

    budgets = await calculate_budgets_bulk(db_session, [subsidy.id])
    assert budgets[subsidy.id] == pytest.approx(4380000.00 + 11500100.00)

    tt = await subsidy_type_totals(db_session, [subsidy.id])
    row = tt[subsidy.id]
    assert row["feo_goods"] == pytest.approx(4380000.00)
    assert row["feo_services"] == pytest.approx(11500100.00)
    assert row["feo_unspecified"] == pytest.approx(0.0)


async def test_goodsservice_loader_replace(db_session):
    source = await _source_subsidy(db_session)
    current_user = await _admin_user(db_session)
    rows_raw = [_row(purchase_no="1", order_no="1", subject="X", item_name="X",
                      contractor="ООО X", inn="7700000009", plan_sum="100",
                      final_sum="100", contract_number="Д-X", contract_kind="Разовый")]
    csv_text = _write_csv(rows_raw)
    from scripts.fadm_sheet_load.sheet_v2_parse import _row as parse_row  # noqa: F401 (sanity import only)
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkstemp(suffix=".csv")[1])
    tmp.write_text(csv_text, encoding="utf-8")
    rows = parse_goodsservice_csv(tmp)

    name = f"ФАДМ 2026_2-replace-{_uid()}"
    subsidy1, _ = await run_build_v2(
        db_session, rows=rows, source_name=source.name, target_name=name,
        budget=Decimal("100"), agreement_number="091-10-2026-008",
        current_user=current_user, replace=False,
    )
    await db_session.commit()
    # Очистить identity map перед --replace: delete_target_subsidy полагается
    # на ON DELETE CASCADE В БД (subsidies.id → feo_categories.subsidy_id), а
    # ORM-объекты FeoCategory головы subsidy1, ещё живущие в сессии с прошлого
    # run_build_v2, иначе получают explicit UPDATE subsidy_id=NULL от
    # session-level cascade раньше DELETE — и падают на NOT NULL (subsidy_id
    # NOT NULL). В реальном скрипте каждый запуск — своя свежая async_session,
    # этой коллизии там нет.
    db_session.expunge_all()

    with pytest.raises(ValueError):
        await run_build_v2(
            db_session, rows=rows, source_name=source.name, target_name=name,
            budget=Decimal("100"), agreement_number="091-10-2026-008",
            current_user=current_user, replace=False,
        )

    subsidy2, _ = await run_build_v2(
        db_session, rows=rows, source_name=source.name, target_name=name,
        budget=Decimal("100"), agreement_number="091-10-2026-008",
        current_user=current_user, replace=True,
    )
    await db_session.commit()
    assert subsidy2.id != subsidy1.id
    gone = await db_session.get(Subsidy, subsidy1.id)
    assert gone is None
