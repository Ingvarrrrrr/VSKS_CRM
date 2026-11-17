"""Сервисная логика корректировки действующей закупки и возврата в черновик заявки.

Вынесено из app/routers/purchase_correction.py (Правило №5, < 500 строк на модуль):
- проверка права purchase.correct (ensure_can_correct);
- контроль превышения сумм/лимитов при переносе в другую категорию/позицию
  (check_correction_excess — переиспользует _collect_excess_warnings,
  collect_tz_over_plan_violations, collect_type_excess_violations);
- возврат до-договорной закупки в черновик исходной заявки с сохранением всех
  привязок к плановым позициям (return_purchase_to_draft_wish_core).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import OWNER_ROLES
from app.auth.object_visibility import ensure_purchase_visible
from app.auth.permissions import _active_org, has_org_key
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.subsidy import Subsidy
from app.models.user import User
from app.models.wish import Wish
from app.services.feo_effective_category import effective_item_feo_category_id
from app.services.purchase_approval_reset import reset_purchase_approvals
from app.services.type_excess_approval import collect_type_excess_violations, register_type_excess_approvals
from app.services.tz_excess_approval import collect_tz_over_plan_violations, register_tz_excess_approvals


async def resolve_purchase_org_id(p: Purchase, current_user: User, db: AsyncSession) -> Optional[int]:
    if p.subsidy_id:
        sub = await db.get(Subsidy, p.subsidy_id)
        if sub is not None:
            return sub.org_id
    return _active_org(current_user)


async def ensure_can_correct(p: Purchase, current_user: User, db: AsyncSession) -> None:
    """Гейт доступа к корректировке действующей закупки (право purchase.correct)."""
    await ensure_purchase_visible(current_user, p.id, db)
    if p.status == "cancelled":
        raise HTTPException(status_code=409, detail="Нельзя корректировать отменённую закупку")
    if current_user.role in OWNER_ROLES:
        return

    org_id = await resolve_purchase_org_id(p, current_user, db)
    if await has_org_key(current_user, db, org_id, "purchase.correct", subsidy_id=p.subsidy_id):
        return

    raise HTTPException(
        status_code=403,
        detail="Нет права «Корректировка действующей закупки» (purchase.correct)",
    )


async def check_correction_excess(
    db: AsyncSession,
    p: Purchase,
    p_items: list,
    touched_cat_ids: set[int],
    allow_excess: bool,
    current_user: User,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Проверяет бюджет/суммы при переносе закупки/позиций в другую категорию или
    плановую позицию.

    При обнаружении превышения и allow_excess=False откатывает транзакцию и
    бросает 409 CORRECTION_CAUSES_EXCESS, предлагая вернуть закупку в черновик
    заявки для пересогласования либо явно подтвердить отправку превышения на
    согласование (allow_excess=True).
    """
    if not p.subsidy_id or not touched_cat_ids:
        return [], [], []

    per_item_mode = bool(getattr(p, "feo_per_item", False))
    cat_items_map: dict[int, list[dict]] = {}
    for pi in p_items:
        eff_cid = effective_item_feo_category_id(per_item_mode, p.feo_category_id, pi.feo_category_id)
        if eff_cid is not None and eff_cid in touched_cat_ids:
            cat_items_map.setdefault(eff_cid, []).append({
                "name": pi.item_name or "Позиция",
                "amount": float(pi.total_price or 0),
            })

    from app.services.wish_distribution import _collect_excess_warnings
    excess_warnings = await _collect_excess_warnings(db, p.subsidy_id, cat_items_map) if cat_items_map else []
    all_tz_violations = await collect_tz_over_plan_violations(
        db, p_items, fallback_category_id=p.feo_category_id,
    )
    tz_violations = [
        v for v in all_tz_violations if v.get("feo_category_id") in touched_cat_ids
    ]
    all_type_violations = await collect_type_excess_violations(db, p.subsidy_id, list(touched_cat_ids))
    type_violations = [
        v for v in all_type_violations
        if v.get("level") == "category" and v.get("feo_category_id") in touched_cat_ids
    ]

    if (excess_warnings or tz_violations or type_violations) and not allow_excess:
        messages: list[str] = []
        for w in excess_warnings:
            budget = float(w.get("budget") or 0)
            messages.append(
                f"Категория «{w['category_name']}»: план {w['plan_after']:,.2f} ₽, "
                f"по ФЭО {budget:,.2f} ₽, превышение {w['excess_amount']:,.2f} ₽"
            )
        for v in tz_violations:
            if v.get("message"):
                messages.append(v["message"])
        for v in type_violations:
            if v.get("message"):
                messages.append(v["message"])

        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CORRECTION_CAUSES_EXCESS",
                "message": (
                    "Перераспределение вызывает превышение сумм: " + "; ".join(messages)
                ),
                "excess_warnings": excess_warnings,
                "tz_violations": tz_violations,
                "type_violations": type_violations,
                "has_wish": bool(p.wish_id),
                "wish_id": p.wish_id,
            },
        )

    tz_approvals: list[dict] = []
    type_approvals: list[dict] = []
    if allow_excess:
        if tz_violations:
            tz_approvals = await register_tz_excess_approvals(
                db, tz_violations, subsidy_id=p.subsidy_id, current_user=current_user,
                context_label=f"корректировка закупки {p.registry_number or f'№{p.id}'}",
            )
        if type_violations:
            type_approvals = await register_type_excess_approvals(
                db, type_violations, subsidy_id=p.subsidy_id, current_user=current_user,
                context_label=f"корректировка закупки {p.registry_number or f'№{p.id}'}",
            )
    return excess_warnings, tz_approvals, type_approvals


async def return_purchase_to_draft_wish_core(
    p: Purchase,
    comment: Optional[str],
    db: AsyncSession,
    current_user: User,
) -> dict:
    """Возвращает закупку через кнопку «Корректировка» в черновик исходной заявки
    (draft), переводя закупку в скрытый статус 'wishes' и сбрасывая согласования.
    Все позиции сохраняют свои текущие привязки к плановым позициям."""
    if not p.wish_id:
        raise HTTPException(
            status_code=409,
            detail="У этой закупки нет исходной заявки — скорректируйте категорию ФЭО или мероприятие в этом окне.",
        )
    if p.status not in ("wishes", "plan_schedule", "work_in_progress"):
        from app.routers.purchase_transitions import STATUS_LABELS
        label = STATUS_LABELS.get(p.status, p.status)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Закупку на стадии «{label}» нельзя вернуть в черновик заявки — по ней уже "
                "оформлен договор или идёт поставка. Используйте корректировку категории и мероприятия."
            ),
        )

    wish = await db.get(Wish, p.wish_id)
    if wish is None:
        raise HTTPException(status_code=404, detail="Исходная заявка не найдена")

    clean_comment = (comment or "").strip() or None
    old_status = p.status
    p.status = "wishes"
    p.approval_status = None

    await reset_purchase_approvals(
        p, db, current_user,
        event_type="returned_to_draft_wish",
        event_data={"wish_id": wish.id, "comment": clean_comment},
    )

    db.add(PurchaseEvent(
        purchase_id=p.id,
        user_id=current_user.id,
        event_type="status_changed",
        data={
            "from": old_status,
            "to": "wishes",
            "reason": clean_comment or "Возврат в черновик заявки через Корректировку",
        },
    ))

    from app.services.wish_distribution import _reset_approvals
    wish.status = "draft"
    wish.rejected_by = None
    wish.rejected_at = None
    wish.rejection_reason = None
    await _reset_approvals(wish.id, db)

    await db.commit()
    return {
        "ok": True,
        "purchase_id": p.id,
        "purchase_status": p.status,
        "wish_id": wish.id,
        "wish_status": wish.status,
    }
