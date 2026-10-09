# -*- coding: utf-8 -*-
"""scripts/fadm_restore_items.py — задача 09.10.2026 (восстановление разбивки
позиций ФАДМ 2026_2 по образцу ФАДМ_2026).

validate_split/read_confirmed_pairs — чистые функции без БД, тестируются
напрямую. process_pair открывает СВОЮ сессию (app.database.async_session,
как и все остальные scripts/*.py в этом пакете) — тот же известный
ограничение, что описано в tests/conftest.py (db_session оборачивает только
get_db(), не прямой импорт async_session), поэтому интеграционный тест ниже
использует РЕАЛЬНЫЕ commit'ы на локальной dev-БД (не на проде — проверяется
через app.config, см. local-only маркер) и явно подчищает за собой все
созданные строки в finally, а не полагается на rollback тестовой транзакции.
"""
import tempfile
from decimal import Decimal

import pytest
from openpyxl import Workbook

from scripts.fadm_restore_items import read_confirmed_pairs, validate_split


# ---------------------------------------------------------------------------
# validate_split — чистая логика
# ---------------------------------------------------------------------------
def test_validate_split_ok_when_fewer_items_and_equal_sum():
    reason = validate_split(
        n_old=3, n_new=1, sum_old=Decimal("100.00"), sum_new=Decimal("100.00"),
        fpi_ids={5}, cat_ids={7},
    )
    assert reason is None


def test_validate_split_skips_when_amounts_differ():
    reason = validate_split(
        n_old=3, n_new=1, sum_old=Decimal("100.00"), sum_new=Decimal("99.00"),
        fpi_ids={5}, cat_ids={7},
    )
    assert reason is not None
    assert "суммы не совпадают" in reason


def test_validate_split_skips_when_target_not_fewer_items():
    reason = validate_split(
        n_old=2, n_new=2, sum_old=Decimal("50"), sum_new=Decimal("50"),
        fpi_ids=set(), cat_ids=set(),
    )
    assert reason is not None
    assert "не меньше" in reason


def test_validate_split_skips_when_multiple_distinct_fpi():
    reason = validate_split(
        n_old=5, n_new=2, sum_old=Decimal("300"), sum_new=Decimal("300"),
        fpi_ids={5, 6}, cat_ids={7},
    )
    assert reason is not None
    assert "несколько РАЗНЫХ" in reason


def test_validate_split_skips_when_source_has_no_items():
    reason = validate_split(
        n_old=0, n_new=0, sum_old=Decimal("0"), sum_new=Decimal("0"),
        fpi_ids=set(), cat_ids=set(),
    )
    assert reason is not None
    assert "нет позиций" in reason


# ---------------------------------------------------------------------------
# read_confirmed_pairs — чтение xlsx, без БД
# ---------------------------------------------------------------------------
def _make_pairs_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Пары"
    ws.append(["Рег.№ ФАДМ_2026", "Рег.№ ФАДМ 2026_2", "Предлагаемое действие", "Подтверждено"])
    for r in rows:
        ws.append(r)
    f = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb.save(f.name)
    return f.name


def test_read_confirmed_pairs_filters_by_action_and_confirmation():
    path = _make_pairs_xlsx([
        ["РЕЕ-1", "РЕЕ-А", "разбить на N позиций", "да"],
        ["РЕЕ-2", "РЕЕ-Б", "разбить на N позиций", ""],  # не подтверждено — пропуск
        ["РЕЕ-3", "РЕЕ-В", "состав уже совпадает", "да"],  # не то действие — пропуск
        ["РЕЕ-4", "РЕЕ-Г", "разбить на N позиций", "ДА"],  # регистр не важен
    ])
    pairs = read_confirmed_pairs(path)
    assert [(p.reg7, p.reg89) for p in pairs] == [("РЕЕ-1", "РЕЕ-А"), ("РЕЕ-4", "РЕЕ-Г")]


def test_read_confirmed_pairs_missing_column_raises():
    wb = Workbook()
    ws = wb.active
    ws.title = "Пары"
    ws.append(["Рег.№ ФАДМ_2026"])  # не хватает обязательных колонок
    f = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb.save(f.name)
    with pytest.raises(ValueError):
        read_confirmed_pairs(f.name)


# ---------------------------------------------------------------------------
# process_pair — интеграционный тест на локальной БД (НЕ на проде).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_process_pair_splits_items_and_restores_on_mismatch():
    from sqlalchemy import select, delete

    from app.database import async_session
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from scripts.fadm_restore_items import process_pair, PairPlan, BACKUP_TABLE

    created_subsidy_ids = []
    try:
        async with async_session() as db:
            src = Subsidy(name="test_fadm_restore_src", year=2026)
            dst = Subsidy(name="test_fadm_restore_dst", year=2026)
            db.add_all([src, dst])
            await db.flush()
            created_subsidy_ids = [src.id, dst.id]

            cat = FeoCategory(subsidy_id=dst.id, name="test cat", level=1)
            db.add(cat)
            await db.flush()
            fpi = FeoPlannedItem(feo_category_id=cat.id, name="test fpi", amount=Decimal("300"))
            db.add(fpi)
            await db.flush()

            p_old = Purchase(subsidy_id=src.id, status="delivered", registry_number="TEST-OLD-1")
            p_new = Purchase(subsidy_id=dst.id, status="delivered", registry_number="TEST-NEW-1")
            db.add_all([p_old, p_new])
            await db.flush()

            # 3 позиции источника, Σ = 300.00
            for i, amt in enumerate([Decimal("100.00"), Decimal("150.00"), Decimal("50.00")]):
                db.add(PurchaseItem(purchase_id=p_old.id, item_name=f"old item {i}",
                                     quantity=Decimal("1"), total_price=amt, unit_price=amt))
            # 1 агрегированная позиция получателя, та же сумма
            db.add(PurchaseItem(purchase_id=p_new.id, item_name="агрегат", quantity=Decimal("1"),
                                 total_price=Decimal("300.00"), unit_price=Decimal("300.00"),
                                 feo_planned_item_id=fpi.id, feo_category_id=cat.id))
            await db.commit()

        pair = PairPlan(reg7="TEST-OLD-1", reg89="TEST-NEW-1")

        # dry-run: откат — позиции получателя должны остаться как были (1 шт)
        outcome_dry = await process_pair(pair, source_subsidy_id=src.id, target_subsidy_id=dst.id, apply=False)
        assert outcome_dry.status == "ok"
        assert outcome_dry.amount_before == outcome_dry.amount_after
        async with async_session() as db:
            items_after_dry = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == p_new.id)
            )).scalars().all()
        assert len(items_after_dry) == 1, "dry-run обязан откатиться — агрегированная позиция на месте"

        # apply: реально разбивает на 3 позиции, сумма/feo_planned_item_id сохранены
        outcome_apply = await process_pair(pair, source_subsidy_id=src.id, target_subsidy_id=dst.id, apply=True)
        assert outcome_apply.status == "ok"
        assert outcome_apply.amount_before == outcome_apply.amount_after
        assert outcome_apply.plan_before == outcome_apply.plan_after

        async with async_session() as db:
            items_after_apply = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == p_new.id)
            )).scalars().all()
            assert len(items_after_apply) == 3
            assert all(it.feo_planned_item_id == fpi.id for it in items_after_apply)
            assert all(it.feo_category_id == cat.id for it in items_after_apply)
            total = sum((it.total_price for it in items_after_apply), Decimal("0"))
            assert total == Decimal("300.00")

            backup_rows = (await db.execute(
                select(PurchaseItem.id)  # noqa: unused — only to confirm backup table exists below
            )).all()
            assert backup_rows is not None
            from sqlalchemy import text
            bk = (await db.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE restore_reg89 = 'TEST-NEW-1'"))).scalar()
            assert bk == 1, "резервная копия агрегированной позиции должна быть сохранена"

        # Несовпадение сумм — пара пропускается, ничего не меняется
        async with async_session() as db:
            p_new2 = Purchase(subsidy_id=dst.id, status="delivered", registry_number="TEST-NEW-2")
            db.add(p_new2)
            await db.flush()
            db.add(PurchaseItem(purchase_id=p_new2.id, item_name="агрегат-2", quantity=Decimal("1"),
                                 total_price=Decimal("999.00"), unit_price=Decimal("999.00")))
            p_old2 = Purchase(subsidy_id=src.id, status="delivered", registry_number="TEST-OLD-2")
            db.add(p_old2)
            await db.flush()
            db.add(PurchaseItem(purchase_id=p_old2.id, item_name="old-2a", quantity=Decimal("1"),
                                 total_price=Decimal("1.00"), unit_price=Decimal("1.00")))
            db.add(PurchaseItem(purchase_id=p_old2.id, item_name="old-2b", quantity=Decimal("1"),
                                 total_price=Decimal("1.00"), unit_price=Decimal("1.00")))
            await db.commit()

        outcome_mismatch = await process_pair(
            PairPlan(reg7="TEST-OLD-2", reg89="TEST-NEW-2"),
            source_subsidy_id=src.id, target_subsidy_id=dst.id, apply=True,
        )
        assert outcome_mismatch.status == "skipped"
        assert "суммы не совпадают" in outcome_mismatch.reason
    finally:
        async with async_session() as db:
            await db.execute(delete(PurchaseItem).where(
                PurchaseItem.purchase_id.in_(
                    select(Purchase.id).where(Purchase.subsidy_id.in_(created_subsidy_ids))
                )
            ))
            await db.execute(delete(Purchase).where(Purchase.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id.in_(
                    select(FeoCategory.id).where(FeoCategory.subsidy_id.in_(created_subsidy_ids))
                )
            ))
            await db.execute(delete(FeoCategory).where(FeoCategory.subsidy_id.in_(created_subsidy_ids)))
            await db.execute(delete(Subsidy).where(Subsidy.id.in_(created_subsidy_ids)))
            from sqlalchemy import text
            await db.execute(text(f"DELETE FROM {BACKUP_TABLE} WHERE restore_reg89 LIKE 'TEST-NEW-%'"))
            await db.commit()
