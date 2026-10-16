# -*- coding: utf-8 -*-
"""app/services/purchase_transfer/ — копирование/слияние закупок между
субсидиями + роутер app/routers/purchase_transfer.py.

match.classify — чистая функция (без БД). Остальное трогает db_session (та
же изолирующая SAVEPOINT-транзакция, что и весь остальной conftest.py — см.
его докстринг, ничего не переживает тест)."""
from decimal import Decimal

import pytest

from app.services.purchase_transfer.match import PurchaseKey, classify


def _key(pid, inn="", supplier="", amount="0"):
    return PurchaseKey(purchase_id=pid, inn=inn, supplier_key=supplier, amount=Decimal(amount))


# ---------------------------------------------------------------------------
# classify — чистая логика (без БД)
# ---------------------------------------------------------------------------
def test_classify_same_by_inn_and_amount():
    source = [_key(1, inn="7705513090", amount="1000.00")]
    target = [_key(101, inn="7705513090", amount="1000.00")]
    result = classify(source, target)
    assert result[1].state == "same"
    assert result[1].match_purchase_id == 101


def test_classify_advance_matches_by_employee_not_inn():
    source = [_key(1, supplier="employee:42", amount="500.00")]
    target = [
        _key(101, supplier="employee:43", amount="500.00"),  # другой сотрудник, та же сумма
        _key(102, supplier="employee:42", amount="500.00"),
    ]
    result = classify(source, target)
    assert result[1].state == "same"
    assert result[1].match_purchase_id == 102


def test_classify_amount_only_when_key_differs():
    source = [_key(1, inn="7705513090", amount="1000.00")]
    target = [_key(101, inn="9999999999", amount="1000.00")]
    result = classify(source, target)
    assert result[1].state == "amount_only"
    assert result[1].match_purchase_id == 101


def test_classify_without_amount_never_pairs():
    """Приёмка 16.10: закупки без суммы сопоставлялись друг с другом как
    «только сумма» — без суммы пару подобрать не по чему, только вручную."""
    source = [_key(1, inn="7705513090", amount="0"), _key(2, amount="0")]
    target = [_key(101, inn="7705513090", amount="0"), _key(102, amount="0")]
    result = classify(source, target)
    assert result[1].state == "none" and result[2].state == "none"


def test_classify_none_when_nothing_matches():
    source = [_key(1, inn="7705513090", amount="1000.00")]
    target = [_key(101, inn="9999999999", amount="500.00")]
    result = classify(source, target)
    assert result[1].state == "none"
    assert result[1].match_purchase_id is None


def test_classify_same_amount_candidates_ordered_by_id():
    # Две исходные с одинаковым ИНН+суммой, две целевые с тем же ключом —
    # пары по порядку id, одна целевая не используется дважды.
    source = [
        _key(1, inn="7705513090", amount="1000.00"),
        _key(2, inn="7705513090", amount="1000.00"),
    ]
    target = [
        _key(201, inn="7705513090", amount="1000.00"),
        _key(202, inn="7705513090", amount="1000.00"),
    ]
    result = classify(source, target)
    assert result[1].match_purchase_id == 201
    assert result[2].match_purchase_id == 202


# ---------------------------------------------------------------------------
# copy_to_subsidy / merge_into — реальная БД (db_session)
# ---------------------------------------------------------------------------
@pytest.fixture
def make_subsidy(db_session, test_org):
    from app.models.subsidy import Subsidy

    async def _make(name="Test subsidy", status="approved"):
        s = Subsidy(name=name, year=2026, org_id=test_org.id, status=status)
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)
        return s

    return _make


@pytest.fixture
def make_contractor(db_session):
    import uuid
    from app.models.contractor import Contractor

    async def _make(name="ООО Ромашка", inn=None):
        # ИНН должен быть уникален в реальной dev-БД (ix_contractors_inn_unique
        # на всей таблице) — тест не изолирован от уже существующих контрагентов,
        # поэтому дефолт — случайный 10-значный ИНН, не захардкоженный.
        if inn is None:
            inn = str(uuid.uuid4().int)[:10]
        c = Contractor(name=name, inn=inn)
        db_session.add(c)
        await db_session.commit()
        await db_session.refresh(c)
        return c

    return _make


@pytest.fixture
def make_feo_category(db_session):
    from app.models.feo_category import FeoCategory

    async def _make(subsidy_id, name="Прочее", parent_id=None, level=1):
        cat = FeoCategory(name=name, subsidy_id=subsidy_id, parent_id=parent_id, level=level,
                           sort_order=1, is_active=True)
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)
        return cat

    return _make


@pytest.mark.asyncio
async def test_copy_creates_linked_copy_and_events(db_session, make_subsidy, make_contractor, make_feo_category, make_purchase, make_user):
    from sqlalchemy import select
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseEvent
    from app.services.purchase_transfer.copy_one import copy_to_subsidy

    source_sid = await make_subsidy(name="Источник")
    target_sid = await make_subsidy(name="Цель")
    contractor = await make_contractor()
    src_cat = await make_feo_category(source_sid.id, name="Канцтовары")
    await make_feo_category(target_sid.id, name="Канцтовары")  # совпадает по имени
    user = await make_user(role="account_owner")

    old = await make_purchase(
        status="contracted", subsidy_id=source_sid.id, contractor_id=contractor.id,
        feo_category_id=src_cat.id, contract_price=Decimal("1000.00"),
    )

    outcomes = await copy_to_subsidy(db_session, [old.id], target_sid.id, user)
    await db_session.commit()

    assert len(outcomes) == 1
    new_id = outcomes[0].new_id

    new_p = await db_session.get(Purchase, new_id)
    assert new_p.subsidy_id == target_sid.id
    assert new_p.copied_from_purchase_id == old.id
    assert new_p.feo_category_id is not None  # нашлась по имени в целевой

    # Оригинал не изменился.
    old_reloaded = await db_session.get(Purchase, old.id)
    assert old_reloaded.subsidy_id == source_sid.id
    assert old_reloaded.feo_category_id == src_cat.id
    assert old_reloaded.copied_from_purchase_id is None

    old_events = (await db_session.execute(
        select(PurchaseEvent).where(PurchaseEvent.purchase_id == old.id, PurchaseEvent.event_type == "copied_to")
    )).scalars().all()
    assert len(old_events) == 1
    assert old_events[0].data["target_purchase_id"] == new_id

    new_events = (await db_session.execute(
        select(PurchaseEvent).where(PurchaseEvent.purchase_id == new_id, PurchaseEvent.event_type == "copied_from")
    )).scalars().all()
    assert len(new_events) == 1
    assert new_events[0].data["source_purchase_id"] == old.id


@pytest.mark.asyncio
async def test_copy_category_not_found_falls_back_to_unallocated(db_session, make_subsidy, make_contractor, make_feo_category, make_purchase, make_user):
    from app.models.purchase import Purchase
    from app.services.purchase_transfer.copy_one import copy_to_subsidy

    source_sid = await make_subsidy(name="Источник2")
    target_sid = await make_subsidy(name="Цель2")
    contractor = await make_contractor()
    src_cat = await make_feo_category(source_sid.id, name="Совсем другое имя категории")
    user = await make_user(role="account_owner")

    old = await make_purchase(
        status="contracted", subsidy_id=source_sid.id, contractor_id=contractor.id,
        feo_category_id=src_cat.id, contract_price=Decimal("777.00"),
    )

    outcomes = await copy_to_subsidy(db_session, [old.id], target_sid.id, user)
    await db_session.commit()
    new_p = await db_session.get(Purchase, outcomes[0].new_id)
    assert new_p.feo_category_id is not None

    from app.models.feo_category import FeoCategory
    na = await db_session.get(FeoCategory, new_p.feo_category_id)
    assert na.name.lower() in ("не определена", "нераспределённое", "нераспределенное")
    assert na.subsidy_id == target_sid.id


@pytest.mark.asyncio
async def test_merge_does_not_overwrite_filled_fields(db_session, make_subsidy, make_purchase, make_user):
    from app.services.purchase_transfer.merge_into import merge_into

    source_sid = await make_subsidy(name="Источник3")
    target_sid = await make_subsidy(name="Цель3")
    emp_a = await make_user(role="employee")
    emp_b = await make_user(role="employee")
    actor = await make_user(role="account_owner")

    source = await make_purchase(status="contracted", subsidy_id=source_sid.id, assigned_user_id=emp_a.id,
                                  service_note_by=None)
    target = await make_purchase(status="contracted", subsidy_id=target_sid.id, assigned_user_id=emp_b.id,
                                  service_note_by=None)

    result = await merge_into(db_session, source, target, actor)
    await db_session.commit()

    await db_session.refresh(target)
    # assigned_user_id у target был заполнен (emp_b) — merge не затирает его исполнителем source.
    assert target.assigned_user_id == emp_b.id
    # service_note_by был пуст у обоих — остаётся пустым (а не падает).
    assert result.target_id == target.id

    await db_session.refresh(source)
    assert source.subsidy_id == source_sid.id  # source не останавливается/не трогается


@pytest.mark.asyncio
async def test_apply_requires_permission(client, auth_headers, db_session, make_subsidy):
    source_sid = await make_subsidy(name="ИсточникPerm")
    target_sid = await make_subsidy(name="ЦельPerm")

    resp = await client.post(
        "/api/purchase-transfer/preview",
        json={"source_subsidy_id": source_sid.id, "target_subsidy_id": target_sid.id},
        headers=auth_headers,
    )
    # Обычный employee без purchase.copy_to_subsidy (и без видимости субсидий
    # другой орги по умолчанию) не должен получить предпросмотр.
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Поиск — копия находится по номеру оригинала и обратно
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_finds_copy_by_original_registry_number(db_session, make_subsidy, make_purchase):
    from sqlalchemy import select
    from app.models.purchase import Purchase
    from app.services.purchase_search import build_purchase_search_clause

    source_sid = await make_subsidy(name="ИсточникSearch")
    target_sid = await make_subsidy(name="ЦельSearch")
    old = await make_purchase(status="contracted", subsidy_id=source_sid.id)
    new = await make_purchase(status="contracted", subsidy_id=target_sid.id, copied_from_purchase_id=old.id)
    await db_session.commit()
    await db_session.refresh(old)

    rows = (await db_session.execute(
        select(Purchase.id).where(build_purchase_search_clause(old.registry_number))
    )).scalars().all()
    assert old.id in rows
    assert new.id in rows
