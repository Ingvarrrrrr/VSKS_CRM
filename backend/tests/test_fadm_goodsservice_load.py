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
        "payment_date": 22, "plan_y": 24, "goods_services": 29, "feo_direction": 30,
        "feo_type": 31, "purchase_done": 44, "contract_signed": 45,
        "ordered": 46, "delivered": 47, "paid": 48, "to_order_ax": 49,
        "ordered_amt_ay": 50, "delivered_amt_az": 51, "monthly_ba": 52,
        "likely_bb": 53, "nice_to_have_bc": 54, "paid_amt_bd": 55,
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


async def _source_subsidy(db_session, *, category_budget: Decimal | None = None) -> Subsidy:
    org = Organization(name=f"Org-{_uid()}")
    db_session.add(org)
    await db_session.flush()
    s = Subsidy(name=f"ФАДМ_2026-test-{_uid()}", year=2026, require_planned_dates=False, org_id=org.id)
    db_session.add(s)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=s.id, name="Прочее", level=1, parent_id=None, budget=category_budget)
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
             final_price="1000", final_sum="1000", sum_to_pay_delivery="1000", plan_y="1000",
             inn="7700000001", contract_number="Д-1", contract_date="2026-01-01",
             payment_doc="555", payment_purpose="оплата", payment_date="2026-03-02",
             goods_services="Товары", contract_signed="True", delivered="True",
             contract_kind="Разовый"),
        # Рамочный накопительный — голова неявная, 2 заказа
        _row(purchase_no="2", order_no="1", subject="Заказ 1", item_name="Услуга Б",
             contractor="ООО Рамка", inn="7700000002", plan_price="500", plan_sum="500",
             final_sum="500", plan_y="500", contract_number="Р-2", contract_date="2026-01-05",
             goods_services="Услуги", contract_signed="True", ordered="True",
             contract_kind="Рамочный накопительный"),
        _row(purchase_no="2", order_no="2", subject="Заказ 2", item_name="Услуга Б2",
             contractor="ООО Рамка", inn="7700000002", plan_price="700", plan_sum="700",
             final_sum="700", plan_y="700", contract_number="Р-2", contract_date="2026-01-05",
             goods_services="Услуги", contract_signed="True", ordered="True",
             contract_kind="Рамочный накопительный"),
        # Рамочный с суммой — служебная строка-лимит + 1 заказ
        _row(purchase_no="3", order_no="Установка предельной суммы договора",
             subject="Лимит", item_name="Лимит", contractor="ООО Лимит",
             inn="7700000003", plan_sum="5000", final_sum="5000",
             contract_number="Л-3", contract_date="2026-01-10",
             contract_kind="Рамочный с суммой"),
        _row(purchase_no="3", order_no="1", subject="Заказ лимита 1", item_name="Товар В",
             contractor="ООО Лимит", inn="7700000003", plan_sum="300", final_sum="300", plan_y="300",
             contract_number="Л-3", contract_date="2026-01-10",
             goods_services="Товары", contract_signed="True",
             contract_kind="Рамочный с суммой"),
        # Авансовая — контрагент = ФИО сотрудника
        _row(purchase_no="4", order_no="1", subject="Авансовый отчёт", item_name="Канцтовары",
             contractor="Петрова Анна Ивановна", plan_sum="200", final_sum="200", plan_y="200",
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

    # Доп. задание 05.10.2026, п.1 — голова рамочного НЕ несёт сумму заказов.
    # «Рамочный с суммой»: purchase_contract_type='framework_with_amount',
    # Contract.max_amount И Purchase.contract_price головы = лимит (5000),
    # НЕ Σ заказов (300).
    limit_head = next(p for p in purchases if p.purchase_contract_type == "framework_with_amount"
                      and p.parent_purchase_id is None)
    assert limit_head.contract_price == Decimal("5000")
    contract = await db_session.get(Contract, limit_head.contract_id)
    assert contract is not None
    assert contract.max_amount == Decimal("5000")

    # «Рамочный накопительный»: голова без суммы (контракт денег не держит) —
    # НЕ 500+700=1200 (прежний баг, задвоение с заказами в «Ведётся работа»).
    cumulative_head = next(p for p in purchases if p.purchase_contract_type == "framework_cumulative"
                           and p.parent_purchase_id is None)
    assert not cumulative_head.contract_price

    # Доп. задание 05.10.2026, п.2 — план из Y: каждая позиция закупки
    # привязана к своей FeoPlannedItem (feo_planned_item_id), созданной ИЗ Y.
    from app.models.purchase_item import PurchaseItem
    # Голова рамочного с суммой несёт одну позицию на лимит (товар/услуга по
    # заказам, см. sheet_v2_build.py::build_framework) — она не часть плана
    # из Y, исключаем ЯВНО по id головы (НЕ через purchase_contract_type ==
    # 'framework_with_amount' в WHERE — у single/advance этот столбец NULL,
    # а "NULL == 'строка'" в SQL даёт NULL, а не False, и NOT(NULL) тоже NULL
    # → WHERE NULL молча роняет строку из результата: прод-находка этого же
    # прогона, словила single+advance позиции (1000+200) по ошибке).
    with_amount_head_ids = [p.id for p in purchases
                            if p.purchase_contract_type == "framework_with_amount" and p.parent_purchase_id is None]
    items = (await db_session.execute(
        select(PurchaseItem).join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy.id)
        .where(Purchase.id.notin_(with_amount_head_ids) if with_amount_head_ids else True)
    )).scalars().all()
    assert items, "нет ни одной позиции закупки"
    assert all(it.feo_planned_item_id is not None for it in items), \
        "позиция закупки не привязана к плановой позиции (план из Y)"
    plan_ids = {it.feo_planned_item_id for it in items}

    from app.models.feo_planned_item import FeoPlannedItem
    plan_total = (await db_session.execute(
        select(FeoPlannedItem.amount).where(FeoPlannedItem.id.in_(plan_ids))
    )).scalars().all()
    # Σ Y = 1000+500+700+300+200 = 2700 (лимит-строка Y не задана — служебная, не позиция)
    assert sum((Decimal(str(v or 0)) for v in plan_total), Decimal("0")) == Decimal("2700")

    # Платёж привязан к разовой закупке по номеру+ИНН+сумме+дате
    assert counters.payments_attached == 1
    single = next(p for p in purchases if p.purchase_method == "single" and p.parent_purchase_id is None
                  and not p.purchase_contract_type)
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


async def _target_subsidy_with_tree(db_session) -> Subsidy:
    """Субсидия-ЦЕЛЬ для --rebuild-in-place: своё дерево ФЭО с budget на
    КОРНЕВЫХ категориях (как владелец расставил budget на 89 вручную) —
    задание 15.10.2026 требует, чтобы rebuild-in-place НЕ трогал ни дерево,
    ни эти суммы."""
    org = Organization(name=f"Org-{_uid()}")
    db_session.add(org)
    await db_session.flush()
    s = Subsidy(name=f"ФАДМ 2026_2-rebuild-{_uid()}", year=2026, require_planned_dates=False, org_id=org.id)
    db_session.add(s)
    await db_session.flush()
    cat_a = FeoCategory(subsidy_id=s.id, name="Направление А", level=1, parent_id=None, budget=Decimal("1000.00"))
    cat_b = FeoCategory(subsidy_id=s.id, name="Направление Б", level=1, parent_id=None, budget=Decimal("2000.00"))
    db_session.add_all([cat_a, cat_b])
    await db_session.commit()
    await db_session.refresh(s)
    await db_session.refresh(cat_a)
    await db_session.refresh(cat_b)
    return s, cat_a, cat_b


def _rebuild_rows(tmp_path, suffix: str) -> list:
    """Две разовые закупки — D='10' (товар) и D='2' (услуга), намеренно в
    таком порядке в CSV, чтобы проверить сортировку по номеру D (задание
    15.10.2026, п.2 — числом, «2» должна создаться раньше «10»)."""
    rows_raw = [
        _row(purchase_no="10", order_no="1", subject="Закупка десять", item_name="Товар Х",
             contractor="ООО Десять", inn="7711111110", plan_sum="100", final_sum="100", plan_y="100",
             contract_number="Д-10", goods_services="Товары", contract_signed="True",
             contract_kind="Разовый"),
        _row(purchase_no="2", order_no="1", subject="Закупка два", item_name="Услуга У",
             contractor="ООО Два", inn="7722222220", plan_sum="200", final_sum="200", plan_y="200",
             contract_number="Д-2", goods_services="Услуги", contract_signed="True",
             contract_kind="Разовый"),
    ]
    csv_text = _write_csv(rows_raw)
    csv_path = tmp_path / f"goodsservice_rebuild_{suffix}.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    return parse_goodsservice_csv(csv_path)


async def _loader_plan_items_count_and_sum(db_session, category_ids) -> tuple[int, Decimal]:
    """Плановые позиции ЗАГРУЗЧИКА (не бюджетные строки F1/G1, не чужие) —
    фильтр ТОТ ЖЕ префикс notes, что ищет _loader_plan_item_ids в самом
    sheet_v2_rebuild.py (ПРАВИЛО №6 — не второй, расходящийся, фильтр в
    тесте)."""
    from scripts.fadm_sheet_load.sheet_v2_rebuild import LOADER_PLAN_ITEM_NOTE_PREFIX
    from app.models.feo_planned_item import FeoPlannedItem

    if not category_ids:
        return 0, Decimal("0")
    rows = (await db_session.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(category_ids),
            FeoPlannedItem.notes.ilike(f"{LOADER_PLAN_ITEM_NOTE_PREFIX}%"),
        )
    )).scalars().all()
    total = sum((Decimal(str(r.amount)) for r in rows if r.amount is not None), Decimal("0"))
    return len(rows), total


async def test_goodsservice_rebuild_in_place(db_session, tmp_path):
    from scripts.fadm_sheet_load.sheet_v2_rebuild import run_rebuild_in_place
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase_item import PurchaseItem
    from app.models.purchase_paid_confirmation import PurchasePaidConfirmation

    target, cat_a, cat_b = await _target_subsidy_with_tree(db_session)
    current_user = await _admin_user(db_session)

    rows1 = _rebuild_rows(tmp_path, "v1")
    result1 = await run_rebuild_in_place(
        db_session, rows=rows1, target_id=target.id, target_name=None,
        current_user=current_user, snapshot_out=str(tmp_path / "snap1.json"),
    )
    await db_session.commit()

    # Первый прогон — ничего не было создано загрузчиком ранее, значит
    # ничего и не удалилось.
    assert result1.delete_counters.purchases_deleted == 0

    purchases_v1 = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id).order_by(Purchase.id)
    )).scalars().all()
    assert len(purchases_v1) == 2
    # Порядок создания — по D числом: «2» раньше «10», несмотря на порядок в CSV.
    assert "закупка 2" in purchases_v1[0].task_comment
    assert "закупка 10" in purchases_v1[1].task_comment

    # Тип позиций — из AD (goods_services), не угадан иначе.
    items_v1 = (await db_session.execute(
        select(PurchaseItem).join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    assert any(it.item_type == "товар" for it in items_v1)
    assert any(it.item_type == "услуга" for it in items_v1)

    # Дерево/бюджет НЕ тронуты — ни строк F1/G1, ни изменения budget корней.
    # Категории дерева по id (кроме автоматической «Не определена», которую
    # заводит get_or_create_unallocated — она не часть дерева владельца).
    categories = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.id.in_([cat_a.id, cat_b.id]))
    )).scalars().all()
    assert len(categories) == 2
    assert {c.budget for c in categories} == {Decimal("1000.00"), Decimal("2000.00")}
    all_category_ids = (await db_session.execute(
        select(FeoCategory.id).where(FeoCategory.subsidy_id == target.id)
    )).scalars().all()
    plan_budget_rows = (await db_session.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(all_category_ids),
            FeoPlannedItem.name.ilike("План ФЭО (лист GoodsService%"),
        )
    )).scalars().all()
    assert plan_budget_rows == [], "rebuild-in-place не должен создавать строки F1/G1"

    # Снимок плановых позиций загрузчика ПОСЛЕ первого прогона — баг
    # 15.10.2026: delete_loader_created_data искал notes по префиксу БЕЗ
    # "Создано " (create_auto_planned_item дописывает его всегда), старые
    # плановые позиции не удалялись и план задваивался на втором прогоне.
    plan_items_count_v1, plan_items_sum_v1 = await _loader_plan_items_count_and_sum(
        db_session, all_category_ids,
    )
    assert plan_items_count_v1 == 2
    assert plan_items_sum_v1 == Decimal("300")

    # Подтверждение «Оплачено» на одной из закупок — должно попасть в снимок
    # ПЕРЕД тем, как закупка будет удалена следующим прогоном.
    confirmed_purchase = next(p for p in purchases_v1 if "закупка 2" in p.task_comment)
    db_session.add(PurchasePaidConfirmation(
        purchase_id=confirmed_purchase.id, subsidy_id=target.id, status="confirmed",
        decided_by=current_user.id, amount_confirmed=Decimal("200.00"),
    ))
    await db_session.commit()

    # «Чужая» закупка — заведена человеком, НЕ загрузчиком (task_comment без
    # маркера «Таблица GoodsService:») — должна пережить пересборку как есть.
    foreign = Purchase(
        subsidy_id=target.id, status="draft", subject="Чужая закупка (заведена человеком)",
        task_comment="Внесена вручную, не из листа",
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    rows2 = _rebuild_rows(tmp_path, "v2")
    result2 = await run_rebuild_in_place(
        db_session, rows=rows2, target_id=target.id, target_name=None,
        current_user=current_user, snapshot_out=str(tmp_path / "snap2.json"),
    )
    await db_session.commit()

    # Второй прогон удалил РОВНО две закупки загрузчика из первого прогона.
    assert result2.delete_counters.purchases_deleted == 2

    still_foreign = await db_session.get(Purchase, foreign.id)
    assert still_foreign is not None, "чужая закупка не должна удаляться rebuild-in-place"
    assert still_foreign.task_comment == "Внесена вручную, не из листа"

    all_purchases_after = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    # Чужая закупка (1) + пересозданные закупки листа (2).
    assert len(all_purchases_after) == 3
    loader_ids_after = {p.id for p in all_purchases_after if p.task_comment and p.task_comment.startswith("Таблица GoodsService:")}
    assert len(loader_ids_after) == 2
    # Пересозданные — это НОВЫЕ id, не те же записи, что в первом прогоне.
    assert loader_ids_after.isdisjoint({p.id for p in purchases_v1})

    # Дерево/бюджет снова не тронуты вторым прогоном.
    categories_after = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.id.in_([cat_a.id, cat_b.id]))
    )).scalars().all()
    assert {c.budget for c in categories_after} == {Decimal("1000.00"), Decimal("2000.00")}

    # Плановые позиции загрузчика НЕ задвоились — старые удалены ПЕРЕД
    # пересборкой (regression-проверка бага 15.10.2026, см. комментарий выше
    # у plan_items_count_v1).
    plan_items_count_v2, plan_items_sum_v2 = await _loader_plan_items_count_and_sum(
        db_session, all_category_ids,
    )
    assert plan_items_count_v2 == plan_items_count_v1 == 2
    assert plan_items_sum_v2 == plan_items_sum_v1 == Decimal("300")

    # Снимок перед вторым удалением записан на диск и содержит подтверждение
    # «Оплачено» закупки «D=2» из первого прогона.
    import json
    snap_path = tmp_path / "snap2.json"
    assert snap_path.exists()
    snap_data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert len(snap_data["purchases"]) == 2
    confirmed_entry = next(p for p in snap_data["purchases"] if p["purchase_id"] == confirmed_purchase.id)
    assert confirmed_entry["confirmations"][0]["status"] == "confirmed"
    assert confirmed_entry["confirmations"][0]["amount_confirmed"] == "200.00"


async def test_goodsservice_loader_no_payments_keep_source_budget(db_session, tmp_path):
    """Задание владельца 15.10.2026 — --no-payments/--keep-source-budget на
    обычной загрузке в НОВУЮ субсидию (run_build_v2): ни один Payment не
    создаётся (ни выписка, ни «оплачено по отметке»), budget корневой
    категории источника (12345.00) переживает копирование как есть, строк
    «План ФЭО (лист GoodsService, F1/G1…)» нет. Поправка владельца: источник
    («ФАДМ 2026_2») уже содержит плановые позиции из того же листа —
    скопированная вместе с деревом FeoPlannedItem-«двойник» ДОЛЖНА быть
    удалена (как и без флага), иначе план из текущего --goodsservice
    задвоится; сохраняется ТОЛЬКО FeoCategory.budget."""
    source = await _source_subsidy(db_session, category_budget=Decimal("12345.00"))
    source_cat = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == source.id)
    )).scalars().one()
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    db_session.add(_FPI(
        feo_category_id=source_cat.id, name="Двойник из источника",
        amount=Decimal("999999.00"), is_active=True, auto_created=True,
        notes="plan item источника — не должен попасть в копию",
    ))
    await db_session.commit()
    current_user = await _admin_user(db_session)

    bp = BankPayment(
        payment_number="777", payment_date=date(2026, 3, 1), status="ИСПОЛНЕН",
        amount=Decimal("1000.00"), payee_inn="7700000099",
        basis_doc_text="№ 091-10-2026-008 от 28.01.2026",
    )
    db_session.add(bp)
    await db_session.commit()

    rows_raw = [
        _row(purchase_no="1", order_no="1", subject="Разовая закупка", item_name="Товар А",
             contractor="ООО Ромашка-NP", plan_price="1000", plan_sum="1000", confirmed="True",
             final_price="1000", final_sum="1000", sum_to_pay_delivery="1000", plan_y="1000",
             inn="7700000099", contract_number="Д-1", contract_date="2026-01-01",
             payment_doc="777", payment_purpose="оплата", payment_date="2026-03-02",
             goods_services="Товары", contract_signed="True", delivered="True", paid="True",
             contract_kind="Разовый"),
    ]
    csv_text = _write_csv(rows_raw)
    csv_path = tmp_path / "goodsservice_no_payments.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    rows = parse_goodsservice_csv(csv_path)
    assert rows

    target_name = f"ФАДМ 2026_2-np-{_uid()}"
    subsidy, counters = await run_build_v2(
        db_session, rows=rows, source_name=source.name, target_name=target_name,
        budget=Decimal("10000"), agreement_number="091-10-2026-008",
        current_user=current_user, replace=False,
        no_payments=True, keep_source_budget=True,
    )
    await db_session.commit()

    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()
    assert purchases

    from app.models.payment import Payment
    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id.in_([p.id for p in purchases]))
    )).scalars().all()
    assert payments == [], "--no-payments не должен создавать Payment"

    categories = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy.id, FeoCategory.parent_id.is_(None))
    )).scalars().all()
    roots = [c for c in categories if c.name == "Прочее"]
    assert roots and roots[0].budget == Decimal("12345.00"), \
        "--keep-source-budget не должен обнулять budget скопированной категории"

    from app.models.feo_planned_item import FeoPlannedItem
    all_category_ids = (await db_session.execute(
        select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalars().all()
    plan_budget_rows = (await db_session.execute(
        select(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(all_category_ids),
            FeoPlannedItem.name.ilike("План ФЭО (лист GoodsService%"),
        )
    )).scalars().all()
    assert plan_budget_rows == [], "--keep-source-budget не должен создавать строки F1/G1"

    # Двойник из источника НЕ скопирован; остались только позиции, построенные
    # ИЗ листа (план-из-Y), их Σ = 1000 (plan_y одной строки CSV).
    all_items = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_(all_category_ids))
    )).scalars().all()
    assert all(it.name != "Двойник из источника" for it in all_items), \
        "--keep-source-budget не должен оставлять скопированные плановые позиции источника"
    total = sum((Decimal(str(it.amount or 0)) for it in all_items), Decimal("0"))
    assert total == Decimal("1000"), "Σ плана должна быть ровно из листа, без двойника источника"
