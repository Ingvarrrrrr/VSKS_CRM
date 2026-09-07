"""Переходы статуса заявки: submit/approve/reject/force-status/stop и правка
исполнителя+срока (PATCH /execution).

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-06,
разрезание wishes.py по образцу purchases.py → purchase_ops.py/purchase_*.py)
БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

Хелперы ядра (_load_wish/_is_saas/_wish_linked_purchases/_wish_locked_descr/
_notify_pending_approvers/_ensure_no_pending_approvals/_enrich/_eff_date/
_ensure_needed_dates/_is_wish_member) вызываются через `wishes_core.<имя>` —
не `from app.routers.wishes import <имя>` — чтобы monkeypatch на ядре (тесты,
будущие правки) продолжал действовать: прямой импорт связал бы имя на момент
импорта этого модуля, а не на момент вызова.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, MANAGER_ROLES
from app.auth.permissions import has_org_key
from app.models.user import User
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.chat_message import ChatMessage
from app.routers.purchase_members import _create_assignment_chat_room
from app.schemas.wishes import WishOut, WishReject, WishExecutionPatch, WishStatusForce, WishStop
from app.services.plan_autoassign import (
    move_or_detach_planned_item as _move_or_detach_planned_item,
    deactivate_if_orphaned as _deactivate_if_orphaned,
)
from app.routers import wishes as wishes_core

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


@router.post("/{wish_id}/stop", response_model=WishOut)
async def stop_wish(
    wish_id: int,
    body: WishStop,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Остановка заявки (владелец, 2026-08-13): «Останавливать могут все» — доступно
    ЛЮБОМУ пользователю, видящему заявку, без ролевых ограничений (та же проверка
    видимости, что и GET /{wish_id}).

    Заявка НЕ удаляется — проставляются stopped_at/stopped_by/stopped_reason,
    и она исчезает из плана закупок (см. app/services/feo_plan.py — агрегаты
    исключают Purchase.stopped_at IS NOT NULL / Wish.stopped_at IS NOT NULL).

    Останавливаются все привязанные закупки, ещё НЕ дошедшие до договора:
    обычные — раньше 'contracted' по STATUS_ORDER; рамочные (purchase_contract_type
    в FRAMEWORK_TYPES) — раньше 'ordered' (у рамочного договора отдельная граница,
    т.к. сам договор — отдельная сущность, не по каждой закупке). Если остановились
    не все закупки заявки — wish.stopped_partial=True.

    Исполнителю (Wish.executor_id) уходит уведомление. Обратной операции
    (возобновление) нет — владелец её не просил.
    """
    from app.routers.purchases import STATUS_ORDER
    from app.routers.purchase_budget import FRAMEWORK_TYPES

    wish = await wishes_core._load_wish(wish_id, db)

    # Видимость — та же проверка, что и в GET /{wish_id} (владелец: «Останавливать
    # могут все» = любой, кто вообще видит заявку, без доп. ролевых ограничений).
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    if current_user.role == 'employee' and wish.created_by != current_user.id and wish.assigned_to != current_user.id:
        member_res = await db.execute(
            select(wishes_core.WishMember).where(
                wishes_core.WishMember.wish_id == wish_id,
                wishes_core.WishMember.user_id == current_user.id,
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

    if wish.stopped_at is not None:
        raise HTTPException(status_code=409, detail="Заявка уже остановлена")

    from datetime import timezone as _timezone
    now = datetime.now(_timezone.utc)
    wish.stopped_at = now
    wish.stopped_by = current_user.id
    wish.stopped_reason = (body.reason if body else None) or None

    purchases = await wishes_core._wish_linked_purchases(wish_id, db)
    stopped_count = 0
    for p in purchases:
        if p.stopped_at is not None:
            continue  # уже остановлена ранее (другой заявкой/повторный вызов)
        is_framework = p.purchase_contract_type in FRAMEWORK_TYPES
        threshold_status = "ordered" if is_framework else "contracted"
        cur_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
        threshold_idx = STATUS_ORDER.index(threshold_status)
        if cur_idx < threshold_idx:
            p.stopped_at = now
            p.stopped_by = current_user.id
            p.stopped_wish_id = wish.id
            stopped_count += 1

    total = len(purchases)
    partial = total > 0 and stopped_count < total
    wish.stopped_partial = partial

    await db.commit()

    try:
        from app.notifications import notify_wish_stopped
        wish_for_notify = await wishes_core._load_wish(wish_id, db)
        executor = getattr(wish_for_notify, 'executor', None)
        if executor and executor.id != current_user.id:
            stopper_name = getattr(current_user, 'full_name', None) or current_user.username
            await notify_wish_stopped(wish_for_notify, executor, stopper_name, partial)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("notify wish stopped failed: %s", _exc)

    wish = await wishes_core._load_wish(wish_id, db)
    return wishes_core._enrich(wish)


@router.post("/{wish_id}/submit", response_model=WishOut)
async def submit_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft wish for approval (creator only, draft/rejected -> submitted)."""
    wish = await wishes_core._load_wish(wish_id, db)

    if not wishes_core._is_saas(current_user) and wish.created_by != current_user.id:
        # Участники заявки (WishMember) тоже могут отправить её на согласование
        if not await wishes_core._is_wish_member(wish_id, current_user.id, db):
            raise HTTPException(status_code=403, detail="Отправить на согласование может автор или участник заявки")
    if not wishes_core._is_saas(current_user) and wish.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'draft' или 'rejected'")

    # Проверяем наличие согласующих: нельзя отправить заявку неизвестно кому
    from app.models.wish_approval import WishApproval as _WA_submit
    _approver_count = (await db.execute(
        select(func.count()).select_from(_WA_submit).where(_WA_submit.wish_id == wish_id)
    )).scalar() or 0
    if _approver_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Нельзя отправить на согласование: не выбраны согласующие. "
                   "Добавьте хотя бы одного согласующего в разделе «Согласующие».",
        )

    # W2: проверяем плановые даты (авансовые пропускаем) — ДО смены статуса
    if getattr(wish, 'source', None) != 'advance_report':
        await wishes_core._ensure_needed_dates(wish, db, wish.items or [], context="submit")

    _was_rejected = wish.status == "rejected"
    wish.status = "submitted"
    # Повторная отправка на согласование (в т.ч. из 'rejected') — старое
    # отклонение больше не актуально, владелец просил не оставлять его висеть
    # (см. Wish.rejected_by докстринг в models/wish.py).
    wish.rejected_by = None
    wish.rejected_at = None
    wish.rejection_reason = None
    await db.flush()
    if _was_rejected:
        # Без keep_user_id — сброс ПОЛНЫЙ. Иначе строка отклонившего согласующего
        # (см. _reset_approvals в decide()) осталась бы 'rejected' навсегда: при
        # повторном дохождении очереди до неё sequential-гейт увидел бы «уже
        # принято решение» и заблокировал бы согласование заново.
        await wishes_core._reset_approvals(wish.id, db)

    # Уведомить согласующих из цепочки (вынесено в _notify_pending_approvers)
    requester_name = current_user.full_name or current_user.username
    await wishes_core._notify_pending_approvers(wish, db, requester_name)

    # Notify approver
    if wish.assigned_to and wish.assigned_to != current_user.id:
        org_id = getattr(current_user, 'org_id', None) or wish.org_id
        room_id = await _create_assignment_chat_room(
            db, current_user.id, wish.assigned_to,
            org_id,
            f"Заявка №{wish.id}: {wish.title or 'без названия'}",
        )
        db.add(ChatMessage(
            room_id=room_id,
            sender_id=current_user.id,
            content=f"📋 Заявка отправлена на согласование: {wish.title or '(без названия)'}",
        ))
        await db.flush()

    await db.commit()
    wish = await wishes_core._load_wish(wish_id, db)
    return wishes_core._enrich(wish)


@router.post("/{wish_id}/approve", response_model=WishOut)
async def approve_wish(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a submitted wish (manager+ roles OR assigned approver, submitted -> approved)."""
    wish = await wishes_core._load_wish(wish_id, db)

    if not wishes_core._is_saas(current_user) and wish.status != "submitted":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'submitted'")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    if not wishes_core._is_saas(current_user) and current_user.role not in MANAGER_ROLES and wish.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Одобрить заявку может менеджер+ или назначенный согласующий")

    # W3: менеджер/SaaS может одобрить чужие pending без блокировки (allow_override=True)
    await wishes_core._ensure_no_pending_approvals(wish, db, current_user, allow_override=True)

    wish.status = "approved"
    wish.approved_by = current_user.id
    # Согласованная заявка автоматически уходит в «План закупок» ОДНОЙ закупкой
    # (быстрое одобрение — без разбиения по категориям), сумма попадает в план ФЭО.
    created_ids: list[int] = []
    if wish.items:
        created_ids = await wishes_core._distribute_wish_to_purchases(wish, db, current_user, split=False)
        wish.status = "converted"
    warning = getattr(wish, "_convert_warning", None)
    excess_warnings = getattr(wish, "_excess_warnings", [])
    tz_excess_approvals = getattr(wish, "_tz_excess_approvals", [])
    purchase_sync = getattr(wish, "_purchase_sync", None)
    await db.commit()
    await db.refresh(wish)
    wish = await wishes_core._load_wish(wish_id, db)
    out = wishes_core._enrich(wish)
    out.convert_warning = warning
    out.purchase_ids = created_ids
    out.excess_warnings = excess_warnings
    out.tz_excess_approvals = tz_excess_approvals
    out.purchase_sync = purchase_sync
    # Владелец (2026-08-20): быстрое одобрение тоже создаёт закупку сразу здесь
    # (см. wish.status = "converted" выше) — отдаём номер закупки в этом же ответе,
    # чтобы фронт не звал следом POST /convert «на всякий случай» (см. тот же фикс
    # в wish_approvals.py::decide и wishes.py::convert_wish).
    if created_ids:
        out.purchases = (await wishes_core._wish_purchase_summaries_map([wish_id], db)).get(wish_id, [])
    return out


@router.post("/{wish_id}/reject", response_model=WishOut)
async def reject_wish(
    wish_id: int,
    body: WishReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a submitted wish with reason (manager+ roles OR assigned approver, submitted -> rejected)."""
    wish = await wishes_core._load_wish(wish_id, db)

    if not wishes_core._is_saas(current_user) and wish.status != "submitted":
        raise HTTPException(status_code=400, detail="Заявка должна быть в статусе 'submitted'")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    if not wishes_core._is_saas(current_user) and current_user.role not in MANAGER_ROLES and wish.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Отклонить заявку может менеджер+ или назначенный согласующий")

    # SaaS может отклонить заявку в любом статусе (в т.ч. converted) — если по ней уже
    # есть закупка в Плане закупок, убираем её из плана; закупка дальше стадии
    # «План закупок» отклонение блокирует явным 409 (владелец, 2026-08-07).
    await wishes_core._withdraw_wish_from_plan(wish.id, db, action_text="отклонить")

    wish.status = "rejected"
    wish.rejection_reason = body.rejection_reason
    # Владелец (2026-08-19): «нужно, чтобы было видно, кто отклонил» — прямое
    # отклонение (эта ветка) часто идёт без единой WishApproval-строки вовсе
    # (менеджер+ отклоняет напрямую, минуя цепочку согласующих), поэтому
    # rejected_by/rejected_at на самой заявке — единственный надёжный источник.
    from datetime import timezone as _tz
    wish.rejected_by = current_user.id
    wish.rejected_at = datetime.now(_tz.utc)
    # Владелец (2026-08-19): «если заявка отклоняется одним из согласующих, она
    # отклоняется у всех, потому что заявку могут изменить именно так, с чем
    # остальные согласующие могут не согласиться. И надо будет повторить заново» —
    # отклонение ОДНИМ согласующим не должно оставлять чужие "approved" решения
    # висеть в цепочке: после правок и повторной отправки согласование обязано
    # начаться с чистого листа, как и при обычном возврате на повторное
    # согласование (см. _reset_approvals выше, строка ~1924).
    await wishes_core._reset_approvals(wish.id, db)
    await db.commit()
    await db.refresh(wish)
    wish = await wishes_core._load_wish(wish_id, db)
    out = wishes_core._enrich(wish)
    return out


@router.patch("/{wish_id}/execution", response_model=WishOut)
async def patch_wish_execution(
    wish_id: int,
    body: WishExecutionPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """B-exec: согласующий ставит исполнителя и срок исполнения.

    Разрешено: assignee (согласующий), admin/manager. Только на submitted/approved.
    """
    wish = await wishes_core._load_wish(wish_id, db)
    if not wishes_core._is_saas(current_user) and wish.status not in ("submitted", "approved"):
        raise HTTPException(status_code=400, detail="Срок и исполнителя можно задать только на статусах submitted/approved")
    if not wishes_core._is_saas(current_user) and current_user.role not in MANAGER_ROLES and wish.assigned_to != current_user.id:
        # Согласующий из цепочки тоже может править (в т.ч. сменить ФЭО, если не согласен)
        from app.models.wish_approval import WishApproval
        in_chain = (await db.execute(
            select(WishApproval.id).where(
                WishApproval.wish_id == wish.id,
                WishApproval.user_id == current_user.id,
            ).limit(1)
        )).scalar_one_or_none()
        if not in_chain:
            raise HTTPException(status_code=403, detail="Только согласующий (в т.ч. из цепочки) или менеджер+ может менять эти поля")

    # Владелец (2026-08-19): «менять позиции может только тот, кто имеет право» —
    # правку ФЭО (категория заявки + построчные feo_category_id/feo_planned_item_id)
    # закрываем ОТДЕЛЬНЫМ правом wish.edit_feo — иначе любой согласующий из цепочки
    # (например, случайный юрист) мог сам перетыкивать позиции. Остальные поля
    # этого эндпоинта (executor_id/execution_deadline/event_id/assigned_to) это
    # право не трогает — их разрешают проверки выше (цепочка/assignee/менеджер+).
    _feo_fields_touched = body.feo_category_id is not None or body.items is not None
    if _feo_fields_touched and current_user.role != "superadmin":
        if not await has_org_key(current_user, db, wish.org_id, "wish.edit_feo", subsidy_id=wish.subsidy_id):
            raise HTTPException(
                status_code=403,
                detail="Право на перераспределение позиций заявки по категориям ФЭО не выдано, обратитесь к администратору",
            )

    if body.executor_id is not None:
        wish.executor_id = body.executor_id
    if body.execution_deadline is not None:
        wish.execution_deadline = body.execution_deadline
    if body.event_id is not None:
        wish.event_id = body.event_id
    if body.feo_category_id is not None:
        wish.feo_category_id = body.feo_category_id
    # W2: assigned_to меняется без сброса цепочки согласования
    if body.assigned_to is not None:
        wish.assigned_to = body.assigned_to

    # Владелец (2026-08-19): построчные ФЭО-правки согласующего (см.
    # WishItemFeoPatch) — состав заявки для него заблокирован на фронте
    # (PurchaseItemsEditor readonly + feoAttrsEditable), но категорию и
    # плановую позицию по каждой строке он вправе перераспределить. Здесь —
    # ТОЛЬКО эти два поля, никогда item_name/quantity/unit_price/total_price/
    # unit/country_origin и без добавления/удаления строк.
    _plan_transfer_warnings: list[str] = []
    if body.items is not None:
        _items_by_id = {wi.id: wi for wi in (wish.items or [])}
        # Валидация ВСЕГО набора до мутации — либо применяем целиком, либо
        # не трогаем ничего (одна транзакция, никаких частичных правок при 400/409).
        for item_patch in body.items:
            if item_patch.id not in _items_by_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Позиция #{item_patch.id} не принадлежит заявке №{wish.id}",
                )
        for item_patch in body.items:
            wi = _items_by_id[item_patch.id]
            _fields_set = item_patch.model_fields_set
            _cat_changing = (
                'feo_category_id' in _fields_set
                and item_patch.feo_category_id != wi.feo_category_id
            )
            if 'feo_category_id' in _fields_set:
                wi.feo_category_id = item_patch.feo_category_id
            if 'feo_planned_item_id' in _fields_set:
                _old_fpi_id = wi.feo_planned_item_id
                if item_patch.feo_planned_item_id is not None:
                    fpi = await db.get(FeoPlannedItem, item_patch.feo_planned_item_id)
                    if not fpi:
                        raise HTTPException(status_code=409, detail="Плановая позиция не найдена")
                    if not fpi.is_active:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"Плановая позиция «{fpi.name}» деактивирована (удалена из плана), "
                                "привязка к ней невозможна — выберите действующую или создайте новую."
                            ),
                        )
                    if wi.feo_category_id is None or fpi.feo_category_id != wi.feo_category_id:
                        _chosen_cat_name = (await db.execute(
                            select(FeoCategory.name).where(FeoCategory.id == fpi.feo_category_id)
                        )).scalar_one_or_none() or f"#{fpi.feo_category_id}"
                        if wi.feo_category_id is not None:
                            _target_cat_name = (await db.execute(
                                select(FeoCategory.name).where(FeoCategory.id == wi.feo_category_id)
                            )).scalar_one_or_none() or f"#{wi.feo_category_id}"
                        else:
                            _target_cat_name = "без категории ФЭО"
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"Плановая позиция «{fpi.name}» относится к категории «{_chosen_cat_name}», "
                                f"а позиция заявки — к категории «{_target_cat_name}». "
                                "Выберите плановую позицию той же категории."
                            ),
                        )
                    wi.feo_planned_item_id = item_patch.feo_planned_item_id
                    wi.over_plan = False
                else:
                    wi.feo_planned_item_id = None
                    wi.over_plan = False
                if _old_fpi_id is not None and _old_fpi_id != wi.feo_planned_item_id:
                    _old_fpi = await db.get(FeoPlannedItem, _old_fpi_id)
                    await _deactivate_if_orphaned(db, _old_fpi)
            elif _cat_changing and wi.feo_planned_item_id is not None:
                # Категория сменилась, а плановую позицию явно не переприслали —
                # та же логика «плановые позиции следуют за сменой категории»,
                # что и в update_wish (см. комментарий там, владелец 2026-08-17).
                if wi.feo_category_id is not None:
                    _w = await _move_or_detach_planned_item(db, wi, wi.feo_category_id)
                    if _w:
                        _plan_transfer_warnings.append(_w)
                else:
                    _old_fpi_id2 = wi.feo_planned_item_id
                    _old_fpi2 = await db.get(FeoPlannedItem, _old_fpi_id2)
                    wi.feo_planned_item_id = None
                    wi.over_plan = False
                    await _deactivate_if_orphaned(db, _old_fpi2)

    await db.commit()
    wish = await wishes_core._load_wish(wish_id, db)
    out = wishes_core._enrich(wish)
    out.plan_transfer_warnings = _plan_transfer_warnings
    return out


@router.post("/{wish_id}/status", response_model=WishOut)
async def force_wish_status(
    wish_id: int,
    body: WishStatusForce,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Superadmin/account_owner: force-переключение статуса заявки (минуя workflow-guard'ы).

    Форс «как будто пройден обычный путь»: при переключении в 'converted' реально
    создаются закупки (status='wishes') и заявка уходит из «Заявок» в «Закупки».
    'approved' — только одобрена (остаётся в «Заявках», закупки не создаются).
    """
    if not wishes_core._is_saas(current_user):
        raise HTTPException(status_code=403, detail="Только superadmin/account_owner может переключать статусы напрямую")
    allowed = {"draft", "submitted", "approved", "rejected", "converted"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Недопустимый статус. Разрешены: {sorted(allowed)}")
    wish = await wishes_core._load_wish(wish_id, db)
    excess_warnings: list = []
    purchase_sync: Optional[dict] = None

    if body.status == "converted":
        if not wish.items:
            raise HTTPException(status_code=400, detail="Заявка пустая — нечего распределять")
        try:
            # Аварийный рычаг: цепочку не блокируем, но закрываем pending-согласования,
            # чтобы заявка не «зависла» у согласующих
            from app.models.wish_approval import WishApproval
            pending = (await db.execute(
                select(WishApproval).where(
                    WishApproval.wish_id == wish.id,
                    WishApproval.status == "pending",
                )
            )).scalars().all()
            for a in pending:
                a.status = "approved"
                a.comment = "Закрыто принудительным переводом статуса"
                a.decided_by_user_id = current_user.id
                a.decided_by_username = current_user.full_name or current_user.username
                a.decided_at = func.now()
            await wishes_core._distribute_wish_to_purchases(wish, db, current_user, split=False)
            wish.status = "converted"
            wish.approved_by = wish.approved_by or current_user.id
            excess_warnings = getattr(wish, "_excess_warnings", [])
            purchase_sync = getattr(wish, "_purchase_sync", None)
            await db.commit()
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Ошибка при создании закупок — откат: {e}")
    elif body.status == "approved":
        wish.status = "approved"
        if not wish.approved_by:
            wish.approved_by = current_user.id
        await db.commit()
    else:
        # draft / submitted / rejected — просто переключение статуса.
        # Гейт (владелец, 2026-08-07): даже аварийный SaaS-рычаг больше не обходит
        # блокировку — закупка дальше «Плана закупок» останавливает force-переключение
        # так же, как обычный откат.
        _force_action_text = {
            "draft": "вернуть в черновик",
            "submitted": "вернуть на повторное согласование",
            "rejected": "отклонить",
        }.get(body.status, "сменить статус")
        await wishes_core._withdraw_wish_from_plan(wish.id, db, action_text=_force_action_text)
        wish.status = body.status
        if body.status in ("draft", "submitted"):
            # Возврат в черновик / на повторное согласование форс-рычагом —
            # старое отклонение так же не актуально, как и в обычном пути.
            wish.rejected_by = None
            wish.rejected_at = None
            wish.rejection_reason = None
            await db.flush()
            # Полный сброс (без keep_user_id) — иначе строка отклонившего
            # согласующего (см. decide()) осталась бы 'rejected' навсегда и
            # заблокировала бы sequential-гейт при повторном согласовании.
            await wishes_core._reset_approvals(wish.id, db)
        await db.commit()

    wish = await wishes_core._load_wish(wish_id, db)
    out = wishes_core._enrich(wish)
    out.excess_warnings = excess_warnings
    out.purchase_sync = purchase_sync
    return out
