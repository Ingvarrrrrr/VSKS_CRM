"""Сериализация PurchaseItem/Purchase в Pydantic-схемы ответа API.

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения. _purchase_to_full — единая точка сборки PurchaseOutFull и для
списка (GET /api/purchases), и для карточки (GET /api/purchases/{id}) —
второй копии сборки не заводить (ПРАВИЛО №6).
"""
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.schemas.schemas import PurchaseItemOut, PurchaseOutFull, PurchaseFileOut, SubsidyAllocationOut, PurchaseAmountsOut
from app.services.purchase_contract_header import contract_header as _contract_header


def _item_to_out(item: PurchaseItem, plan_residual=None, plan_planned_amount=None) -> PurchaseItemOut:
    product_name = None
    product_photo_url = None
    product_description = None
    product_description_44fz = None
    if item.product:
        product_name = item.product.name
        product_photo_url = item.product.photo_url
        product_description = item.product.description
        product_description_44fz = item.product.description_44fz
    return PurchaseItemOut(
        id=item.id,
        product_id=item.product_id,
        item_name=item.item_name,
        item_type=item.item_type,
        quantity=item.quantity,
        unit=item.unit,
        unit_price=item.unit_price,
        total_price=item.total_price,
        final_unit_price=item.final_unit_price,
        final_total=item.final_total,
        # Снимок плана (Шаг 1 «план ≠ факт») — отдаём фронту вместе с текущей ценой,
        # иначе дерево ФЭО/панели план-vs-факт (Шаг 5) не смогут отличить план от ТЗ.
        planned_quantity=getattr(item, 'planned_quantity', None),
        planned_unit_price=getattr(item, 'planned_unit_price', None),
        planned_total=getattr(item, 'planned_total', None),
        country_origin=item.country_origin,
        # Phase 26-V/W/BB: contractor + match + receipt linkage — критично для UI
        contractor_id=item.contractor_id,
        contractor_inn=item.contractor_inn,
        contractor_name=item.contractor_name,
        match_confirmed=item.match_confirmed if item.match_confirmed is not None else True,
        receipt_id=getattr(item, 'receipt_id', None),
        vat_rate=getattr(item, 'vat_rate', None),
        vat_amount=getattr(item, 'vat_amount', None),
        total_with_vat=getattr(item, 'total_with_vat', None),
        feo_planned_item_id=getattr(item, 'feo_planned_item_id', None),
        feo_category_id=getattr(item, 'feo_category_id', None),
        over_plan=getattr(item, 'over_plan', False) or False,
        needed_date=getattr(item, 'needed_date', None),
        accepted_name=getattr(item, 'accepted_name', None),
        accepted_quantity=getattr(item, 'accepted_quantity', None),
        accepted_unit=getattr(item, 'accepted_unit', None),
        product_name=product_name,
        product_photo_url=product_photo_url,
        product_description=product_description,
        product_description_44fz=product_description_44fz,
        plan_residual=plan_residual,
        plan_planned_amount=plan_planned_amount,
    )


def _purchase_to_full(
    p: Purchase, contractors: dict, subsidies: dict, allocations: list | None = None,
    contractor_inns: dict | None = None, receipt_map: dict | None = None, ru_map: dict | None = None,
    su_map: dict | None = None, feo_excess_map: dict | None = None, item_plan_map: dict | None = None,
    wish_title_map: dict | None = None, wish_status_map: dict | None = None,
    feo_mismatch_map: dict | None = None, amounts_map: dict | None = None,
    contract=None,
) -> PurchaseOutFull:
    # Ленивый импорт — избежать цикла на уровне модуля: purchases.py (ядро)
    # импортирует _purchase_to_full ОТСЮДА, поэтому этот модуль не может
    # импортировать is_framework_head из purchases.py на уровне модуля.
    from app.routers.purchases import is_framework_head

    data = {c.name: getattr(p, c.name) for c in Purchase.__table__.columns}
    # ПРАВИЛО №6 (2026-09-07, группа D7): при заданном contract_id — шапка
    # договора (number/date/type/contractor_id) читается из связанного
    # Contract, а не из денормализованного кэша на закупке (см. докстринг
    # app.services.purchase_contract_header — четыре фазы бэкфилла чинили
    # ровно это расхождение). `contract` — уже загруженный вызывающим
    # (selectinload(Purchase.contract), без N+1); если не передан — как
    # раньше, из кэша.
    _hdr = _contract_header(p, contract)
    data["contract_number"] = _hdr.contract_number
    data["contract_date"] = _hdr.contract_date
    data["purchase_contract_type"] = _hdr.purchase_contract_type
    data["contractor_id"] = _hdr.contractor_id
    _ipm = item_plan_map or {}
    items = [
        _item_to_out(i, *(_ipm.get(i.id) or (None, None)))
        for i in (p.items or [])
    ]
    files = [
        PurchaseFileOut(
            id=f.id,
            purchase_id=f.purchase_id,
            filename=f.filename,
            mime_type=f.mime_type,
            size=f.size,
            file_type=f.file_type,
            doc_format=f.doc_format,
            is_active=f.is_active if f.is_active is not None else True,
            content_hash=f.content_hash,
            uploaded_by_id=f.uploaded_by_id,
            created_at=str(f.created_at) if f.created_at else None,
        )
        for f in (p.files or [])
    ]
    alloc_out = None
    if allocations is not None:
        alloc_out = [
            SubsidyAllocationOut(
                id=a.id,
                subsidy_id=a.subsidy_id,
                subsidy_name=a.subsidy.name if a.subsidy else subsidies.get(a.subsidy_id),
                amount=a.amount,
            )
            for a in allocations
        ]
    # Multi-contractor label for advance reports
    multi_contractor_label: str | None = None
    if p.purchase_method == 'advance' and p.items:
        unique_names = {item.contractor_name for item in p.items if item.contractor_name}
        if len(unique_names) > 1:
            multi_contractor_label = "Множественный контрагент"
        elif len(unique_names) == 1:
            multi_contractor_label = next(iter(unique_names))

    _excess = (feo_excess_map or {}).get(p.id) or {}
    _mismatch = (feo_mismatch_map or {}).get(p.id) or {}
    # ПРАВИЛО №6 (2026-09-05): amounts_map — bulk-загруженный
    # app.services.purchase_amounts.load_purchase_amounts (без N+1, см. вызывающий
    # код). Если карта не передана (путь ещё не переведён) — считаем на месте
    # чистой функцией purchase_amounts() без item-фолбэков (contract_items_total/
    # items_total/framework_max_amount не переданы), лучше приблизительное
    # значение, чем совсем без amounts.
    from app.services.purchase_amounts import PurchaseAmounts as _PurchaseAmounts, purchase_amounts as _purchase_amounts_fn
    _pa: _PurchaseAmounts = (amounts_map or {}).get(p.id) or _purchase_amounts_fn(p)
    amounts_out = PurchaseAmountsOut(
        plan=_pa.plan, contract=_pa.contract, fact=_pa.fact, paid=_pa.paid,
        effective=_pa.effective, effective_source=_pa.effective_source,
    )
    return PurchaseOutFull(
        **data,
        amounts=amounts_out,
        items=items,
        files=files,
        files_count=len(files),
        contractor_name=contractors.get(_hdr.contractor_id),
        contractor_inn=(contractor_inns or {}).get(_hdr.contractor_id),
        feo_category_name=p.feo_category.name if p.feo_category else None,
        subsidy_name=subsidies.get(p.subsidy_id),
        event_name=p.event.name if p.event else None,
        subsidy_allocations=alloc_out,
        last_receipt_date=(receipt_map or {}).get(p.id),
        reimbursement_user_name=(ru_map or {}).get(p.reimbursement_user_id),
        multi_contractor_label=multi_contractor_label,
        # Остановка закупки (владелец, 2026-08-13) — имя того, кто остановил
        # (см. Wish._enrich stopped_by_name: тот же приём — full_name или username).
        stopped_by_name=(su_map or {}).get(p.stopped_by),
        # Превышение плана ФЭО (план crystalline-soaring-heron.md, п.4) — см.
        # _compute_purchase_feo_excess; пусто (feo_excess=False), если карта не
        # передана (вызывающий не просил ?with_feo_excess) или превышения нет.
        feo_excess=_excess.get("feo_excess", False),
        feo_excess_hint=_excess.get("feo_excess_hint"),
        feo_excess_amount=_excess.get("feo_excess_amount"),
        feo_excess_category=_excess.get("feo_excess_category"),
        feo_excess_category_id=_excess.get("feo_excess_category_id"),
        feo_excess_state=_excess.get("feo_excess_state", "none"),
        feo_excess_approved_by=_excess.get("feo_excess_approved_by"),
        feo_excess_approved_at=_excess.get("feo_excess_approved_at"),
        # Родительская заявка (план crystalline-soaring-heron.md, п.3) — «Создана
        # из заявки №N «…»» на карточке закупки.
        wish_title=(wish_title_map or {}).get(p.wish_id) if p.wish_id else None,
        # Статус заявки — карточке закупки в статусе 'wishes' нужно объяснить,
        # ждёт она одобрения или отцеплена (владелец, 2026-08-21, дефект 1).
        wish_status=(wish_status_map or {}).get(p.wish_id) if p.wish_id else None,
        # Владелец (2026-09-02): «уведомление глобально, если позиция категории
        # ФЭО вверху и в каждом товаре не соответствует друг другу» — см.
        # _compute_purchase_feo_mismatch. Считается ВСЕГДА (не опционально, в
        # отличие от feo_excess) — расхождение редкое (страховка на будущее),
        # дешевле проверять всегда, чем прятать за флагом.
        feo_mismatch=_mismatch.get("feo_mismatch", False),
        feo_mismatch_items=_mismatch.get("feo_mismatch_items", []),
        # Владелец (2026-09-03): фронту нужно отличать рамочную ГОЛОВУ
        # (согласование необходимости договора — ApprovalPanel в спец-режиме)
        # от дочерних закупок внутри того же рамочного контракта (те
        # согласуются как обычная закупка, purchase_contract_type у них тоже
        # framework_* — одного этого поля недостаточно). Единый источник
        # истины — is_framework_head() в app.routers.purchases.
        is_framework_head=is_framework_head(p),
    )
