from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import (
    get_current_user, get_org_filter,
    OWNER_ROLES,
)
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_member import WishMember
from app.schemas.wishes import WishCreate, WishUpdate, WishOut
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.item_contractor import set_item_contractor
# _move_or_detach_planned_item/_deactivate_if_orphaned нужны только update_wish
# (ниже) — остальные хелперы автозаведения плана (_auto_assign_planned_items/
# _backfill_item_type_from_plan) переехали в app/services/wish_distribution.py
# вместе с _distribute_wish_to_purchases/_sync_purchase_from_wish, которые их
# используют (Правило №5, сессия 2026-09-06).
from app.services.plan_autoassign import (
    move_or_detach_planned_item as _move_or_detach_planned_item,
    deactivate_if_orphaned as _deactivate_if_orphaned,
)
from decimal import Decimal
# Перенос заявки в План закупок и обратно (Правило №5, сессия 2026-09-06,
# разрезание wishes.py по образцу purchases.py → purchase_ops.py) — вынесены в
# app/services/wish_distribution.py. Импорт здесь ОБЯЗАТЕЛЕН для re-export:
# app/routers/wish_approvals.py и app/services/wish_advance_conversion.py делают
# `from app.routers.wishes import _withdraw_wish_from_plan/_reset_approvals/
# _distribute_wish_to_purchases` — эти имена обязаны остаться доступны как
# атрибуты этого модуля. _collect_excess_warnings/_sync_purchase_from_wish нужны
# по тому же принципу — app/routers/wish_convert.py вызывает их через
# `wishes_core.<имя>` (см. докстринг wish_transitions.py про monkeypatch), а не
# прямым импортом из wish_distribution, чтобы весь путь «правки ядра видны
# роутерам-переходам» шёл одним способом.
from app.services.wish_distribution import (
    _withdraw_wish_from_plan,
    _reset_approvals,
    _distribute_wish_to_purchases,
    _collect_excess_warnings,
    _sync_purchase_from_wish,
)
# Вторая резка wishes.py (Правило №5, сессия 2026-09-08, по образцу первой —
# commit 89187a0 — и users.py → commit ca7b02c): сериализация (_enrich/
# _attach_purchase_matches/_wish_purchase_summaries_map) → app/services/
# wish_serializers.py; проверки доступа/членства и гейты (_is_wish_member/
# _ensure_*/_wish_locked_descr/_notify_pending_approvers/_wish_linked_purchases/
# CONTRACTED_STATUSES/_item_field/_is_meaningful_item/_as_date/_eff_date) →
# app/services/wish_access.py. Импорт здесь ОБЯЗАТЕЛЕН для re-export — те же
# причины и тот же приём, что у wish_distribution выше: потребители
# (wish_transitions.py/wish_convert.py/wish_export.py/wish_advance_conversion.py/
# wish_distribution.py/wish_lists.py/wish_items.py) зовут эти имена через
# `wishes_core.<имя>` или ленивым `from app.routers.wishes import <имя>`, а не
# напрямую из новых модулей.
from app.services.wish_serializers import (
    _enrich,
    _attach_purchase_matches,
    _wish_purchase_summaries_map,
)
from app.services.wish_access import (
    CONTRACTED_STATUSES,
    _wish_linked_purchases,
    _is_wish_member,
    _ensure_no_pending_approvals,
    _as_date,
    _eff_date,
    _ensure_needed_dates,
    _ensure_feo_categories_assigned,
    _item_field,
    _is_meaningful_item,
    _wish_locked_descr,
    _notify_pending_approvers,
)


def _is_saas(user: User) -> bool:
    """SaaS-роли (superadmin/account_owner) — обходят любые status-guard'ы."""
    return user.role in OWNER_ROLES


router = APIRouter(prefix="/api/wishes", tags=["wishes"])

# Phase 31: fields tracked for diff-highlighting (D-05..D-09)
# estimated_price is the wish amount proxy (Wish has no total_price column)
WISH_TRACKED_FIELDS: set[str] = {
    "title", "description", "status", "subsidy_id", "estimated_price",
}


async def _load_wish(wish_id: int, db: AsyncSession) -> Wish:
    """Load wish with all relationships."""
    result = await db.execute(
        select(Wish)
        .options(
            selectinload(Wish.creator),
            selectinload(Wish.approver),
            selectinload(Wish.assignee),
            selectinload(Wish.subsidy),
            selectinload(Wish.event),
            selectinload(Wish.executor),
            selectinload(Wish.items),
            selectinload(Wish.stopped_by_user),
            selectinload(Wish.contractor),
            selectinload(Wish.rejected_by_user),
        )
        .where(Wish.id == wish_id)
    )
    wish = result.scalar_one_or_none()
    if wish is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return wish


@router.get("/{wish_id}", response_model=WishOut)
async def get_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get single wish with items. Creator, assignee, or manager/admin of same org."""
    wish = await _load_wish(wish_id, db)
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        # Check if current user is a participant (wish member)
        member_res = await db.execute(
            select(WishMember).where(
                WishMember.wish_id == wish_id,
                WishMember.user_id == current_user.id,
            )
        )
        if member_res.scalar_one_or_none() is None:
            # …или согласующий из цепочки (вкладка «На согласование мне»)
            from app.models.wish_approval import WishApproval
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            if appr.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    enriched = _enrich(wish)
    mnames = (await db.execute(
        select(User.full_name, User.username)
        .join(WishMember, WishMember.user_id == User.id)
        .where(WishMember.wish_id == wish_id)
    )).all()
    enriched.member_names = [fn or un for fn, un in mnames]

    from app.models.wish_approval import WishApproval
    anames = (await db.execute(
        select(User.full_name, User.username)
        .join(WishApproval, WishApproval.user_id == User.id)
        .where(WishApproval.wish_id == wish_id)
        .order_by(WishApproval.order_num)
    )).all()
    enriched.approver_names = [fn or un for fn, un in anames]
    enriched.purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.wish_id == wish_id).order_by(Purchase.id)
    )).scalars().all()
    # Пункт 4 (владелец, 2026-08-13): номер/статус/сумма для меню «Перейти в закупку».
    enriched.purchases = (await _wish_purchase_summaries_map([wish_id], db)).get(wish_id, [])
    # items уже загружены selectinload'ом в _load_wish — суммируем в памяти,
    # без доп. запроса (см. items_total в list_wishes для батч-версии).
    enriched.items_total = sum((it.total_price or Decimal("0")) for it in (wish.items or [])) or Decimal("0")

    # W1: contracted_locked — есть ли закупка в статусе Договор+
    # Правка владельца (2026-08-18): сообщение о блокировке должно называть
    # конкретную закупку и её реальную стадию, а не всегда «Договор» — см.
    # _wish_locked_descr. contracted_locked_reason — готовая строка для баннера
    # на фронте (frontend/src/views/WishesView.vue), None если не заблокировано.
    _locked_descr = await _wish_locked_descr(wish_id, db)
    enriched.contracted_locked = bool(_locked_descr)
    enriched.contracted_locked_reason = _locked_descr

    # W-diff: «двойник» каждой позиции в закупке — только карточка, не список
    await _attach_purchase_matches(wish, enriched, db)

    # Phase 31: unseen_fields for single wish GET (D-05..D-09)
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        _unseen_single = await _get_unseen_map(db, 'wish', [wish_id], current_user.id)
        _unseen_fields = _unseen_single.get(wish_id, [])
        enriched.unseen_fields = _unseen_fields
        enriched.unseen_changes_count = len(_unseen_fields)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen wish single failed: %s", _exc)

    return enriched


@router.post("/{wish_id}/copy", response_model=WishOut, status_code=201)
async def copy_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Копирование заявки (владелец, 2026-08-13): «при переделывании больших
    заявок не приходилось делать двойную работу — могут быть однотипные заявки
    с небольшим расхождением». Создаёт НОВУЮ заявку-черновик.

    Копируется ТОЛЬКО то, что описывает сам товар — item_name/item_type/
    product_id/quantity/unit/country_origin по каждой позиции — и заголовок
    исходной заявки с пометкой «(копия)».

    НЕ копируется (владелец прямо просил дозаполнять и проверять, «куда что
    идёт»): категории ФЭО у позиций (feo_category_id), привязка к плановым
    позициям (feo_planned_item_id/match_confirmed), НДС-ставка и over_plan,
    цены (unit_price/total_price), даты потребности (needed_date), исполнитель,
    согласующие, статус, привязки к закупкам, вложения. Сама новая заявка
    всегда создаётся в статусе 'draft' (как в create_wish), автор — текущий
    пользователь.

    org_id и subsidy_id копируются «как есть» — это рамка (организация и
    бюджет), в которой человек работает, а не «куда что идёт» внутри неё.

    Права: та же проверка видимости, что в GET /{wish_id} (без доп. ролевых
    ограничений сверх неё — копировать может любой, кто видит заявку).
    """
    wish = await _load_wish(wish_id, db)
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        member_res = await db.execute(
            select(WishMember).where(
                WishMember.wish_id == wish_id,
                WishMember.user_id == current_user.id,
            )
        )
        if member_res.scalar_one_or_none() is None:
            from app.models.wish_approval import WishApproval
            appr = await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )
            if appr.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    from app.schemas.wishes import _clamp_title
    new_title = _clamp_title(f"{wish.title} (копия)")

    new_wish = Wish(
        org_id=wish.org_id,
        title=new_title,
        subsidy_id=wish.subsidy_id,
        status="draft",
        created_by=current_user.id,
    )
    db.add(new_wish)
    await db.flush()

    for it in (wish.items or []):
        db.add(WishItem(
            wish_id=new_wish.id,
            product_id=it.product_id,
            item_name=it.item_name,
            item_type=it.item_type,
            quantity=it.quantity,
            unit=it.unit,
            country_origin=it.country_origin,
        ))

    await db.commit()
    new_wish = await _load_wish(new_wish.id, db)
    enriched = _enrich(new_wish)
    enriched.items_total = sum((it.total_price or Decimal("0")) for it in (new_wish.items or [])) or Decimal("0")
    return enriched


@router.post("/", response_model=WishOut, status_code=201)
async def create_wish(
    body: WishCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new wish (all roles)."""
    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, body.subsidy_id)

    org_ids = get_org_filter(current_user)
    org_id = org_ids[0] if org_ids else current_user.org_id

    wish = Wish(
        org_id=org_id,
        title=body.title,
        category=body.category,
        description=body.description,
        quantity=body.quantity,
        unit=body.unit,
        estimated_price=body.estimated_price,
        link=body.link,
        priority=body.priority,
        desired_date=body.desired_date,
        justification=body.justification,
        subsidy_id=body.subsidy_id,
        feo_category_id=body.feo_category_id,
        event_id=body.event_id,
        assigned_to=body.assigned_to,
        status="draft",
        created_by=current_user.id,
        feo_per_item=body.feo_per_item,
        vat_mode=body.vat_mode or 'uniform',
    )
    db.add(wish)
    await db.flush()

    # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
    if body.contractor_id is not None:
        from app.models.contractor import Contractor as _Contractor
        _create_contractor = await db.get(_Contractor, body.contractor_id)
        if _create_contractor:
            set_item_contractor(wish, contractor=_create_contractor, name=body.contractor_name)
        else:
            set_item_contractor(wish, contractor_id=body.contractor_id)
    elif body.contractor_name:
        set_item_contractor(wish, name=body.contractor_name)

    if body.items:
        for item_data in body.items:
            if not _is_meaningful_item(item_data):
                continue  # пустая строка-заготовка — в БД не пишем
            wi = WishItem(
                wish_id=wish.id,
                product_id=item_data.get('product_id'),
                item_name=item_data.get('item_name', ''),
                item_type=item_data.get('item_type', 'товар'),
                quantity=item_data.get('quantity', 1),
                unit=item_data.get('unit', 'шт'),
                unit_price=item_data.get('unit_price', 0),
                total_price=item_data.get('total_price', 0),
                country_origin=item_data.get('country_origin', 'РФ'),
                feo_category_id=item_data.get('feo_category_id'),  # B9
                feo_planned_item_id=item_data.get('feo_planned_item_id'),  # привязка к плановой позиции плана закупок
                over_plan=item_data.get('over_plan', False),
                needed_date=_as_date(item_data.get('needed_date')),  # W2
                vat_rate=item_data.get('vat_rate'),
            )
            db.add(wi)
        await db.flush()

    await db.commit()
    wish = await _load_wish(wish.id, db)
    return _enrich(wish)


@router.put("/{wish_id}", response_model=WishOut)
async def update_wish(
    wish_id: int,
    body: WishUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a wish.
    Draft/rejected: full edit.
    Submitted/approved/converted: edit allowed (for all non-SaaS if not contracted-locked),
    then resets approval chain and re-notifies approvers.
    B3: contracted-locked wishes (purchase in Договор+) are read-only.
    """
    wish = await _load_wish(wish_id, db)

    if not _is_saas(current_user) and wish.created_by != current_user.id:
        # Участники заявки (WishMember) тоже могут её редактировать
        if not await _is_wish_member(wish_id, current_user.id, db):
            # Дефект 1 (владелец, 2026-08-20): согласующий из цепочки WishApproval
            # сюда попадать не должен вовсе — фронт больше не зовёт PUT для него,
            # ФЭО он правит через PATCH /execution. Но если это всё-таки произошло
            # (старый фронт/прямой запрос) — подсказать конкретно, а не молчать
            # общей фразой (feedback_explain_blocking_reason).
            from app.models.wish_approval import WishApproval
            is_chain_approver = (await db.execute(
                select(WishApproval.id).where(
                    WishApproval.wish_id == wish_id,
                    WishApproval.user_id == current_user.id,
                ).limit(1)
            )).scalar_one_or_none() is not None
            detail = "Редактировать заявку может автор или участник заявки"
            if is_chain_approver:
                detail += ". Состав заявки меняет автор — как согласующий, правьте категорию ФЭО прямо в форме (сохраняется автоматически), решение отправляйте кнопкой «Согласовать»/«Отклонить»"
            raise HTTPException(status_code=403, detail=detail)

    # W2: contracted-lock replaces old draft-only gate
    if not _is_saas(current_user):
        _locked_descr = await _wish_locked_descr(wish.id, db)
        if _locked_descr:
            raise HTTPException(
                status_code=409,
                detail=f"Заявка привязана к закупке — {_locked_descr}. Редактирование запрещено",
            )
        # SaaS is always allowed; for others allow draft/rejected AND submitted/approved/converted

    # Владелец (2026-08-13): «После согласования заявку править нельзя, только в
    # закупке» — на статусе 'converted' заявка уже в Плане закупок, единственный
    # источник правды для позиций — сама закупка (PurchaseItem), а не WishItem.
    # Раньше правка позиций тут ЧАСТИЧНО синхронизировалась в закупку
    # (_sync_wish_items_to_purchases копировал название/кол-во/цену, но НЕ
    # категорию ФЭО) — данные расходились: в заявке позиция в одной категории,
    # в закупке в другой. Теперь правка позиций конвертированной заявки
    # отклоняется явно; несущественные поля заявки (приоритет, срок и т.п.)
    # по-прежнему редактируемы — блокируются только `items`.
    if not _is_saas(current_user) and wish.status == "converted" and body.items is not None:
        _linked_purchases = await _wish_linked_purchases(wish_id, db)
        _purchase_nums = ", ".join(
            f"№{p.purchase_number or p.id}" for p in _linked_purchases
        ) or "не найдена"
        raise HTTPException(
            status_code=409,
            detail=(
                "Заявка уже в плане закупок — изменения вносятся в закупке "
                f"({_purchase_nums})"
            ),
        )

    # Capture old status BEFORE mutation
    old_status = wish.status

    # Phase 31: capture old values for diff-tracking BEFORE any mutation (D-05..D-09)
    _old_wish_values = {f: getattr(wish, f, None) for f in WISH_TRACKED_FIELDS}

    # A1 fix: снимок существенных скалярных полей ДО мутации (Дыра 2)
    # Жалоба владельца 2026-08-13: привязка позиции к категории/плановой позиции
    # ФЭО — это маршрутизация по бюджету, а не смена предмета закупки. Согласующий
    # привязывал позицию к ФЭО и нажимал «Сохранить» уже ПОСЛЕ того, как согласовал —
    # feo_category_id в этом наборе стирал его же согласование («повторное
    # согласование» без реального изменения того, ЧТО закупается). За перерасход
    # отвечают отдельные гейты (assert_no_unapproved_excess / потолок субсидии),
    # поэтому feo_category_id сюда не входит.
    _APPROVAL_SENSITIVE_FIELDS: set[str] = {
        "title", "subsidy_id", "estimated_price",
        "quantity", "unit", "justification",
    }
    _old_sensitive = {f: getattr(wish, f, None) for f in _APPROVAL_SENSITIVE_FIELDS}

    # A1 fix: снимок позиций ДО мутации для точного сравнения (Дыра 1)
    # feo_category_id намеренно НЕ входит в кортеж сравнения — см. комментарий
    # у _APPROVAL_SENSITIVE_FIELDS выше (жалоба 2026-08-13).
    _old_items = {
        wi.id: (
            str(wi.item_name or ''),
            str(wi.unit or ''),
            float(wi.quantity or 0),
            float(wi.unit_price or 0),
            float(wi.total_price or 0),
        )
        for wi in (wish.items or [])
    }

    if body.subsidy_id is not None:
        from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
        await assert_subsidy_approved_for_binding(db, body.subsidy_id)

    update_data = body.model_dump(exclude_none=True, exclude={'items'})
    for field, value in update_data.items():
        setattr(wish, field, value)

    # Контрагент — необязательное поле (владелец, 2026-08-17), а «необязательное»
    # значит, что его можно и СНЯТЬ, не только поставить. Общий model_dump(exclude_none=True)
    # выше НЕ трогаем скопом: на нём годами держится поведение остальных Optional-полей
    # формы заявки («ключ отсутствует/null» = «не менять», привычно для частичных PUT —
    # например автосохранение одного поля не должно стирать все остальные) — массовая
    # замена на exclude_unset рисковала бы молча обнулить что-то, что никто не просил
    # чистить. Поэтому точечно, только для contractor_id/contractor_name: используем
    # body.model_fields_set — Pydantic v2 кладёт туда имя поля, если СООТВЕТСТВУЮЩИЙ КЛЮЧ
    # реально присутствовал в JSON тела запроса (даже если значение — null), и не кладёт,
    # если ключ отсутствовал вовсе. Так «прислали null» (пользователь снял контрагента)
    # отличается от «ключ не прислали» (например, автосохранение другого поля заявки —
    # значение контрагента трогать не должно).
    # ПРАВИЛО №6 (группа D5): единственный писатель контрагента — item_contractor.
    # set_item_contractor (FK — источник истины, текст обнуляется, когда FK задан).
    # Partial-update нюанс (см. комментарий выше про model_fields_set): поле,
    # которое НЕ пришло ключом в этом запросе, не трогаем — только contractor_id
    # принудительно обнуляет текст ВСЕГДА, когда сам он устанавливается ненулевым
    # (инвариант «текст только при contractor_id IS NULL» не может ждать, пока
    # придёт ещё и contractor_name отдельным запросом).
    if 'contractor_id' in body.model_fields_set:
        if body.contractor_id is not None:
            from app.models.contractor import Contractor as _Contractor
            _new_contractor = await db.get(_Contractor, body.contractor_id)
            if _new_contractor:
                set_item_contractor(
                    wish, contractor=_new_contractor,
                    name=(body.contractor_name if 'contractor_name' in body.model_fields_set else None),
                )
            else:
                # Контрагент с таким id не найден — ставим голый FK, текст всё равно NULL.
                set_item_contractor(wish, contractor_id=body.contractor_id)
        else:
            # Снятие контрагента: FK → NULL; contractor_name трогаем ТОЛЬКО если он
            # реально пришёл в этом же запросе, иначе не вносим шум в чужое поле.
            wish.contractor_id = None
            if 'contractor_name' in body.model_fields_set:
                wish.contractor_name = body.contractor_name
    elif 'contractor_name' in body.model_fields_set:
        if wish.contractor_id:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "update_wish: contractor_name=%r проигнорирован — у заявки id=%s уже задан "
                "contractor_id=%s (FK остаётся источником истины)",
                body.contractor_name, wish.id, wish.contractor_id,
            )
        else:
            wish.contractor_name = body.contractor_name

    # Плановые позиции следуют за сменой категории (владелец, 2026-08-17):
    # предупреждения, когда привязку пришлось снять вместо переезда (см. ветку
    # non-draft ниже) — возвращаются в ответе, не проглатываются молча.
    _plan_transfer_warnings: list[str] = []

    if body.items is not None:
        if old_status == "draft":
            # Draft: delete+recreate (original behaviour)
            await db.execute(delete(WishItem).where(WishItem.wish_id == wish.id))
            for item_data in body.items:
                if not _is_meaningful_item(item_data):
                    continue  # пустая строка-заготовка — в БД не пишем
                wi = WishItem(
                    wish_id=wish.id,
                    product_id=item_data.get('product_id'),
                    item_name=item_data.get('item_name', ''),
                    item_type=item_data.get('item_type', 'товар'),
                    quantity=item_data.get('quantity', 1),
                    unit=item_data.get('unit', 'шт'),
                    unit_price=item_data.get('unit_price', 0),
                    total_price=item_data.get('total_price', 0),
                    country_origin=item_data.get('country_origin', 'РФ'),
                    feo_category_id=item_data.get('feo_category_id'),  # B9
                    feo_planned_item_id=item_data.get('feo_planned_item_id'),  # план закупок ФЭО
                    over_plan=item_data.get('over_plan', False),
                    needed_date=_as_date(item_data.get('needed_date')),  # W2
                    vat_rate=item_data.get('vat_rate'),
                )
                db.add(wi)
            await db.flush()
        else:
            # Non-draft (submitted/approved/converted/rejected): update existing items in-place by id,
            # and DELETE items that dropped out of the payload (owner removes a duplicate/empty row →
            # it must actually disappear from the DB, not just from the UI). Add is still NOT
            # supported here — out of scope, unchanged from prior behaviour (items without a
            # matching id are silently skipped).
            existing_items = {wi.id: wi for wi in wish.items}
            payload_ids: set[int] = set()
            for item_data in body.items:
                item_id = item_data.get('id') if isinstance(item_data, dict) else getattr(item_data, 'id', None)
                if item_id:
                    payload_ids.add(item_id)
                wi = existing_items.get(item_id) if item_id else None
                if wi is None:
                    continue
                if 'item_name' in item_data:
                    wi.item_name = item_data['item_name']
                if 'unit_price' in item_data:
                    wi.unit_price = item_data['unit_price']
                if 'quantity' in item_data:
                    wi.quantity = item_data['quantity']
                if 'unit' in item_data:
                    wi.unit = item_data['unit']
                if 'total_price' in item_data:
                    wi.total_price = item_data['total_price']
                elif 'unit_price' in item_data or 'quantity' in item_data:
                    wi.total_price = (wi.unit_price or 0) * (wi.quantity or 0)
                _wi_cat_changing = (
                    'feo_category_id' in item_data
                    and item_data['feo_category_id'] != wi.feo_category_id
                )
                if 'feo_category_id' in item_data:
                    wi.feo_category_id = item_data['feo_category_id']
                if 'feo_planned_item_id' in item_data:
                    # Явный выбор плановой позиции с фронта (в т.ч. её очистка) —
                    # доверяем как есть, автоперенос ниже не запускаем.
                    wi.feo_planned_item_id = item_data['feo_planned_item_id']
                elif _wi_cat_changing and wi.feo_planned_item_id is not None:
                    # Плановые позиции следуют за сменой категории (владелец,
                    # 2026-08-17): payload сменил feo_category_id позиции, но не
                    # прислал новый feo_planned_item_id явно — старая привязка
                    # осталась указывать на прежнюю категорию. Если позиция —
                    # единственный владелец своей плановой строки, строка
                    # переезжает вместе с ней; если план общий с другими
                    # закупками/заявками — привязка снимается и предупреждение
                    # копится в _plan_transfer_warnings (возвращается в ответе).
                    if wi.feo_category_id is not None:
                        _w = await _move_or_detach_planned_item(db, wi, wi.feo_category_id)
                        if _w:
                            _plan_transfer_warnings.append(_w)
                    else:
                        # Категория очищена целиком — плановой позиции
                        # переезжать некуда, привязка просто снимается.
                        from app.models.feo_planned_item import FeoPlannedItem as _FPI2
                        from app.services.plan_autoassign import deactivate_if_orphaned as _deactivate_if_orphaned
                        _old_fpi2 = await db.get(_FPI2, wi.feo_planned_item_id)
                        wi.feo_planned_item_id = None
                        wi.over_plan = False
                        await _deactivate_if_orphaned(db, _old_fpi2)
                if 'over_plan' in item_data:
                    wi.over_plan = item_data['over_plan']
                if 'needed_date' in item_data:
                    wi.needed_date = _as_date(item_data['needed_date'])
                if 'vat_rate' in item_data:
                    wi.vat_rate = item_data['vat_rate']

                # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): правка
                # заявки — тот же обход, что и _sync_wish_items_to_purchases выше,
                # проверяем ЗДЕСЬ (на WishItem), т.к. именно отсюда цена/кол-во
                # затем копируются в PurchaseItem. over_plan=true пропускаем —
                # сознательно сверх плана.
                if ('unit_price' in item_data or 'quantity' in item_data) and not getattr(wi, 'over_plan', False):
                    await assert_tz_not_over_plan(
                        db,
                        feo_planned_item_id=wi.feo_planned_item_id,
                        feo_category_id=wi.feo_category_id,
                        quantity=wi.quantity,
                        unit_price=wi.unit_price,
                        total_price=wi.total_price,
                        item_name=wi.item_name,
                    )

            # Позиции, которых больше нет в payload, — удаляем физически.
            ids_to_delete = set(existing_items.keys()) - payload_ids
            if ids_to_delete:
                _locked_descr = await _wish_locked_descr(wish.id, db)
                if _locked_descr:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Нельзя удалить позицию заявки: закупка {_locked_descr} уже на этапе "
                            "договора. Отмените закупку вручную в реестре закупок, либо не удаляйте позицию."
                        ),
                    )
                # Сироты в закупке: PurchaseItem с FK на удаляемую позицию (ondelete=SET NULL
                # только обнулит связь, но НЕ уберёт строку) — чистим явно, но только пока
                # закупка ещё не ушла дальше «Плана закупок» (иначе выше сработал бы гейт).
                _linked_purchases = await _wish_linked_purchases(wish.id, db)
                _early_stage_purchase_ids = {
                    p.id for p in _linked_purchases if p.status in ("plan_schedule", "wishes")
                }
                if _early_stage_purchase_ids:
                    await db.execute(
                        delete(PurchaseItem).where(
                            PurchaseItem.wish_item_id.in_(ids_to_delete),
                            PurchaseItem.purchase_id.in_(_early_stage_purchase_ids),
                        )
                    )
                # Удаляем через саму relationship-коллекцию (cascade="all, delete-orphan" на
                # Wish.items), а не Core delete(): так wish.items остаётся синхронной в памяти
                # для последующего сравнения _old_items/_new_items (сброс согласования ниже).
                for _del_id in ids_to_delete:
                    wish.items.remove(existing_items[_del_id])

            await db.flush()

    # W2: re-approval trigger for submitted/approved/converted wishes
    # A1 fix: сбрасываем согласование ТОЛЬКО при изменении существенных полей.
    # Существенные поля = те, что определяют предмет закупки и требуют повторного
    # одобрения согласующих. Несущественные (priority, desired_date, event_id,
    # assigned_to, executor_id, execution_deadline, link) НЕ сбрасывают цепочку.
    if old_status in ("submitted", "approved", "converted"):
        # Дыра 2 исправлена: используем _old_sensitive (снят ДО мутации) вместо
        # _old_wish_values (который содержит только WISH_TRACKED_FIELDS, без quantity/unit/justification).
        _sensitive_changed = any(
            str(_old_sensitive.get(f)) != str(getattr(wish, f, None))
            for f in _APPROVAL_SENSITIVE_FIELDS
        )
        # Дыра 1 исправлена: сравниваем реальное содержимое позиций до/после.
        # Фронт всегда шлёт body.items, поэтому «items is not None» — недостаточное условие.
        # feo_category_id намеренно НЕ входит — привязка к ФЭО/плановой позиции не
        # меняет предмет закупки, это маршрутизация по бюджету (жалоба 2026-08-13).
        _new_items = {
            wi.id: (
                str(wi.item_name or ''),
                str(wi.unit or ''),
                float(wi.quantity or 0),
                float(wi.unit_price or 0),
                float(wi.total_price or 0),
            )
            for wi in (wish.items or [])
        }
        _items_changed = (_old_items != _new_items)

        if _sensitive_changed or _items_changed:
            # Проверяем наличие согласующих ДО смены статуса (старые заявки могли быть одобрены без цепочки)
            from app.models.wish_approval import WishApproval as _WA
            _approver_count = (await db.execute(
                select(func.count()).select_from(_WA).where(_WA.wish_id == wish.id)
            )).scalar() or 0
            if _approver_count == 0:
                raise HTTPException(
                    status_code=409,
                    detail="Заявка уйдёт на повторное согласование, но согласующие не выбраны — "
                           "добавьте хотя бы одного согласующего в разделе «Согласующие».",
                )
            # W2: проверяем плановые даты перед сбросом в submitted (авансовые пропускаем)
            if getattr(wish, 'source', None) != 'advance_report':
                await _ensure_needed_dates(wish, db, wish.items or [], context="submit")
            wish.status = "submitted"
            # Повторная отправка на согласование после правки — старое
            # отклонение больше не актуально (владелец, 2026-08-19).
            wish.rejected_by = None
            wish.rejected_at = None
            wish.rejection_reason = None
            await db.flush()
            await _reset_approvals(wish.id, db)
            # Заявка уходит на ПОВТОРНОЕ согласование — позиции могли измениться,
            # закупка в Плане закупок больше не актуальна, убираем её оттуда. Если что-то
            # уже в работе/договоре — откат запрещаем явно (не молчим, коммита ещё не было).
            await _withdraw_wish_from_plan(wish.id, db, action_text="вернуть на повторное согласование")
            requester_name = getattr(current_user, 'full_name', None) or current_user.username
            await _notify_pending_approvers(wish, db, requester_name)

    await db.commit()

    # Phase 31: record EntityChange for each TRACKED_FIELD that changed (D-05..D-09)
    # Only record changes made by OTHER users (D-07: own changes are not highlighted)
    try:
        from app.models.entity_change import EntityChange as _EC
        _changes = []
        for _fname in WISH_TRACKED_FIELDS:
            _old = _old_wish_values.get(_fname)
            _new = getattr(wish, _fname, None)
            _old_s = str(_old) if _old is not None else None
            _new_s = str(_new) if _new is not None else None
            if _old_s != _new_s:
                _changes.append(_EC(
                    entity_type='wish',
                    entity_id=wish.id,
                    field_name=_fname,
                    old_value=_old_s,
                    new_value=_new_s,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        if _changes:
            for _c in _changes:
                db.add(_c)
            await db.commit()
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed for wish: %s", _exc)

    wish = await _load_wish(wish_id, db)
    out = _enrich(wish)
    out.plan_transfer_warnings = _plan_transfer_warnings
    return out


@router.delete("/{wish_id}", status_code=204)
async def delete_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a draft wish (creator only)."""
    wish = await _load_wish(wish_id, db)

    if not _is_saas(current_user) and wish.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Только автор может удалить заявку")
    if not _is_saas(current_user) and wish.status != "draft":
        raise HTTPException(status_code=400, detail="Можно удалить только черновик")

    # Заявку удаляют — purchases.wish_id обнулится каскадом (ON DELETE SET NULL),
    # закупка осиротеет в плане. Плановые (plan_schedule) убираем из плана заранее;
    # если что-то уже в работе/договоре — удаление блокируем явно (владелец, 2026-08-07).
    await _withdraw_wish_from_plan(wish.id, db, action_text="удалить")

    await db.delete(wish)
    await db.commit()
