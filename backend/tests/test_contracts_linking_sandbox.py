"""services/contracts_linking.py::ensure_contract_linked — лукап договора
глобальный (рамочные договоры общие на несколько субсидий, П15), изолируется
ТОЛЬКО по признаку «песочница для экспериментов» (план breezy-mixing-
lovelace.md, Часть Б, правка после регрессии: сужение до
Contract.subsidy_id == p.subsidy_id ломало реальный межсубсидийный кейс).

Тесты через db_session (реальная БД, транзакция с откатом, см. conftest.py).
"""
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.services.contracts_linking import ensure_contract_linked
from app.services.subsidy_copy import create_sandbox_copy


async def _make_subsidy(db_session, **kw) -> Subsidy:
    subsidy = Subsidy(name=f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026, **kw)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def test_real_purchase_links_to_existing_contract_of_another_subsidy(db_session):
    """П15: рамочный договор (пример владельца — ОФИСМАГ «51802 ОП/КОР»)
    общий на несколько субсидий — настоящая закупка субсидии A обязана
    находить и связываться с уже существующим договором субсидии B
    (глобальный лукап, не сужен по subsidy_id). Номер — с уникальным
    суффиксом (не буквальный «51802 ОП/КОР» из примера владельца), иначе
    в общей БД проекта зависшие прогоны этого же теста накопили бы дубли
    и сломали .scalar_one_or_none() (MultipleResultsFound)."""
    num = f"51802 ОП/КОР-{uuid.uuid4().hex[:8]}"
    subsidy_a = await _make_subsidy(db_session)
    subsidy_b = await _make_subsidy(db_session)

    contract_b = Contract(
        number=num, contract_type="framework_cumulative",
        subsidy_id=subsidy_b.id, subject="Рамочный договор ОФИСМАГ",
    )
    db_session.add(contract_b)
    await db_session.commit()
    await db_session.refresh(contract_b)

    purchase_a = Purchase(
        subsidy_id=subsidy_a.id, item_name="Закупка по рамочному договору другой субсидии",
        contract_number=num, status="work_in_progress",
    )
    db_session.add(purchase_a)
    await db_session.commit()
    await db_session.refresh(purchase_a)

    await ensure_contract_linked(purchase_a, db_session)
    await db_session.commit()

    assert purchase_a.contract_id == contract_b.id


async def test_sandbox_purchase_does_not_link_to_original_contract_links_to_copy(db_session):
    """Закупка песочницы-копии A не связывается с договором оригинала A —
    связывается с КОПИЕЙ договора (та же модель copy_purchases.py уже создала
    при копировании субсидии)."""
    source = await _make_subsidy(db_session)
    num = f"Д-ОРИГИНАЛ-{uuid.uuid4().hex[:8]}"

    contract = Contract(
        number=num, contract_type="single", subsidy_id=source.id, subject="Договор оригинала",
    )
    db_session.add(contract)
    await db_session.flush()
    purchase = Purchase(
        subsidy_id=source.id, item_name="Закупка оригинала", status="paid",
        contract_id=contract.id, contract_number=num,
        contract_price=Decimal("100.00"),
    )
    db_session.add(purchase)
    await db_session.commit()

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    copy_contract = (await db_session.execute(
        select(Contract).where(Contract.subsidy_id == copy.id)
    )).scalars().first()
    assert copy_contract is not None
    assert copy_contract.id != contract.id

    # Новая закупка внутри ПЕСОЧНИЦЫ с тем же номером договора, что у оригинала —
    # должна найти/остаться на договоре КОПИИ, а не оригинала.
    new_sandbox_purchase = Purchase(
        subsidy_id=copy.id, item_name="Вторая закупка в песочнице по тому же договору",
        contract_number=num, status="work_in_progress",
    )
    db_session.add(new_sandbox_purchase)
    await db_session.commit()
    await db_session.refresh(new_sandbox_purchase)

    await ensure_contract_linked(new_sandbox_purchase, db_session)
    await db_session.commit()

    assert new_sandbox_purchase.contract_id == copy_contract.id
    assert new_sandbox_purchase.contract_id != contract.id


async def test_real_purchase_does_not_link_to_contract_owned_by_sandbox(db_session):
    """Обратная сторона: настоящая (не-песочная) закупка не должна находить
    договор, который принадлежит чьей-то копии-песочнице, даже при совпадении
    номера/контрагента — иначе реальная закупка приклеилась бы к экспериментальным
    данным."""
    source = await _make_subsidy(db_session)
    num2 = f"Д-ОРИГИНАЛ-{uuid.uuid4().hex[:8]}"
    contract = Contract(
        number=num2, contract_type="single", subsidy_id=source.id, subject="Договор оригинала 2",
    )
    db_session.add(contract)
    await db_session.flush()
    purchase = Purchase(
        subsidy_id=source.id, item_name="Закупка оригинала 2", status="paid",
        contract_id=contract.id, contract_number=num2,
    )
    db_session.add(purchase)
    await db_session.commit()

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()
    copy_contract = (await db_session.execute(
        select(Contract).where(Contract.subsidy_id == copy.id)
    )).scalars().first()
    assert copy_contract is not None

    # Третья, настоящая субсидия — новая закупка с ТЕМ ЖЕ номером договора,
    # что у договора копии (чисто гипотетическое совпадение номеров) — не
    # должна зацепиться за договор, принадлежащий песочнице copy.
    other_real_subsidy = await _make_subsidy(db_session)
    other_purchase = Purchase(
        subsidy_id=other_real_subsidy.id, item_name="Другая настоящая закупка",
        contract_number=copy_contract.number, status="work_in_progress",
    )
    db_session.add(other_purchase)
    await db_session.commit()
    await db_session.refresh(other_purchase)

    await ensure_contract_linked(other_purchase, db_session)
    await db_session.commit()

    # Номер совпадает и у оригинала, и у его копии (copy_purchases.py клонирует
    # номер как есть) — настоящая закупка обязана найти НАСТОЯЩИЙ (оригинала),
    # не договор копии, хотя оба кандидата с одинаковым номером.
    assert other_purchase.contract_id != copy_contract.id
    assert other_purchase.contract_id == contract.id
