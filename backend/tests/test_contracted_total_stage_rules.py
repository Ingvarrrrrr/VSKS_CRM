"""Прод-находка 09.10.2026 (ФАДМ 2026_2, субсидия id=89): карточка «Заключено
договоров» (app.services.stage_cumulative.contracted_total_by_subsidy) и
список договоров по клику (app.services.dashboard_contracts_drill.
contracts_drill_rows) обязаны давать ОДНО число (ПРАВИЛО №6).

Решение владельца (09.10.2026, прод-пример «АДС-АВТО», договор «1»,
framework_with_amount, закупка №1253): действующий (status='active')
рамочный-с-суммой договор засчитывается в «Заключено договоров» САМ ПО СЕБЕ,
независимо от статуса закупки-шапки (parent_purchase_id IS NULL) — «он
увеличивает законтрактованное, но не запланированное». Гейт по статусу шапки
(заводился и отменён тем же днём) в коде отсутствует; граница — только
Contract.status == 'active' (как и раньше).

Отдельный дефект — Σ списка (dashboard_contracts_drill) была МЕНЬШЕ карточки
(stage_cumulative.contracted_rows_by_category) на 35 611,80 ₽: список считал
заказы framework_with_amount/framework_cumulative ТОЛЬКО по
FRAMEWORK_COMMITTED_STATUSES (ordered/delivered/paid), а карточка уже
включала reserved_child_predicate() (заказ рамочного в статусе 'contracted' —
договор на партию уже заключён, сам заказ как отдельная закупка ещё не
оформлен). Исправлено: оба места теперь используют ОДНО и то же выражение
(FRAMEWORK_COMMITTED_STATUSES ∪ reserved_child_predicate()) — ЭТО остаётся в
силе и покрыто тестами ниже."""
import uuid
from decimal import Decimal

import pytest

from app.services.dashboard_contracts_drill import contracts_drill_rows
from app.services.stage_cumulative import contracted_total_by_subsidy


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"StageRules-{uuid.uuid4().hex[:8]}", year=2026, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_purchase(db_session, subsidy_id, *, status, **kwargs):
    from app.models.purchase import Purchase
    p = Purchase(subsidy_id=subsidy_id, status=status, item_name=f"P-{uuid.uuid4().hex[:6]}", **kwargs)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_framework_with_amount_counts_limit_even_with_head_in_wishes(db_session, test_org):
    """(а1) Шапка рамочного-с-суммой договора в 'wishes' (заказов не было,
    как «АДС-АВТО») — действующий договор ВСЁ РАВНО засчитан лимитом и в
    карточке, и в списке (владелец, 09.10.2026: «увеличивает
    законтрактованное, но не запланированное»)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("600000"),
    )
    db_session.add(fwa)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="wishes",
        contract_id=fwa.id, purchase_contract_type="framework_with_amount",
    )

    card = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert card[subsidy.id]["amount"] == pytest.approx(600_000.0)

    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])
    assert len(rows) == 1
    assert rows[0]["contract_amount"] == pytest.approx(600_000.0)
    assert rows[0]["contract_amount"] == pytest.approx(card[subsidy.id]["amount"])


@pytest.mark.asyncio
async def test_framework_with_amount_inactive_contract_not_counted(db_session, test_org):
    """(а2) Граница по-прежнему Contract.status == 'active' (не статус
    шапки): недействующий (status != 'active') рамочный-с-суммой договор не
    засчитан, даже с заданным max_amount — отличает «статус шапки больше не
    гейт» от «статус самого договора — всё ещё гейт»."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="draft", max_amount=Decimal("600000"),
    )
    db_session.add(fwa)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_id=fwa.id, purchase_contract_type="framework_with_amount",
    )

    card = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert card.get(subsidy.id, {"amount": 0.0})["amount"] == pytest.approx(0.0)

    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])
    assert rows == []


@pytest.mark.asyncio
async def test_single_purchase_wishes_is_not_contracted(db_session, test_org):
    """(б) Разовый договор, единственная закупка в 'wishes' — не засчитан
    (прод-пример: закупка №1245 №3209, договор 1242, 6 510). Это правило уже
    действовало (_contracted_purchase_exists), тест закрепляет его явно,
    вместе с остальными сценариями."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    single = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("6510"),
    )
    db_session.add(single)
    await db_session.flush()
    await _make_purchase(db_session, subsidy.id, status="wishes", contract_id=single.id)

    card = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    assert card.get(subsidy.id, {"amount": 0.0})["amount"] == pytest.approx(0.0)

    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])
    assert rows == []


@pytest.mark.asyncio
async def test_card_equals_drill_sum_on_mixed_data_with_reserved_and_subsidy_mismatch(db_session, test_org):
    """(в) Карточка == Σ строк списка на смешанных данных:
      - разовый договор, committed-закупка;
      - framework_with_amount, шапка 'contracted', один ребёнок 'ordered'
        и один ребёнок 'contracted' (parent_purchase_id задан — «зарезервирован»,
        reserved_child_predicate) — ровно причина расхождения 35 611,80 на
        проде: список раньше не считал второго ребёнка;
      - framework_cumulative с ребёнком-заказом в статусе 'contracted'
        (parent_purchase_id задан) — та же «зарезервированная» ветка;
      - committed-закупка без договора вовсе;
      - договор (single) с subsidy_id=NULL, чья закупка принадлежит ЭТОЙ
        субсидии, но НЕ committed (status='work_in_progress' — прод-пример
        «Бэст прайс» №975/договор 122) — не должна давать расхождение между
        карточкой и списком (ни одна из двух формул её не видит, т.к. не
        committed; тест закрепляет, что сама по себе такая запись в данных не
        ломает инвариант card == Σ rows)."""
    from app.models.contract import Contract

    subsidy = await _make_subsidy(db_session)
    other_subsidy = await _make_subsidy(db_session)

    # 1) Разовый — committed.
    single = Contract(
        number=f"S-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("100000"),
    )
    db_session.add(single)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_price=Decimal("100000"), contract_id=single.id,
    )

    # 2) framework_with_amount — шапка contracted, ребёнок ordered + ребёнок
    #    "зарезервирован" (contracted, есть parent_purchase_id).
    fwa = Contract(
        number=f"FWA-{uuid.uuid4().hex[:6]}", contract_type="framework_with_amount",
        subsidy_id=subsidy.id, status="active", max_amount=Decimal("584032"),
    )
    db_session.add(fwa)
    await db_session.flush()
    head = await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_id=fwa.id, purchase_contract_type="framework_with_amount",
    )
    await _make_purchase(
        db_session, subsidy.id, status="ordered", contract_price=Decimal("300000"),
        contract_id=fwa.id, parent_purchase_id=head.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted", contract_price=Decimal("38903"),
        contract_id=fwa.id, parent_purchase_id=head.id,
    )

    # 3) framework_cumulative — ребёнок delivered + ребёнок "зарезервирован".
    cumulative = Contract(
        number=f"FC-{uuid.uuid4().hex[:6]}", contract_type="framework_cumulative",
        subsidy_id=subsidy.id, status="active",
    )
    db_session.add(cumulative)
    await db_session.flush()
    cum_head = await _make_purchase(
        db_session, subsidy.id, status="plan_schedule",
        contract_id=cumulative.id, purchase_contract_type="framework_cumulative",
    )
    await _make_purchase(
        db_session, subsidy.id, status="delivered",
        contract_price=Decimal("50000"), contract_id=cumulative.id, parent_purchase_id=cum_head.id,
    )
    await _make_purchase(
        db_session, subsidy.id, status="contracted",
        contract_price=Decimal("12000"), contract_id=cumulative.id, parent_purchase_id=cum_head.id,
    )

    # 4) committed-закупка без договора вовсе.
    await _make_purchase(db_session, subsidy.id, status="paid", payment_amount=Decimal("777"))

    # 5) Договор с subsidy_id=NULL (прод-аномалия «Бэст прайс»/122), закупка —
    #    этой субсидии, НЕ committed.
    mismatched = Contract(
        number=f"MM-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=None, status="active", max_amount=Decimal("3386.50"),
    )
    db_session.add(mismatched)
    await db_session.flush()
    await _make_purchase(
        db_session, subsidy.id, status="work_in_progress", contract_id=mismatched.id,
    )

    # Другая субсидия — контрольная, не должна утечь в сумму первой.
    noise_single = Contract(
        number=f"N-{uuid.uuid4().hex[:6]}", contract_type="single",
        subsidy_id=other_subsidy.id, status="active", max_amount=Decimal("9999"),
    )
    db_session.add(noise_single)
    await db_session.flush()
    await _make_purchase(
        db_session, other_subsidy.id, status="contracted",
        contract_price=Decimal("9999"), contract_id=noise_single.id,
    )

    card = await contracted_total_by_subsidy(db_session, subsidy_ids=[subsidy.id])
    rows = await contracts_drill_rows(db_session, subsidy_ids=[subsidy.id])

    total_rows = sum(r["contract_amount"] for r in rows)
    assert total_rows == pytest.approx(card[subsidy.id]["amount"])
    # Контроль по существу — не просто совпадение нулей.
    assert card[subsidy.id]["amount"] > 100_000
