"""Purchase state-machine transitions router — extracted from purchases.py (Phase 16-06).

Handles:
  POST /api/purchases/{pid}/transition       — forward-only status transition with field guards
  POST /api/purchases/{pid}/convert-to-order — convert service_note basis to plan_schedule

G-08: TRANSITION_REQUIRED dict lives here (only transition endpoint uses it).
STATUS_ORDER stays in purchases.py (G-08 — used by CRUD + members + my-tasks).
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES, MANAGER_ROLES, OWNER_ROLES
from app.auth.permissions import require_action
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.routers.purchases import (
    _purchase_to_full, _item_to_out, STATUS_ORDER,
)
from app.schemas.schemas import PurchaseOutFull
# Гейты обязательных полей/превышения ФЭО-ТЗ-типа переехали в
# app/services/purchase_transition_core.py — импорты сюда больше не нужны.

router = APIRouter(prefix="/api/purchases", tags=["purchase-transitions"])

# G-08: TRANSITION_REQUIRED lives HERE (only transition endpoint uses it)

STATUS_LABELS: dict[str, str] = {
    "planned":        "Запланирован",
    "contracted":     "Заключён договор",
    "ordered":        "Заказано",
    "delivered":      "Поставлено",
    "paid":           "Оплачено",
    "wishes":         "Заявка",
    "plan_schedule":  "План закупок",
    "work_in_progress": "Ведётся работа",
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


async def _autofill_accepted_fields(purchase: Purchase, db: AsyncSession) -> None:
    """5-я стадия жизненного цикла позиции («приняли») — автозаполнение при delivered.

    Для каждой purchase_item, у которой accepted_name ещё NULL: берём name/quantity/unit
    из связанной ContractItem (по source_item_id), а если договорной строки нет — из самой
    purchase_item (item_name/quantity/unit). Позиции, где accepted_name уже заполнен
    (ручная правка PATCH-ем или повторный переход), не трогаем.
    """
    items_res = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )
    items = items_res.scalars().all()
    if not items:
        return
    item_ids = [it.id for it in items]
    ci_res = await db.execute(
        select(ContractItem).where(ContractItem.source_item_id.in_(item_ids))
    )
    ci_by_source: dict[int, ContractItem] = {}
    for ci in ci_res.scalars().all():
        if ci.source_item_id not in ci_by_source:
            ci_by_source[ci.source_item_id] = ci
    for it in items:
        if it.accepted_name is not None:
            continue
        ci = ci_by_source.get(it.id)
        if ci is not None:
            it.accepted_name = ci.name
            it.accepted_quantity = ci.quantity
            it.accepted_unit = ci.unit
        else:
            it.accepted_name = it.item_name
            it.accepted_quantity = it.quantity
            it.accepted_unit = it.unit


@router.post("/{pid}/transition", response_model=PurchaseOutFull)
async def transition_status(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Forward-only status transition.
    wishes → plan_schedule → work_in_progress → contracted → delivered → paid
    (рамочные договоры: work_in_progress → delivered, минуя contracted)
    """
    if target_status not in STATUS_ORDER:
        raise HTTPException(422, f"Недопустимый статус: {target_status}")

    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # assert_no_unapproved_excess ниже больше не бросает 409 за перекос
    # ОТДЕЛЬНОЙ категории (excess_amount), возвращает список предупреждений —
    # копим сюда, отдаём в ответе (excess_warnings, см. конец функции). Тот же
    # паттерн, что уже применён в app.routers.wishes/purchases.py.
    _excess_warnings: list[dict] = []

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

    # Владелец (2026-09-29): «авансовый не должен уходить в план закупок без
    # согласования возмещения — иначе все сотрудники наделают авансовых и
    # оставят их в плане закупок». Для обычной закупки из заявки закупка
    # вообще появляется только ПОСЛЕ согласования (app/routers/wish_convert.py
    # ::convert_wish требует wish.status in ('approved','converted')) — здесь
    # тот же принцип для авансового: компаньон (Purchase.wish_id,
    # source='advance_report') обязан быть 'approved' до первого выхода из
    # 'wishes'. Проверка ДО SaaS-bypass — правило действует без исключений
    # по ролям, ровно так, как просил владелец.
    if getattr(p, 'purchase_method', None) == 'advance' and p.status == 'wishes' and target_status != 'wishes':
        from app.models.wish import Wish
        # Реальные статусы (см. app/routers/wish_approvals.py::decide): когда
        # последний согласующий цепочки одобряет заявку с items (companion
        # авансового ВСЕГДА имеет WishItem-и — зеркало позиций закупки),
        # decide() в ОДНОЙ транзакции ставит status='approved', а затем
        # (т.к. wish.items непусто) сразу 'converted' — 'approved' как
        # устойчивое конечное состояние для такой заявки не наблюдается.
        # Принимаем оба, чтобы не зависеть от промежуточной летучей стадии.
        _companion = await db.get(Wish, p.wish_id) if p.wish_id else None
        if _companion is None or _companion.status not in ('approved', 'converted'):
            raise HTTPException(
                409,
                "Сначала отправьте возмещение на согласование и дождитесь согласования"
            )

    # SaaS-bypass: superadmin/account_owner — force-set статус минуя любые guard'ы.
    if current_user.role in OWNER_ROLES:
        p.status = target_status
        if target_status == "delivered":
            await _autofill_accepted_fields(p, db)
        await db.commit()
        await db.refresh(p)
        return p

    current_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
    target_idx = STATUS_ORDER.index(target_status)

    # 27.4-12: advance owner bypass — ограничен.
    # Сотрудник (даже владелец авансового) может двигать ТОЛЬКО forward
    # и ТОЛЬКО когда закупка уже направлена в работу (work_in_progress+).
    is_advance_owner = (
        getattr(p, 'purchase_method', None) == 'advance'
        and getattr(p, 'reimbursement_user_id', None) == current_user.id
    )
    is_manager_plus = current_user.role in MANAGER_ROLES
    WORK_IN_PROGRESS_IDX = STATUS_ORDER.index("work_in_progress")

    if is_advance_owner and not is_manager_plus:
        if current_idx < WORK_IN_PROGRESS_IDX:
            raise HTTPException(
                403,
                "Закупка должна быть направлена в работу "
                "(статус «Направлено в закупку» или позже) перед изменением сотрудником"
            )
        if target_idx <= current_idx:
            raise HTTPException(
                403,
                "Сотрудник может двигать статус только вперёд. "
                "Откат разрешён только администратору"
            )
    elif not is_manager_plus:
        # Не владелец авансового и не manager+ → требуется permission action
        from app.auth.permissions import get_effective_actions, _active_org
        actions = await get_effective_actions(current_user, db, _active_org(current_user))
        if 'purchase.status_change' not in actions:
            raise HTTPException(403, "Нужно разрешение «Изменение статуса закупки»")

    # Direction check: forward-only for non-admin
    if target_idx <= current_idx:
        if current_user.role not in ADMIN_ROLES:
            raise HTTPException(422, "Откат статуса разрешён только администратору")

    # Framework skip: рамочные договоры пропускают стадию «Заключён договор».
    # Данные берутся из головного рамочного договора — отдельный договор не заключается.
    _is_framework = p.purchase_contract_type in FRAMEWORK_TYPES
    if _is_framework and target_status == "contracted" and current_user.role not in OWNER_ROLES:
        raise HTTPException(
            422,
            "Закупка по рамочному договору не проходит стадию «Заключён договор»: "
            "используйте переход сразу в «Поставлено»."
        )

    # Approval guard: block contracted transition if approval is pending/rejected
    if target_status == "contracted" and p.approval_status and p.approval_status not in ("approved",):
        raise HTTPException(
            422,
            f"Закупка должна быть согласована перед заключением договора. "
            f"Текущий статус согласования: {p.approval_status}"
        )

    # Ядро перехода (гейты обязательных полей + превышения ФЭО/ТЗ/типа +
    # смена статуса + побочные эффекты) вынесено в
    # app/services/purchase_transition_core.py::apply_purchase_status_transition —
    # тем же кодом пользуется автоматический перевод авансовой закупки после
    # финального согласования компаньона (см. app/services/wish_distribution.py,
    # владелец 2026-09-29). Второй копии гейтов НЕТ (ПРАВИЛО №6).
    from app.services.purchase_transition_core import apply_purchase_status_transition
    _excess_warnings = await apply_purchase_status_transition(
        p, pid, target_status, current_user, db, current_idx, target_idx,
    )

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
    # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки — см. _purchase_to_full.
    from app.services.purchase_amounts import load_purchase_amounts as _load_purchase_amounts
    _amounts_map = await _load_purchase_amounts(db, [p.id])
    out = _purchase_to_full(p, contractors, subsidies, amounts_map=_amounts_map)
    if _excess_warnings:
        out.excess_warnings = _excess_warnings
    return out


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
    # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки — см. _purchase_to_full.
    from app.services.purchase_amounts import load_purchase_amounts as _load_purchase_amounts
    _amounts_map = await _load_purchase_amounts(db, [p.id])
    return _purchase_to_full(p, contractors, subsidies, amounts_map=_amounts_map)
