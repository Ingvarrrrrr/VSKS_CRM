"""test_acceptance_docs.py — unit-тесты app/services/acceptance_docs.py
(ПРАВИЛО №6, группа D4, 2026-09-07): JSONB acceptance_docs — источник истины
закрывающих документов закупки; скаляры acceptance_doc_name/date/number/
amount — производный КЭШ (первый документ), пишется ТОЛЬКО sync_scalars
(вызывается изнутри add_doc/remove_doc/replace_docs) — нужен report-builder'у
(field_registry.py/pivot_engine.py). Остальные читатели используют
derived_scalars()/total_amount() напрямую (единый читатель), не кэш-колонки.
"""
from decimal import Decimal

import pytest

from app.services.acceptance_docs import (
    add_doc, remove_doc, replace_docs, dedup, derived_scalars, total_amount, sync_scalars,
)


def test_dedup_removes_exact_duplicate_by_type_number_amount():
    docs = [
        {"type": "Чек", "number": "123", "amount": 100.0},
        {"type": "Чек", "number": "123", "amount": 100.0},
    ]
    out = dedup(docs)
    assert len(out) == 1


def test_dedup_keeps_docs_with_empty_number():
    """Легаси-записи без number не дедуплицируются вслепую (см. backfill 26-ooo)."""
    docs = [{"type": "", "number": "", "amount": 0}, {"type": "", "number": "", "amount": 0}]
    assert len(dedup(docs)) == 2


def test_dedup_merges_file_id_from_duplicate_into_kept():
    docs = [
        {"type": "Чек", "number": "1", "amount": 50.0, "file_id": None},
        {"type": "Чек", "number": "1", "amount": 50.0, "file_id": 99},
    ]
    out = dedup(docs)
    assert len(out) == 1
    assert out[0]["file_id"] == 99


@pytest.mark.asyncio
async def test_add_doc_appends_and_flags_modified(db_session, make_purchase):
    p = await make_purchase(status="delivered")
    changed = add_doc(p, {"type": "Акт", "number": "A-1", "amount": 500.0})
    assert changed is True
    assert len(p.acceptance_docs) == 1
    await db_session.commit()
    await db_session.refresh(p)
    assert p.acceptance_docs[0]["number"] == "A-1"


@pytest.mark.asyncio
async def test_add_doc_syncs_scalar_cache(db_session, make_purchase):
    """Координатор (2026-09-07): скаляр-кэш обязан обновиться сразу внутри
    add_doc — равен derived_scalars(p) без отдельного вызова sync_scalars."""
    p = await make_purchase(status="delivered")
    add_doc(p, {"name": "Акт", "number": "A-1", "date": "2026-02-01", "amount": 500.0})
    d = derived_scalars(p)
    assert p.acceptance_doc_name == d["name"] == "Акт"
    assert p.acceptance_doc_number == d["number"] == "A-1"
    assert p.acceptance_doc_amount == d["amount"] == Decimal("500.0")
    await db_session.commit()
    await db_session.refresh(p)
    assert p.acceptance_doc_name == "Акт"
    assert p.acceptance_doc_amount == Decimal("500.0")


@pytest.mark.asyncio
async def test_remove_doc_recomputes_scalar_cache(db_session, make_purchase):
    """После удаления ПЕРВОГО документа кэш должен пересчитаться на новый
    docs[0], а не остаться со старым значением."""
    p = await make_purchase(status="delivered", acceptance_docs=[
        {"name": "Чек 1", "number": "1", "amount": 10.0, "receipt_id": 1},
        {"name": "Чек 2", "number": "2", "amount": 20.0, "receipt_id": 2},
    ])
    sync_scalars(p)
    assert p.acceptance_doc_number == "1"

    remove_doc(p, lambda d: d.get("receipt_id") == 1)
    d = derived_scalars(p)
    assert p.acceptance_doc_number == d["number"] == "2"
    assert p.acceptance_doc_amount == d["amount"] == Decimal("20.0")
    await db_session.commit()
    await db_session.refresh(p)
    assert p.acceptance_doc_number == "2"


@pytest.mark.asyncio
async def test_add_doc_duplicate_not_added(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_docs=[{"type": "Чек", "number": "5", "amount": 10.0}])
    changed = add_doc(p, {"type": "Чек", "number": "5", "amount": 10.0})
    assert changed is False
    assert len(p.acceptance_docs) == 1


@pytest.mark.asyncio
async def test_remove_doc_by_predicate(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_docs=[
        {"type": "Чек", "number": "1", "amount": 10.0, "receipt_id": 7},
        {"type": "Чек", "number": "2", "amount": 20.0, "receipt_id": 8},
    ])
    removed = remove_doc(p, lambda d: d.get("receipt_id") == 7)
    assert len(removed) == 1
    assert len(p.acceptance_docs) == 1
    assert p.acceptance_docs[0]["receipt_id"] == 8


@pytest.mark.asyncio
async def test_remove_doc_no_match_leaves_untouched(db_session, make_purchase):
    p = await make_purchase(status="delivered", acceptance_docs=[{"type": "Чек", "number": "1", "amount": 10.0}])
    removed = remove_doc(p, lambda d: d.get("receipt_id") == 999)
    assert removed == []
    assert len(p.acceptance_docs) == 1


@pytest.mark.asyncio
async def test_replace_docs_dedups_and_sets(db_session, make_purchase):
    p = await make_purchase(status="delivered")
    replace_docs(p, [
        {"type": "Акт", "number": "1", "amount": 100.0},
        {"type": "Акт", "number": "1", "amount": 100.0},
    ])
    assert len(p.acceptance_docs) == 1


def test_derived_scalars_empty_docs_falls_back_to_legacy_scalars():
    class P:
        acceptance_docs = []
        acceptance_doc_name = "УПД"
        acceptance_doc_number = "77"
        acceptance_doc_date = None
        acceptance_doc_amount = Decimal("300")
    d = derived_scalars(P())
    assert d == {"name": "УПД", "number": "77", "date": None, "amount": Decimal("300")}


def test_derived_scalars_one_doc():
    class P:
        acceptance_docs = [{"name": "Акт", "number": "A-1", "date": "2026-02-28", "amount": 555}]
    d = derived_scalars(P())
    assert d["name"] == "Акт"
    assert d["number"] == "A-1"
    assert d["amount"] == Decimal("555")
    from datetime import date
    assert d["date"] == date(2026, 2, 28)


def test_derived_scalars_multiple_docs_uses_first():
    class P:
        acceptance_docs = [
            {"name": "Чек 1", "number": "1", "amount": 10},
            {"name": "Чек 2", "number": "2", "amount": 20},
        ]
    d = derived_scalars(P())
    assert d["name"] == "Чек 1"
    assert d["number"] == "1"


def test_total_amount_sums_all_docs():
    class P:
        acceptance_docs = [{"amount": 10}, {"amount": 20.5}]
        acceptance_doc_amount = None
    assert total_amount(P()) == Decimal("30.5")


def test_total_amount_empty_docs_falls_back_to_legacy_scalar():
    class P:
        acceptance_docs = []
        acceptance_doc_amount = Decimal("42")
    assert total_amount(P()) == Decimal("42")


@pytest.mark.asyncio
async def test_purchase_put_with_acceptance_docs_syncs_scalar_cache(
    client, db_session, make_purchase, auth_headers,
):
    """PUT с acceptance_docs игнорирует explicit legacy-скаляр в payload
    (PATCHABLE-подобная защита в PUT — см. purchases.py) и синхронизирует
    скаляр-кэш ИЗ JSONB через replace_docs()->sync_scalars() (ПРАВИЛО №6,
    правка координатора 2026-09-07: кэш — не «оставить пустым», а «всегда
    равен первому документу JSONB»)."""
    p = await make_purchase(status="wishes", planned_total_price=Decimal("100"))
    resp = await client.put(
        f"/api/purchases/{p.id}",
        json={
            "acceptance_docs": [{"name": "Акт", "number": "42", "date": "2026-01-15", "amount": 250.0}],
            "acceptance_doc_name": "ДОЛЖНО ИГНОРИРОВАТЬСЯ (explicit-скаляр из payload)",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["acceptance_doc_name"] == "Акт"
    assert body["acceptance_doc_number"] == "42"
    assert float(body["acceptance_doc_amount"]) == 250.0

    await db_session.refresh(p)
    # Кэш реально записан в БД — равен первому JSONB-документу, НЕ значению,
    # присланному напрямую в payload (то было проигнорировано).
    assert p.acceptance_doc_name == "Акт"
    assert p.acceptance_doc_number == "42"
    assert p.acceptance_doc_amount == Decimal("250.0")
