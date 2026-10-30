# -*- coding: utf-8 -*-
"""POST /api/purchases/{pid}/split — наследование wish_id/ФЭО-режима заявки
при разбиении многокатегорийной закупки (задача 29.10.2026, прод, заявка 226).

Баг (прод): заявку разбили на части по колонкам канбана — части получили
wish_id=NULL (GET /wishes/{id}/purchases-board открывал пустой канбан),
status='planned' (легаси, вне STATUS_ORDER) и feo_per_item=False несмотря на
то, что позиции части остались РАЗНЫХ категорий ФЭО (унаследованных от разных
плановых позиций заявки) — комбинация давала ложный баннер «РАСХОЖДЕНИЕ
КАТЕГОРИИ ФЭО» (app/services/purchase_feo_checks.py).

Три теста:
1. Разбиение многокатегорийной закупки-заявки — части получают wish_id,
   feo_per_item=True (без reason="header" на _item_feo_mismatch), status=
   'plan_schedule' (не легаси 'planned').
2. PATCH /api/purchases/{id} с ТЕМ ЖЕ subsidy_id, что уже стоит на части, —
   не попадает в ignored_fields (регресс тоста «Субсидия (закупка уже на
   стадии договора)» на автосейве, которую не менял).
3. GET /api/wishes/{wish_id}/purchases-board находит части (parent_purchase_id)
   даже если на конкретной части wish_id ещё не проставлен (подстраховка до
   прогона backfill-миграции c7d9e1f3g5h7 на старых данных)."""
import pytest
from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.services.purchase_feo_checks import _item_feo_mismatch
from app.services.purchase_split import resolve_part_feo_header


async def _seed_wish_purchase_two_categories(db_session, test_org):
    """Заявка wish, закупка wish_id=wish.id, feo_category_id шапки=NULL,
    feo_per_item=False, 2 позиции — у каждой своя плановая позиция СВОЕЙ
    категории ФЭО (ровно баг-репорт: позиции разных категорий внутри одной
    закупки-заявки, до разбиения)."""
    subsidy = Subsidy(name="Тест-заявка-226", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat_a = FeoCategory(subsidy_id=subsidy.id, name="Статья А", level=1)
    cat_b = FeoCategory(subsidy_id=subsidy.id, name="Статья Б", level=1)
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    fpi_a = FeoPlannedItem(feo_category_id=cat_a.id, name="План А", unit="шт")
    fpi_b = FeoPlannedItem(feo_category_id=cat_b.id, name="План Б", unit="шт")
    db_session.add_all([fpi_a, fpi_b])
    await db_session.flush()

    wish = Wish(org_id=test_org.id, title="Заявка 226 теста", status="approved")
    db_session.add(wish)
    await db_session.flush()

    p = Purchase(
        item_name="Закупка заявки 226 теста", subsidy_id=subsidy.id, wish_id=wish.id,
        # 'plan_schedule' (не 'wishes') — проверяем именно общий fallback-статус
        # частей без стадии договора (раньше легаси 'planned', см. докстринг
        # split_purchase_core); 'wishes'-исходная — отдельный, уже существующий
        # до этой правки особый случай (части наследуют 'wishes'), не предмет
        # этого теста.
        status="plan_schedule", feo_category_id=None, feo_per_item=False,
    )
    db_session.add(p)
    await db_session.flush()

    it_a = PurchaseItem(
        purchase_id=p.id, item_name="Товар А", quantity=1, unit="шт",
        unit_price=100, total_price=100, feo_category_id=cat_a.id, feo_planned_item_id=fpi_a.id,
    )
    it_b = PurchaseItem(
        purchase_id=p.id, item_name="Товар Б", quantity=1, unit="шт",
        unit_price=200, total_price=200, feo_category_id=cat_b.id, feo_planned_item_id=fpi_b.id,
    )
    db_session.add_all([it_a, it_b])
    await db_session.commit()
    await db_session.refresh(p)
    await db_session.refresh(it_a)
    await db_session.refresh(it_b)
    return wish, p, it_a, it_b, cat_a, cat_b


@pytest.mark.asyncio
async def test_split_multi_category_wish_purchase_links_parts(client, db_session, admin_headers, test_org):
    wish, p, it_a, it_b, cat_a, cat_b = await _seed_wish_purchase_two_categories(db_session, test_org)

    resp = await client.post(
        f"/api/purchases/{p.id}/split",
        json={"groups": [
            {"column_key": "Группа А", "item_ids": [it_a.id]},
            {"column_key": "Группа Б", "item_ids": [it_b.id]},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    part_ids = resp.json()["purchase_ids"]
    assert len(part_ids) == 2

    rows = (await db_session.execute(
        select(Purchase).options().where(Purchase.id.in_(part_ids))
    )).scalars().all()
    for part in rows:
        assert part.wish_id == wish.id, f"часть {part.id}: wish_id не унаследован"
        assert part.status == "plan_schedule", f"часть {part.id}: статус {part.status!r}, ожидали 'plan_schedule'"
        # Каждая часть одно-категорийна внутри себя — feo_per_item НЕ обязан
        # включаться (проверяется ниже отдельным тестом на многокатегорийной
        # части), но feo_category_id шапки должен подхватить единственную
        # категорию своих позиций (была NULL у исходной).
        part_items = (await db_session.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == part.id)
        )).scalars().all()
        assert len(part_items) == 1
        assert part.feo_category_id == part_items[0].feo_category_id

        # Главное регресс-условие: баннер «РАСХОЖДЕНИЕ КАТЕГОРИИ ФЭО» не
        # должен загораться ни на одной позиции части.
        mismatch = await _item_feo_mismatch(db_session, part, part_items[0])
        assert mismatch is None, f"часть {part.id}: ложный feo-mismatch {mismatch}"


@pytest.mark.asyncio
async def test_split_part_with_differing_categories_gets_feo_per_item(db_session, test_org):
    """Юнит resolve_part_feo_header (ПРАВИЛО №6 — тот же источник, что и
    alembic-backfill c7d9e1f3g5h7) напрямую: группа с >1 различной категорией
    позиций → feo_per_item=True."""
    per_item, cat_id = resolve_part_feo_header(False, None, [1, 2])
    assert per_item is True
    assert cat_id is None  # неоднозначно, шапку не придумываем

    per_item2, cat_id2 = resolve_part_feo_header(False, None, [5, 5])
    assert per_item2 is False
    assert cat_id2 == 5  # одна категория у всех позиций → подставляем в шапку

    per_item3, cat_id3 = resolve_part_feo_header(True, 7, [5, 5])
    assert per_item3 is True  # исходный feo_per_item=True не откатывается
    assert cat_id3 == 7  # шапка уже была — не трогаем


@pytest.mark.asyncio
async def test_patch_same_subsidy_id_not_ignored(client, db_session, admin_headers, test_org):
    """Регресс: PATCH с subsidy_id, РАВНЫМ текущему, на статусе ПОСЛЕ
    SUBSIDY_PATCHABLE_STATUSES не должен попадать в ignored_fields — значение
    не менялось, значит это не попытка смены финансирования."""
    subsidy = Subsidy(name="Тест-патч-субсидии", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    p = Purchase(
        item_name="Закупка для PATCH-теста", subsidy_id=subsidy.id,
        status="contracted",  # ВНЕ SUBSIDY_PATCHABLE_STATUSES
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.patch(
        f"/api/purchases/{p.id}",
        json={"subsidy_id": subsidy.id, "subject": "Без изменений по субсидии"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "subsidy_id" not in (body.get("ignored_fields") or []), body.get("ignored_fields")


@pytest.mark.asyncio
async def test_purchases_board_finds_parts_via_parent_even_without_wish_id(client, db_session, admin_headers, test_org):
    """GET /api/wishes/{wish_id}/purchases-board находит часть разбиения через
    parent_purchase_id, даже если на самой части wish_id почему-то ещё не
    проставлен (старые данные до backfill-миграции c7d9e1f3g5h7)."""
    wish = Wish(org_id=test_org.id, title="Заявка для board-теста", status="approved")
    db_session.add(wish)
    await db_session.flush()

    source = Purchase(item_name="Исходная (уже split)", wish_id=wish.id, status="split")
    db_session.add(source)
    await db_session.flush()

    part = Purchase(
        item_name="Часть без wish_id", status="plan_schedule",
        parent_purchase_id=source.id, wish_id=None,
    )
    db_session.add(part)
    await db_session.commit()
    await db_session.refresh(part)

    resp = await client.get(f"/api/wishes/{wish.id}/purchases-board", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    board_ids = {row["id"] for row in resp.json()["purchases"]}
    assert part.id in board_ids, "часть не найдена на доске заявки через parent_purchase_id"
    assert source.id not in board_ids, "исходная 'split'-закупка не должна попадать в канбан заявки"
