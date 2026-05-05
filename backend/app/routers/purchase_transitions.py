"""Purchase state-machine transitions router — extracted from purchases.py (Phase 16-06).

Handles:
  POST /api/purchases/{pid}/transition       — forward-only status transition with field guards
  POST /api/purchases/{pid}/convert-to-order — convert service_note basis to plan_schedule

G-08: TRANSITION_REQUIRED dict lives here (only transition endpoint uses it).
STATUS_ORDER stays in purchases.py (G-08 — used by CRUD + members + my-tasks).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.user import User
from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES, MANAGER_ROLES
from app.auth.permissions import require_action
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.routers.purchases import _purchase_to_full, _item_to_out, STATUS_ORDER
from app.schemas.schemas import PurchaseOutFull

router = APIRouter(prefix="/api/purchases", tags=["purchase-transitions"])

# G-08: TRANSITION_REQUIRED lives HERE (only transition endpoint uses it)

STATUS_LABELS: dict[str, str] = {
    "planned":        "Запланирован",
    "confirmed":      "Подтверждён",
    "contracted":     "Заключён договор",
    "ordered":        "Заказано",
    "delivered":      "Поставлено",
    "paid":           "Оплачено",
    "wishes":         "Заявка",
    "plan_schedule":  "План-график",
    "work_in_progress": "В работе",
    "cancelled":      "Отменён",
}

FIELD_LABELS: dict[str, str] = {
    "contract_number":       "Номер договора",
    "contract_date":          "Дата договора",
    "acceptance_doc_name":     "Наименование акта приёмки",
    "acceptance_doc_date":     "Дата акта приёмки",
    "acceptance_doc_number":   "Номер акта приёмки",
    "acceptance_doc_amount":   "Сумма акта приёмки",
    "payment_doc_number":      "Номер платёжного поручения",
    "payment_doc_date":        "Дата платежа",
    "payment_amount":          "Сумма платежа",
}

TRANSITION_REQUIRED: dict[str, list[str]] = {
    "contracted": ["contract_number", "contract_date"],
    "delivered": ["acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number", "acceptance_doc_amount"],
    "paid": ["payment_doc_number", "payment_doc_date", "payment_amount"],
}


@router.post("/{pid}/transition", response_model=PurchaseOutFull)
async def transition_status(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Forward-only status transition.
    wishes → plan_schedule → confirmed → work_in_progress → contracted → delivered → paid
    """
    if target_status not in STATUS_ORDER:
        raise HTTPException(422, f"Недопустимый статус: {target_status}")

    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    current_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
    target_idx = STATUS_ORDER.index(target_status)

    # Role check: only manager+ can transition
    if current_user.role not in MANAGER_ROLES:
        raise HTTPException(403, "Недостаточно прав для смены статуса")

    # Direction check: forward-only for non-admin
    if target_idx <= current_idx:
        if current_user.role not in ADMIN_ROLES:
            raise HTTPException(422, "Откат статуса разрешён только администратору")

    # Approval guard: block contracted transition if approval is pending/rejected
    if target_status == "contracted" and p.approval_status and p.approval_status not in ("approved",):
        raise HTTPException(
            422,
            f"Закупка должна быть согласована перед заключением договора. "
            f"Текущий статус согласования: {p.approval_status}"
        )

    # Catalog guard: warn but don't block (except advance reports)
    # Previously blocked status transition — now just logs a warning
    if target_status == "confirmed" and getattr(p, 'purchase_method', None) != "advance":
        unmatched = [i for i in (p.items or []) if not i.product_id]
        if unmatched:
            import logging
            logging.getLogger(__name__).warning(
                "Purchase %s has %d items not linked to catalog", pid, len(unmatched)
            )

    # Field guards for specific target statuses
    if target_status in TRANSITION_REQUIRED:
        # acceptance_docs JSONB overrides legacy single fields
        has_acceptance_docs = bool(p.acceptance_docs and len(p.acceptance_docs) > 0 and any(d.get("name") for d in p.acceptance_docs))
        required_fields = TRANSITION_REQUIRED[target_status]
        if has_acceptance_docs and target_status == "delivered":
            required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        # Phase 23.4: для авансовых отчётов с привязанными чеками acceptance_doc не обязательны
        if target_status == "delivered" and getattr(p, "purchase_method", None) == "advance":
            from app.models.purchase_receipt import PurchaseReceipt
            rcpt_result = await db.execute(
                select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == p.id).limit(1)
            )
            if rcpt_result.first() is not None:
                required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        missing = [
            f for f in required_fields
            if not getattr(p, f, None)
        ]
        if missing:
            is_advance = getattr(p, "purchase_method", None) == "advance"
            # Доработка 5 мая: для авансового «Дата договора» переименовываем
            # в «Дата документа основания» (чек/УПД) — пользователю иначе непонятно,
            # что это поле принимает дату чека.
            field_label_map = dict(FIELD_LABELS)
            if is_advance:
                field_label_map["contract_date"] = "Дата документа основания (чек/УПД)"
                field_label_map["contract_number"] = "Номер документа основания (№ чека/УПД)"
            missing_labels = [field_label_map.get(f, f) for f in missing]
            status_label = STATUS_LABELS.get(target_status, target_status)

            if is_advance and target_status == "contracted":
                advance_hint = (
                    " Заполните в карточке закупки дату/номер чека или УПД."
                    " Либо загрузите чек через QR/Файл — тогда поля заполнятся автоматически."
                )
            elif is_advance and target_status == "delivered":
                advance_hint = (
                    " Для авансового отчёта добавьте чек через сканирование QR"
                    " или загрузку JSON/изображения. После добавления чека статус «Поставлено» доступен."
                )
            else:
                advance_hint = (
                    " Для авансового отчёта рекомендуется загрузить чек через QR —"
                    " большинство полей заполнятся автоматически."
                ) if is_advance else ""

            raise HTTPException(
                422,
                detail={
                    "code": "STATUS_TRANSITION_BLOCKED",
                    "message": (
                        f"Для перехода в статус «{status_label}» заполните:"
                        f" {', '.join(missing_labels)}.{advance_hint}"
                    ),
                    "missing_fields": missing,
                    "status": target_status,
                    "status_label": status_label,
                },
            )

    old_status = p.status
    p.status = target_status

    # При переходе в contracted — обновить цены в каталоге товаров
    if target_status == "contracted" and p.items:
        sub = await db.get(Subsidy, p.subsidy_id) if p.subsidy_id else None
        contract_org_id = sub.org_id if sub else None
        for item in p.items:
            if not item.product_id:
                continue
            product = await db.get(Product, item.product_id)
            if not product:
                continue
            item_price = item.unit_price
            product.contract_price = item_price
            product.price = item_price
            product.contract_number = p.contract_number
            product.contract_date = p.contract_date
            product.contract_org_id = contract_org_id

    # Auto-create/link contract record when moving to contracted status
    if target_status == "contracted":
        await ensure_contract_linked(p, db)

    await db.commit()

    # Auto-log status change event
    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=getattr(current_user, "id", None),
            event_type="status_changed",
            data={"from": old_status, "to": target_status},
        ))
        await db.commit()
    except Exception:
        pass

    # Notify purchase members + linked task assignees about status change
    try:
        from app.notifications import notify_purchase_status_changed
        from app.models.purchase_event import PurchaseMember
        from app.models.task import Task, TaskAssignee

        notify_user_ids: set[int] = set()
        notify_users = []

        # 1. Purchase members
        members_r = await db.execute(
            select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
        )
        for m in members_r.scalars().all():
            if m.user_id != current_user.id:
                notify_user_ids.add(m.user_id)

        # 2. Assigned user of purchase
        if p.assigned_user_id and p.assigned_user_id != current_user.id:
            notify_user_ids.add(p.assigned_user_id)

        # 3. All assignees of tasks linked to this purchase
        linked_tasks_r = await db.execute(
            select(Task.id).where(Task.purchase_id == pid)
        )
        linked_task_ids = [r[0] for r in linked_tasks_r.all()]
        if linked_task_ids:
            ta_r = await db.execute(
                select(TaskAssignee.user_id).where(
                    TaskAssignee.task_id.in_(linked_task_ids)
                )
            )
            for r in ta_r.all():
                if r[0] != current_user.id:
                    notify_user_ids.add(r[0])

        # Load user objects
        for uid in notify_user_ids:
            u = await db.get(User, uid)
            if u:
                notify_users.append(u)

        if notify_users:
            await notify_purchase_status_changed(
                p, current_user.full_name or current_user.username,
                target_status, notify_users
            )
    except Exception:
        pass

    # Re-fetch with eager loads after commit
    result2 = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result2.scalar_one()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)


@router.post("/{pid}/convert-to-order", response_model=PurchaseOutFull)
async def convert_service_note_to_order(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action('purchase.transition_status')),
):
    """Конвертировать служебную записку на выдачу в закупку (меняет purchase_basis на plan_schedule)."""
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if p.purchase_basis != 'service_note':
        raise HTTPException(422, "Конвертация доступна только для служебных записок")
    p.purchase_basis = 'plan_schedule'
    await db.commit()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)
