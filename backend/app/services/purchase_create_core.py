"""insert_purchase_with_items — ядро POST /api/purchases/ (создание закупки).

Вынесено из app/routers/purchases.py::create_purchase (рефакторинг под импорт
исторических закупок, задача 02.10.2026, БЕЗ изменения поведения — ПРАВИЛО №5).
Было ~200 строк одной функции-эндпоинта вперемешку с HTTP-специфичными
проверками (admin_override/403, excess-предупреждениями, авто-заявкой на
возмещение авансового, согласованиями превышения) — сюда вынесена только
механическая часть вставки: генерация номера закупки, сам объект Purchase,
реестровый/договорной номер, позиции (матчинг товара, контрагент по строке,
форма позиции, снимок план=факт на момент создания), субсидийные аллокации,
пересчёт денег, запись в BudgetHistory.

НЕ входит сюда (осознанно, остаётся в create_purchase вокруг вызова):
- авто-заявка на возмещение авансового отчёта (создаёт Wish/WishItem —
  отдельная сущность, не часть вставки закупки);
- регистрация запросов на согласование превышения ТЗ/типа (tz_excess_approval,
  type_excess_approval) — это ПОСЛЕ-эффект, не часть вставки;
- уведомления;
- db.commit() — коммитит вызывающий, как и раньше.

create_purchase вызывает insert_purchase_with_items — поведение эндпоинта
идентично версии до выноса.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.product import Product
from app.models.user import User
from app.models.subsidy_allocation import PurchaseSubsidyAllocation
from app.schemas.schemas import PurchaseCreate
from app.auth.jwt import get_single_org_id
from app.product_matcher import find_matching_product
from app.services.item_forms import item_form_for_purchase_item
from app.services.item_amounts import apply_item_amounts
from app.services.item_types import normalize_item_type
from app.services.item_contractor import set_item_contractor


async def insert_purchase_with_items(
    db: AsyncSession,
    data: PurchaseCreate,
    current_user,
    *,
    items_data: list,
    total_nmck: Optional[Decimal],
) -> tuple[Purchase, list[PurchaseItem]]:
    """Создаёт Purchase + его PurchaseItem, без commit.

    items_data/total_nmck переданы вызывающим — они считаются в create_purchase
    ДО вызова (авто-план авансового, excess-проверки читают их же, тот же
    предпросмотр суммы, что и здесь — ПРАВИЛО №6, не второй расчёт).

    Возвращает (p, created_items) — created_items в порядке items_data
    (нужно вызывающему для hard-link с WishItem авто-заявки авансового).
    """
    # Ленивые импорты — во избежание цикла purchases.py (роутер) ↔ этот модуль:
    # _sync_purchase_from_contract определена в самом purchases.py, а
    # _assign_framework_seq/recalc_purchase_money живут в своих сервисных
    # модулях без обратной зависимости на purchases.py.
    from app.routers.purchases import _sync_purchase_from_contract
    from app.routers.purchase_budget import _assign_framework_seq
    from app.services.purchase_money_writer import recalc_purchase_money

    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    dump = data.model_dump(exclude={"items", "subsidy_allocations"})
    dump["total_nmck"] = total_nmck
    # Контракт API (PLAN.md шаг 3, п. D, ревью 02.10.2026): Purchase.economy
    # больше не пишется из payload — экономия теперь РАСЧЁТ
    # (app.services.purchase_economy, ПРАВИЛО №6). Поле оставлено в схеме для
    # обратной совместимости старых клиентов, значение молча игнорируется.
    dump.pop("economy", None)
    # Phase 28 B4: validate provided assigned_user_id
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    # Auto-assign current user as owner when frontend did not specify one.
    # Без этого закупка с assigned_user_id=NULL становится невидимой для рядового
    # автора (list_purchases фильтрует по visible_user_ids; NULL IN (...) = false).
    if not dump.get("assigned_user_id"):
        dump["assigned_user_id"] = current_user.id
    # SN-UX: для СЗ авто-заполнить автора (текущий) и дату (сейчас) если фронт не прислал
    if dump.get("purchase_basis") == "service_note":
        if not dump.get("service_note_by"):
            dump["service_note_by"] = current_user.id
        if not dump.get("service_note_at"):
            dump["service_note_at"] = datetime.now(timezone.utc)
    p = Purchase(**dump)
    db.add(p)
    await db.flush()  # get p.id before commit

    year = date.today().year
    if not p.registry_number:
        p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
    # removed in phase26-j-1: only set when single contract без FK на existing contracts row
    # auto-generate мусорит номером вида "2026/42" для рамочных закупок с реальным contract_id.
    if not p.contract_number and not p.contract_id:
        p.contract_number = f"{year}/{p.id}"

    # phase26-j-1: sync number/date/type из связанного контракта, если contract_id задан
    await _sync_purchase_from_contract(p, db)

    await _assign_framework_seq(p, db)

    # item-forms-accommodation-transport.md: форма позиций выводится из
    # p.contract_form (item_form_for_purchase_item, по КАЖДОЙ строке — см.
    # цикл ниже) — для спец-форм apply_item_amounts пересчитывает
    # quantity/unit_price/total_price из extra_attrs и ПОБЕЖДАЕТ то, что
    # прислал клиент; для обычных позиций (item_form=None) поведение не
    # меняется — total_price по-прежнему берётся из payload как есть.

    # ПРАВИЛО №6 (группа D5, QA-находка): фронт (PurchaseItemsEditor.vue) кладёт
    # contractor_id/contractor_inn/contractor_name прямо в объект позиции —
    # PurchaseItem(**d) писал их МИМО set_item_contractor, снова заводя текст
    # рядом с FK при обычном сохранении из UI. Карта контрагентов — один SELECT
    # на ВСЕ позиции запроса (без N+1), как в wish_distribution.py.
    _item_dumps = [item_d.model_dump() for item_d in items_data]
    _item_contractor_ids = {d.get("contractor_id") for d in _item_dumps if d.get("contractor_id")}
    _item_contractors_map: dict = {}
    if _item_contractor_ids:
        _ic_rows = (await db.execute(select(Contractor).where(Contractor.id.in_(_item_contractor_ids)))).scalars().all()
        _item_contractors_map = {c.id: c for c in _ic_rows}

    # W1 (прод, заявка №88, 2026-09-30): позиции этой закупки в порядке
    # _item_dumps/items_data — тот же порядок, в котором (is_advance) создатель
    # копирует WishItems компаньона (см. create_purchase), что позволяет
    # проставить hard link purchase_items.wish_item_id по позиции без угадывания
    # сопоставления — см. app/services/advance_wish_sync.py.
    _created_items: list[PurchaseItem] = []
    for d in _item_dumps:
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    # Баг 2026-10-01 (ПРАВИЛО №6): item_type строки позиции —
                    # это Product.item_kind («товар»/«услуга»/«работа»), а не
                    # product_type («Вид» — свободный текст). Запись в
                    # product_type создавала второй источник типа, из-за
                    # которого /products/match затем отдавал его обратно как
                    # item_type (см. app/routers/products_match.py).
                    item_kind=normalize_item_type(d.get("item_type")) or "товар",
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        _d_contractor_id = d.pop("contractor_id", None)
        _d_contractor_inn = d.pop("contractor_inn", None)
        _d_contractor_name = d.pop("contractor_name", None)
        item = PurchaseItem(purchase_id=p.id, **d)
        _created_items.append(item)
        # «Проживание и питание»: форма берётся ПО СТРОКЕ (item.item_form),
        # не одна _item_form_create на всю закупку — item_form_for_purchase_item
        # зеркалит item_form_for_purchase для contract_form без выбора на строке.
        _row_item_form_create = item_form_for_purchase_item(p, item)
        if _row_item_form_create:
            apply_item_amounts(item, _row_item_form_create)
        # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
        _d_contractor_obj = _item_contractors_map.get(_d_contractor_id) if _d_contractor_id else None
        if _d_contractor_obj is not None:
            set_item_contractor(item, contractor=_d_contractor_obj, inn=_d_contractor_inn, name=_d_contractor_name)
        elif _d_contractor_id:
            set_item_contractor(item, contractor_id=_d_contractor_id)
        else:
            set_item_contractor(item, inn=_d_contractor_inn, name=_d_contractor_name)
        # Снимок плана (Шаг 1 «план ≠ факт»): позиция создаётся напрямую (не из
        # заявки) — план фиксируется как введённые сейчас значения, если снимок
        # не передан явно клиентом.
        if item.planned_quantity is None and item.planned_unit_price is None and item.planned_total is None:
            item.planned_quantity = item.quantity
            item.planned_unit_price = item.unit_price
            item.planned_total = item.total_price
        db.add(item)

    # Save subsidy allocations
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=p.id,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # ПРАВИЛО №6 (2026-09-05): единственный писатель денежных колонок — раньше
    # здесь была вторая копия «contract_price = Σ items» БЕЗ проверки статуса
    # (писала цену договора даже для закупки на стадии `wishes`, до всякого
    # договора — то самое «второе перо», конкурирующее с
    # _recalc_contract_price_from_contract_items). recalc_purchase_money сам
    # решает, писать ли contract_price, по стадии (см. purchase_money_writer.py).
    _items_total_create = (
        sum((i.total_price or Decimal("0")) for i in items_data) if items_data else None
    )
    await recalc_purchase_money(db, p, items_total=_items_total_create, contract_items_total=None)

    # Budget history write hook — record initial planned_total_price
    if p.subsidy_id and p.planned_total_price:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=p.subsidy_id,
            purchase_id=p.id,
            entity_type="purchase",
            old_value=None,
            new_value=float(p.planned_total_price),
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    return p, _created_items
