"""Перенос согласованной заявки в закупку(и): /convert, /convert-to-advance-report,
/approve-distribution.

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-06,
разрезание wishes.py по образцу purchases.py → purchase_ops.py/purchase_*.py)
БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

Хелперы ядра вызываются через `wishes_core.<имя>` (не прямым `from ... import`),
чтобы monkeypatch на ядре продолжал действовать — см. докстринг wish_transitions.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, ADMIN_ROLES, MANAGER_ROLES
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.wish_item import WishItem
from app.schemas.wishes import WishConvert
from app.services.tz_excess_approval import register_tz_excess_approvals
from app.routers import wishes as wishes_core

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


@router.post("/{wish_id}/convert")
async def convert_wish(
    wish_id: int,
    body: WishConvert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('wishes')),
):
    """Convert an approved wish to a purchase (org_admin+, approved -> converted).
    B4: copies all WishItems to PurchaseItems with quantity/price from wish items.
    B9: carries feo_category_id from wish and per-item feo_category_id.
    B10: backfills product_id by item_name for legacy wish_items.
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from sqlalchemy.orm import selectinload as sil

    wish = await wishes_core._load_wish(wish_id, db)
    # Идемпотентность (владелец, 2026-08-20): последний согласующий цепочки сам
    # переносит заявку в закупку (см. wish_approvals.py::decide, _distribute_wish_to_purchases
    # + wish.status = "converted"). Если фронт после этого всё равно дёргает /convert
    # (например пользователь нажал «Передать в План закупок» по старой памяти) — заявка
    # уже 'converted', и раньше это падало 400 «должна быть в статусе approved», хотя
    # закупка реально была создана. Статус 'converted' здесь пропускаем в общий путь —
    # ниже блок «защита от дублей» (existing purchases) находит её и просто возвращает,
    # вторую закупку не создавая.
    _was_already_converted = wish.status == "converted"

    if not wishes_core._is_saas(current_user) and wish.status not in ("approved", "converted"):
        from app.routers.feo_planned_items import _WISH_STATUS_LABELS
        _label = _WISH_STATUS_LABELS.get(wish.status, wish.status)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Заявку нельзя перенести в закупку: она в статусе «{_label}». "
                "Перенести можно только согласованную заявку."
            ),
        )

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    await wishes_core._ensure_no_pending_approvals(wish, db, current_user)

    # Защита от дублей: закупки по заявке уже есть — не создаём вторую,
    # скрытые (status='wishes') продвигаем в План закупок
    existing = (await db.execute(
        select(Purchase).where(Purchase.wish_id == wish.id)
    )).scalars().all()

    if _was_already_converted and not existing:
        # Рассинхрон: заявка помечена converted, но ни одной закупки по ней нет —
        # такого в норме не бывает (единственный путь в 'converted' — либо этот же
        # эндпоинт, либо decide()/approve(), оба создают закупку ДО смены статуса).
        raise HTTPException(
            status_code=409,
            detail=(
                "Заявка помечена как перенесённая в закупку, но сама закупка не найдена "
                "(рассинхронизация данных). Обратитесь к администратору — вручную создавать "
                "закупку заново нельзя, это привело бы к дублю."
            ),
        )

    if existing:
        # W2-гейт: проверяем категорию ФЭО и даты ПЕРЕД продвижением скрытых закупок —
        # это тоже момент «попадания в План закупок» (владелец, 2026-08-11).
        wishes_existing = [ep for ep in existing if ep.status == "wishes"]
        if wishes_existing and getattr(wish, 'source', None) != 'advance_report':
            items_res = await db.execute(select(WishItem).where(WishItem.wish_id == wish.id))
            _all_items_existing = items_res.scalars().all()
            await wishes_core._ensure_feo_categories_assigned(
                wish, [it for it in _all_items_existing if wishes_core._is_meaningful_item(it)], db,
            )
            await wishes_core._ensure_needed_dates(wish, db, _all_items_existing)
        # Задача владельца, план zany-fluttering-mountain.md п.4 (2026-08-10): эта
        # ветка — ОТДЕЛЬНЫЙ путь движения закупки по стадиям (wishes → plan_schedule),
        # не проходящий через POST /api/purchases/{pid}/transition (см. её гейт в
        # purchase_transitions.py) — идемпотентное повторное согласование заявки,
        # у которой уже есть скрытые закупки.
        # Владелец (2026-08-12): продвижение больше НЕ блокируется несогласованным
        # превышением — assert_no_unapproved_excess убран, вместо отказа собираем
        # excess_warnings (по категории и её предкам) ПОСЛЕ фактического
        # продвижения статусов, см. _collect_excess_warnings.
        _cat_items: dict[int, list[dict]] = {}
        if wishes_existing:
            from app.models.purchase_item import PurchaseItem as _PurchaseItem
            _ep_ids = [ep.id for ep in wishes_existing]
            _items_res = await db.execute(
                select(_PurchaseItem).where(_PurchaseItem.purchase_id.in_(_ep_ids))
            )
            _items_by_purchase: dict[int, list] = {}
            for _pit in _items_res.scalars().all():
                _items_by_purchase.setdefault(_pit.purchase_id, []).append(_pit)
            for ep in wishes_existing:
                _ep_items = _items_by_purchase.get(ep.id, [])
                for _pit in _ep_items:
                    _cid = _pit.feo_category_id or ep.feo_category_id
                    if _cid:
                        _cat_items.setdefault(_cid, []).append({
                            "name": _pit.item_name, "amount": float(_pit.total_price or 0),
                        })
                if not any(_pit.feo_category_id for _pit in _ep_items) and ep.feo_category_id:
                    _cat_items.setdefault(ep.feo_category_id, []).append({
                        "name": ep.item_name or ep.subject or f"Закупка №{ep.id}",
                        "amount": float(ep.total_nmck or ep.planned_total_price or 0),
                    })
        for ep in existing:
            if ep.status == "wishes":
                ep.status = "plan_schedule"
            # Контрагент заявки (владелец, 2026-08-17) — заполняем ТОЛЬКО пустое
            # поле закупки, не перетираем уже заданное (могло быть проставлено
            # вручную прямо в закупке).
            if getattr(wish, 'contractor_id', None) and not ep.contractor_id:
                ep.contractor_id = wish.contractor_id
        wish.status = "converted"
        wish.approved_by = wish.approved_by or current_user.id
        wish.purchase_id = wish.purchase_id or existing[0].id
        # Повторный перенос (владелец, план crystalline-soaring-heron.md, п.2) —
        # тот же helper, что и в _distribute_wish_to_purchases: приводит предмет и
        # состав уже существующей закупки к текущей заявке (см. её докстринг).
        _purchase_sync = await wishes_core._sync_purchase_from_wish(wish, existing, db)
        await db.flush()
        _excess_warnings = await wishes_core._collect_excess_warnings(db, wish.subsidy_id, _cat_items)
        _tz_excess_approvals = await register_tz_excess_approvals(
            db, getattr(wish, "_tz_excess_violations_sync", []) or [],
            subsidy_id=wish.subsidy_id, current_user=current_user,
            context_label=f"повторное согласование заявки №{wish.id} (/convert)",
        )
        await db.commit()
        return {
            "wish_id": wish.id, "purchase_id": existing[0].id, "status": "converted",
            "registry_number": existing[0].registry_number,
            "already_converted": _was_already_converted,
            "excess_warnings": _excess_warnings,
            "tz_excess_approvals": _tz_excess_approvals,
            "purchase_sync": _purchase_sync,
        }

    # Preload items with products (B4/B10)
    res = await db.execute(
        select(WishItem).options(sil(WishItem.product)).where(WishItem.wish_id == wish.id)
    )
    items_full = res.scalars().all()

    # Гейт ФЭО (владелец, 2026-08-11): /convert — отдельный путь создания закупок
    # мимо _distribute_wish_to_purchases (см. комментарий про «Дефект» ниже про
    # тот же паразитный дубль для «ТЗ не выше плана»/превышения ФЭО) — тем же
    # общим хелпером закрываем и его. См. docstring _ensure_feo_categories_assigned.
    await wishes_core._ensure_feo_categories_assigned(wish, [it for it in items_full if wishes_core._is_meaningful_item(it)], db)

    # W2-гейт в основном пути /convert
    await wishes_core._ensure_needed_dates(wish, db, items_full)

    # B10: Backfill product_id for legacy items lacking it
    missing = [it for it in items_full if not it.product_id and (it.item_name or "").strip()]
    if missing:
        names = list({(it.item_name or "").strip() for it in missing})
        pres = await db.execute(select(Product).where(Product.name.in_(names)))
        name_to_product = {(p.name or "").strip().lower(): p for p in pres.scalars().all()}
        for it in missing:
            hit = name_to_product.get((it.item_name or "").strip().lower())
            if hit:
                it.product_id = hit.id

    # Дефект (приёмка 2026-08-07): /convert — ОТДЕЛЬНЫЙ путь создания закупок,
    # не проходящий через _distribute_wish_to_purchases (approve_wish и
    # force_wish_status('converted') используют её и получают проверки автоматом,
    # этот эндпоинт — нет, шёл мимо гейта «ТЗ не выше плана» и мимо превышения
    # ФЭО). Воспроизводим ТОТ ЖЕ порядок и теми же общими функциями (никакой
    # второй копии логики): автозаведение → «ТЗ не выше плана» → превышение ФЭО.
    # Обоснование порядка — см. комментарий у аналогичного блока в
    # _distribute_wish_to_purchases.
    from app.services.plan_autoassign import auto_assign_planned_items as _auto_assign_planned_items
    await _auto_assign_planned_items(
        items_full, wish.feo_category_id, db, note=f"заявкой №{wish.id} (/convert)",
    )
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): накопление по общей
    # плановой позиции в пределах ЭТОЙ заявки — та же группировка, что у
    # assert_tz_batch_not_over_plan.
    # Владелец (2026-09-02): больше НЕ 409 здесь — собираем нарушения, регистрируем
    # запрос на согласование ПОСЛЕ создания закупки (см. app.services.tz_excess_approval
    # и комментарий у аналогичного места в _distribute_wish_to_purchases выше).
    from app.services.tz_excess_approval import collect_tz_over_plan_violations
    _tz_violations = await collect_tz_over_plan_violations(
        db, items_full, fallback_category_id=wish.feo_category_id,
    )
    # Владелец (2026-08-12): /convert больше не блокируется несогласованным
    # превышением ФЭО — assert_no_unapproved_excess убран, вместо отказа собираем
    # excess_warnings ПОСЛЕ создания закупки (см. вызов _collect_excess_warnings
    # ниже, уже после flush() позиций).
    _conv_cat_items: dict[int, list[dict]] = {}
    for _wi in items_full:
        _cid = _wi.feo_category_id or wish.feo_category_id
        if _cid:
            _conv_cat_items.setdefault(_cid, []).append({
                "name": _wi.item_name, "amount": float(_wi.total_price or 0),
            })

    # B4: planned_total_price = SUM(items.total_price)
    total_nmck = sum(float(i.total_price or 0) for i in items_full)
    total_qty = sum(float(i.quantity or 0) for i in items_full)

    # Владелец (2026-09-06, QA раунд 2, п.2): «Утверждённая цена»
    # (approved_price/approved_quantity) действует ТОЛЬКО для заявок БЕЗ
    # позиций — там нечего скорректировать построчно, override — единственный
    # способ задать сумму. У заявки С позициями согласующий правит количество/
    # цену В САМИХ позициях (до конвертации) — сумма закупки строго = Σ
    # позиций (пересчитает recalc_purchase_money ниже); approved_price/
    # approved_quantity из тела запроса в этом случае ИГНОРИРУЮТСЯ (не 422 —
    # заявка всё равно конвертируется, просто override не участвует).
    _has_items = bool(items_full)
    _approved_price_ignored = _has_items and body.approved_price is not None
    _approved_quantity_ignored = _has_items and body.approved_quantity is not None
    if _has_items:
        eff_qty = total_qty or wish.quantity
        eff_price = total_nmck
    else:
        eff_qty = body.approved_quantity if (body.approved_quantity and float(body.approved_quantity) > 0) else wish.quantity
        eff_price = body.approved_price if (body.approved_price and float(body.approved_price) > 0) else wish.estimated_price
    if _approved_price_ignored or _approved_quantity_ignored:
        import logging as _logging_convert
        _logging_convert.getLogger(__name__).info(
            "convert_wish: заявка #%s имеет позиции — approved_price=%s/approved_quantity=%s "
            "из тела запроса проигнорированы, сумма закупки = Σ позиций (%s)",
            wish.id, body.approved_price, body.approved_quantity, total_nmck,
        )
    conv_dates = {wishes_core._eff_date(wish, wi) for wi in items_full}
    conv_dates.discard(None)
    conv_delivery_date = conv_dates.pop() if len(conv_dates) == 1 else None

    # C1: авансовый отчёт → фиксируем тип; обычная заявка → single
    _is_advance_conv = (getattr(wish, 'source', None) == 'advance_report')
    _conv_purchase_method = 'advance' if _is_advance_conv else 'single'
    _conv_payment_basis_type = 'advance_report' if _is_advance_conv else None
    p = Purchase(
        wish_id=wish.id,
        subsidy_id=body.subsidy_id or wish.subsidy_id,
        feo_category_id=wish.feo_category_id,  # B9
        event_id=getattr(wish, 'event_id', None),  # «Мероприятие»
        item_name=wish.title,
        subject=wish.title,
        planned_quantity=eff_qty,
        # ПРАВИЛО №6 (2026-09-06, уточнено QA раунд 2, п.2 — владелец):
        # total_nmck/nmck зеркалят planned_total_price (eff_price) —
        # раньше planned_total_price брал body.approved_price (одобренная
        # цена, которую согласующий может ввести ВРУЧНУЮ на этом экране — см.
        # WishConvert/convertForm), а total_nmck/nmck считали СВОЮ формулу
        # (БЕЗ учёта approved_price) — при override два поля расходились
        # сразу при создании. Решение владельца: approved_price/approved_
        # quantity действуют ТОЛЬКО для заявок БЕЗ позиций (eff_price/eff_qty
        # выше уже это учитывают — при наличии позиций override
        # ИГНОРИРУЕТСЯ, eff_price = Σ items); ниже, после вставки
        # PurchaseItem, recalc_purchase_money пересчитает все три поля из
        # фактической Σ (для закупки с позициями — то же самое число, что и
        # eff_price здесь; для headless — no-op, значения здесь остаются).
        planned_total_price=eff_price,
        total_nmck=eff_price,
        nmck=eff_price,
        status="plan_schedule",
        service_note_text=wish.justification,
        service_note_by=wish.created_by,
        # B1: исполнитель = executor_id (без фолбэка на инициатора)
        assigned_user_id=getattr(wish, 'executor_id', None),
        # B1: служебка «на чьё имя» = assigned_to заявки
        service_note_to_user_id=wish.assigned_to,
        execution_term=getattr(wish, 'execution_deadline', None),  # B-exec: срок исполнения
        delivery_date=conv_delivery_date,
        purchase_method=_conv_purchase_method,
        payment_basis_type=_conv_payment_basis_type,
        feo_per_item=bool(getattr(wish, 'feo_per_item', False)),
        vat_mode=(getattr(wish, 'vat_mode', None) or 'uniform'),
        # Контрагент заявки (владелец, 2026-08-17) — переезжает в закупку, если
        # указан. Purchase свежесозданный, поэтому «не перетирать уже заданное»
        # выполняется автоматически.
        contractor_id=getattr(wish, 'contractor_id', None),
    )
    db.add(p)
    await db.flush()  # get p.id

    # Контрагент заявки — на каждую позицию (см. аналогичный резолв в
    # _distribute_wish_to_purchases выше). Если контрагента в справочнике ещё
    # нет — свободный ввод contractor_name.
    _conv_contractor_obj = None
    if getattr(wish, 'contractor_id', None):
        from app.models.contractor import Contractor as _ConvContractor
        _conv_contractor_obj = await db.get(_ConvContractor, wish.contractor_id)

    # B4/B9/B10: copy all WishItems to PurchaseItems
    for wi in items_full:
        pi = PurchaseItem(
            purchase_id=p.id,
            product_id=wi.product_id,
            item_name=wi.item_name,
            item_type=wi.item_type,
            quantity=wi.quantity,           # B4: «утверждённое кол-во» = из WishItem
            unit=wi.unit,
            unit_price=wi.unit_price,       # B4: «утверждённая цена» = из WishItem
            total_price=wi.total_price,
            country_origin=wi.country_origin,
            feo_category_id=wi.feo_category_id,  # B9: per-item feo
            feo_planned_item_id=wi.feo_planned_item_id,  # расходуем уже запланированную позицию, не задваиваем план
            over_plan=getattr(wi, 'over_plan', False),
            needed_date=wishes_core._eff_date(wish, wi),  # W2: наследование эффективной даты
            wish_item_id=wi.id,  # W1: hard link to source WishItem
            vat_rate=getattr(wi, 'vat_rate', None),
            contractor_id=(_conv_contractor_obj.id if _conv_contractor_obj else None),
            contractor_inn=(_conv_contractor_obj.inn if _conv_contractor_obj else None),
            contractor_name=(
                _conv_contractor_obj.name if _conv_contractor_obj
                else getattr(wish, 'contractor_name', None)
            ),
        )
        db.add(pi)
    await db.flush()

    # ПРАВИЛО №6 (2026-09-06): единственный писатель денежных колонок — если у
    # закупки есть только что вставленные PurchaseItem, их фактическая Σ
    # становится planned_total_price/total_nmck/nmck (status="plan_schedule" —
    # не заморожена); если позиций нет (headless-заявка) — no-op, значения
    # выше (eff_price) остаются как есть. См. комментарий у конструктора
    # Purchase(...) выше про approved_price/body.approved_price.
    from app.services.purchase_money_writer import recalc_purchase_money as _recalc_purchase_money_convert
    await _recalc_purchase_money_convert(db, p)

    wish.purchase_id = p.id
    wish.status = "converted"
    wish.approved_by = current_user.id

    _excess_warnings = await wishes_core._collect_excess_warnings(db, wish.subsidy_id, _conv_cat_items)
    # Владелец (2026-09-02): регистрируем запрос(ы) на согласование превышения ТЗ
    # над плановой позицией ПОСЛЕ создания закупки (см. _tz_violations выше).
    _tz_excess_approvals = await register_tz_excess_approvals(
        db, _tz_violations, subsidy_id=wish.subsidy_id, current_user=current_user,
        context_label=f"согласование заявки №{wish.id} (/convert)",
    )
    await db.commit()

    return {
        "wish_id": wish.id, "purchase_id": p.id, "status": "converted",
        "registry_number": p.registry_number,
        "already_converted": False,
        "excess_warnings": _excess_warnings,
        "tz_excess_approvals": _tz_excess_approvals,
        # Первое создание закупки — синхронизировать нечего (см. purchase_sync
        # в ветке «существующая закупка» выше).
        "purchase_sync": None,
        # Владелец (2026-09-06, QA раунд 2, п.2): approved_price/approved_
        # quantity игнорируются, если у заявки есть позиции (см. комментарий
        # выше у _has_items) — фронт может показать это пользователю (скрытие
        # самого поля — другая задача, не эта правка).
        "approved_price_ignored": _approved_price_ignored,
        "approved_quantity_ignored": _approved_quantity_ignored,
    }


@router.post("/{wish_id}/convert-to-advance-report")
async def convert_wish_to_advance_report_endpoint(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Оформить как авансовый отчёт» (владелец, 2026-09-04, дословно): «человек
    может по ошибке заводить Авансовый через заявку ... надо дать возможность
    завести эту заявку как авансовый отчёт» — реальный случай: Любарец завела
    кабель как обычную заявку на закупку, хотя деньги уже потрачены и это
    авансовый отчёт.

    Логика переноса — в app.services.wish_advance_conversion (ПРАВИЛО №6: не
    вторая копия «заявка → закупка», а переиспользование
    _distribute_wish_to_purchases с wish.source == 'advance_report').

    Права: автор заявки, участник (WishMember), назначенный исполнитель/
    ответственный, согласующий из цепочки, либо менеджер+/SaaS — тот же круг,
    что уже может влиять на заявку (submit/stop), без отдельной галочки
    доступа (действие узкое и срочное, не отдельная фича с ролевой матрицей).
    """
    wish = await wishes_core._load_wish(wish_id, db)

    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    is_privileged = wishes_core._is_saas(current_user) or current_user.role in MANAGER_ROLES
    if not is_privileged:
        allowed = (
            wish.created_by == current_user.id
            or wish.assigned_to == current_user.id
            or wish.executor_id == current_user.id
            or await wishes_core._is_wish_member(wish_id, current_user.id, db)
        )
        if not allowed:
            from app.models.wish_approval import WishApproval
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            allowed = appr.scalar_one_or_none() is not None
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="Переоформить заявку в авансовый отчёт может автор, участник, "
                       "ответственный/согласующий заявки или менеджер+.",
            )

    from app.services.wish_advance_conversion import convert_wish_to_advance_report

    purchase = await convert_wish_to_advance_report(wish, db, current_user)
    cancelled = getattr(wish, "_advance_conversion_cancelled_purchases", [])
    await db.commit()

    wish = await wishes_core._load_wish(wish_id, db)
    return {
        "wish_id": wish.id,
        "purchase_id": purchase.id,
        "registry_number": purchase.registry_number,
        "purchase_method": purchase.purchase_method,
        "status": wish.status,
        "cancelled_purchases": cancelled,
    }


@router.post("/{wish_id}/approve-distribution")
async def approve_distribution(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """D-05/D-06: Atomic all-or-nothing распределение. Creates N purchases (status='wishes'),
    one per distinct resolved column key group, copies wish items to purchase_items,
    creates assignment chat rooms, links purchase.wish_id, then marks wish.status='converted'.

    Распределённая заявка уходит из «Заявок» в «Закупки» (status='converted').
    Rolls back entirely on any failure — zero purchases persist if any step fails.
    Returns 400 if wish is already distributed.
    """
    wish = await wishes_core._load_wish(wish_id, db)
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Заявка не входит в ваши организации")
    if not wishes_core._is_saas(current_user) and wish.status == "converted":
        raise HTTPException(status_code=400, detail="Заявка уже распределена")
    if not wishes_core._is_saas(current_user) and wish.status not in ("draft", "submitted", "approved"):
        raise HTTPException(status_code=400, detail=f"Нельзя распределить заявку в статусе {wish.status}")
    if current_user.role not in ADMIN_ROLES and wish.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Распределять заявку может админ или назначенный согласующий")
    if not wish.items:
        raise HTTPException(status_code=400, detail="Заявка пустая — нечего распределять")

    await wishes_core._ensure_no_pending_approvals(wish, db, current_user)

    try:
        ids = await wishes_core._distribute_wish_to_purchases(wish, db, current_user)
        wish.status = "converted"
        wish.approved_by = current_user.id
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании закупок — откат: {e}")

    return {
        "wish_id": wish.id,
        "purchase_ids": ids,
        "count": len(ids),
        "status": "converted",
        "warning": getattr(wish, "_convert_warning", None),
        "excess_warnings": getattr(wish, "_excess_warnings", []),
        "tz_excess_approvals": getattr(wish, "_tz_excess_approvals", []),
    }
