"""Подтверждение «Оплачено» согласующими субсидии (план 2026-10-04-fadm-statement, п.3,
доработка после приёмки 04.10: статусы contracted/ordered/delivered, не только delivered).

Вместо молчаливого автоперевода закупки в paid (см.
app/services/purchase_payments.py::recompute_purchase_payments,
PAID_CONFIRMATION_ELIGIBLE_STATUSES) при достижении порога оплаты заводится
PurchasePaidConfirmation (pending). Согласующий субсидии
(app/models/subsidy_approver.py::SubsidyApprover, достаточно одного) либо
superadmin/account_owner подтверждает — закупка переходит в paid ШТАТНЫМ
переходом (app/services/purchase_transition_core.py), ПОШАГОВО через каждый
промежуточный статус (contracted→ordered→delivered→paid), если нужно: функция
не умеет прыгать через гейты нескольких статусов разом. Каждый шаг пишет
PurchaseEvent и шлёт notify_purchase_status_changed сам (ПРАВИЛО №6 — вторая
копия гейтов/уведомления не заводится); если шаг заблокирован (чаще всего
delivered — нет закрывающих документов) — 409 с причиной, запрос остаётся
pending. Либо отклоняет (запись помечается rejected, статус закупки не
трогается, привязанные ЭТИМ прогоном выписки платежи отвязываются — см.
unlink_bank_payment, и пара запоминается — см.
app/models/purchase_paid_confirmation_rejection.py).

GET  /api/subsidies/{id}/paid-confirmations?status=pending
GET  /api/purchases/{pid}/paid-confirmation
POST /api/paid-confirmations/{id}/confirm
POST /api/paid-confirmations/{id}/reject

Перф-доработка 2026-10-06 (лог прода: список pending по субсидии с ~120
строками шёл 40-60+ с — таймаут фронта REQUEST_TIMEOUT_MS=60000 в api.ts):
список (list_subsidy_paid_confirmations) раньше гонял _simulate_confirm_chain
(savepoint + штатный переход) ДЛЯ КАЖДОЙ строки — ~0.4 с/строка — и добирал
Purchase/Contractor/Payment по одному (N+1). Теперь список грузит эти три
таблицы батчем (один select с IN по списку id) и НЕ симулирует — отдаёт
checked=false для pending (blocked_reason=None, plan_excess_warning из
персистентной колонки c.plan_excess_warning). Фронт дозапрашивает проверку
отдельно, порциями — см. POST /api/subsidies/{id}/paid-confirmations/check
в app/routers/purchase_paid_confirmations_check.py (вынесено отдельным
роутером — этот файл уже на границе ПРАВИЛА №5 про модульность).
Единственное место, где реально гоняется цепочка перехода — тот же
_simulate_confirm_chain (ПРАВИЛО №6), что и раньше: ни список, ни /check,
ни одноразовый GET по закупке не заводят вторую копию проверки.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.contractor import Contractor
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover

router = APIRouter(tags=["purchase-paid-confirmations"])

_SAAS_BYPASS_ROLES = ("superadmin", "account_owner")


async def _get_subsidy_or_404(sid: int, db: AsyncSession) -> Subsidy:
    s = await db.get(Subsidy, sid)
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    return s


async def _is_subsidy_approver(db: AsyncSession, subsidy_id: int, user_id: int) -> bool:
    row = (await db.execute(
        select(SubsidyApprover.id).where(
            SubsidyApprover.subsidy_id == subsidy_id,
            SubsidyApprover.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def _assert_can_decide(current_user, db: AsyncSession, subsidy_id: int) -> None:
    if current_user.role in _SAAS_BYPASS_ROLES:
        return
    if await _is_subsidy_approver(db, subsidy_id, current_user.id):
        return
    raise HTTPException(
        403,
        "Подтвердить или отклонить оплату может только согласующий этой субсидии "
        "(см. вкладку «Субсидии» → «Согласующие») либо владелец аккаунта",
    )


# Тексты гейтов превышения (feo_plan_excess.py/tz_excess_approval.py) уже
# по-русски называют категорию/план/факт/превышение — но форматируют деньги
# по-английски (f"{x:,.2f}" → "340,764.50"). Владелец (доработка «оплата из
# выписки — факт»): plan_excess_warning обязан быть в русском денежном
# формате «340 764,50 ₽». Не переписываем сами гейты (другие вызывающие их
# тоже показывают эти тексты, менять формат там — отдельная, более широкая
# задача) — только нормализуем ДЛЯ ЭТОГО нового поля.
_US_MONEY_RE = re.compile(r"(\d[\d,]*)\.(\d{2})(?=\s*₽)")


def _ru_money_format(text: str) -> str:
    return _US_MONEY_RE.sub(lambda m: f"{m.group(1).replace(',', ' ')},{m.group(2)}", text)


def _format_plan_excess_warning(messages: list) -> Optional[str]:
    """Объединяет собранные во время _walk_to_paid тексты обойдённых гейтов
    превышения плана (план над ФЭО / ТЗ над плановой позицией) в ОДНО поле
    ответа — убирает дубли (один и тот же гейт обычно срабатывает на каждом
    шаге цепочки одинаково) и приводит деньги к русскому формату."""
    seen = set()
    unique = []
    for m in messages or []:
        if m not in seen:
            seen.add(m)
            unique.append(m)
    if not unique:
        return None
    return "\n\n".join(_ru_money_format(m) for m in unique)


async def _walk_to_paid(
    db: AsyncSession, p: Purchase, current_user, *, commit: bool, send_notification: bool,
    plan_excess_messages_out: Optional[list] = None,
) -> tuple[list[str], Optional[tuple[str, object]]]:
    """Идёт по STATUS_ORDER от p.status до 'paid' ПОШАГОВО через
    apply_purchase_status_transition (contracted→ordered→delivered→paid,
    сколько нужно шагов) — функция не умеет прыгать через гейты нескольких
    статусов разом. Возвращает (пройденные_статусы, None) при полном успехе,
    или (пройденные_статусы, (статус_на_котором_встало, exc.detail)) при
    первом заблокированном шаге — НЕ бросает исключение наружу, чтобы ОДИН и
    тот же код обслуживал и настоящий confirm (который решает — откатывать
    транзакцию целиком или нет), и «сухой» прогон для blocked_reason
    (_simulate_confirm_chain ниже) — ПРАВИЛО №6, не дублируем цикл.

    Владелец (доработка «оплата из выписки — факт», план 2026-10-04-fadm-
    statement): confirm ВСЕГДА идёт с skip_plan_excess_gates=True — превышение
    плана по категории ФЭО (ни «план над ФЭО», ни «ТЗ/договор над плановой
    позицией») НЕ блокирует эту цепочку, его текст складывается в
    plan_excess_messages_out (если передан) — см. apply_purchase_status_
    transition. Прочие гейты (закрывающие документы и т.п.) не затронуты —
    по-прежнему блокируют и попадают в (статус, exc.detail)."""
    from app.routers.purchases import STATUS_ORDER
    from app.services.purchase_transition_core import apply_purchase_status_transition

    paid_idx = STATUS_ORDER.index("paid")
    visited: list[str] = []
    while STATUS_ORDER.index(p.status) < paid_idx:
        cur_idx = STATUS_ORDER.index(p.status)
        next_status = STATUS_ORDER[cur_idx + 1]
        event_note = "Поставлено (по подтверждению оплаты)" if next_status == "delivered" else None
        try:
            await apply_purchase_status_transition(
                p, p.id, next_status, current_user, db, cur_idx, cur_idx + 1,
                event_note=event_note, commit=commit, send_notification=send_notification,
                skip_plan_excess_gates=True, plan_excess_messages_out=plan_excess_messages_out,
            )
        except HTTPException as exc:
            return visited, (next_status, exc.detail)
        visited.append(next_status)
    return visited, None


async def _simulate_confirm_chain(
    db: AsyncSession, p: Purchase, current_user,
) -> tuple[Optional[str], Optional[str]]:
    """«Сухая» проверка (доработка приёмки — поля blocked_reason/
    plan_excess_warning в ответе): прошла бы вся цепочка confirm до paid без
    фактической записи? Гоняет _walk_to_paid (commit=False/send_notification=
    False, те же skip_plan_excess_gates=True, что и настоящий confirm) ВНУТРИ
    SAVEPOINT (db.begin_nested()) на уже загруженном объекте p, затем
    безусловно откатывает savepoint.

    ВАЖНО для вызывающего (_confirmation_to_dict): SAVEPOINT-rollback истекает
    (expire) ТОЛЬКО объекты, реально изменённые внутри него — проверено
    эмпирически объекты сессии, которых эта симуляция не коснулась (включая
    саму PurchasePaidConfirmation `c`), остаются доступны как ни в чём не
    бывало, но сам `p` будет истёкшим (ветки TRANSITION_REQUIRED меняют его
    поля) — обращаться к p.* ПОСЛЕ вызова этой функции нельзя: вызывающий код
    обязан сначала прочитать все нужные поля p в обычные переменные/словарь,
    и только потом звать эту функцию.

    Возвращает (blocked_reason, plan_excess_warning) — ПЕРВОЕ: None (помех
    нет) или причина первой блокировки, которая по-прежнему блокирует (не
    превышение плана — то не блокирует нигде, см. apply_purchase_status_
    transition.skip_plan_excess_gates); ВТОРОЕ: None или человекочитаемое,
    по-русски и с русским денежным форматом предупреждение о превышении,
    которое БУДЕТ обойдено, если согласующий нажмёт confirm (см.
    _format_plan_excess_warning)."""
    from app.routers.purchase_transitions import STATUS_LABELS
    from app.services.purchase_payments import PAID_CONFIRMATION_ELIGIBLE_STATUSES

    if p.status not in PAID_CONFIRMATION_ELIGIBLE_STATUSES:
        label = STATUS_LABELS.get(p.status, p.status)
        return f"Закупка сейчас в статусе «{label}» — подтверждение недоступно, обновите список", None

    plan_excess_messages: list[str] = []
    nested = await db.begin_nested()
    try:
        _, blocked = await _walk_to_paid(
            db, p, current_user, commit=False, send_notification=False,
            plan_excess_messages_out=plan_excess_messages,
        )
    finally:
        await nested.rollback()

    plan_excess_warning = _format_plan_excess_warning(plan_excess_messages)
    if blocked is None:
        return None, plan_excess_warning
    next_status, detail = blocked
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    label = STATUS_LABELS.get(next_status, next_status)
    return f"Нельзя перевести закупку в «{label}»: {message}", plan_excess_warning


def _confirmation_payments_dict(payments: list[Payment]) -> list[dict]:
    return [
        {
            "id": pay.id,
            "payment_date": pay.payment_date.isoformat() if pay.payment_date else None,
            "document_number": pay.document_number,
            "amount": float(pay.amount) if pay.amount is not None else None,
            "payment_purpose": pay.payment_purpose,
        }
        for pay in payments
    ]


def _build_purchase_dict(p: Purchase, contractor_name: Optional[str]) -> dict:
    """Единственное место, где закупка приводится к виду карточки
    подтверждения — переиспользуется и одиночным GET/confirm/reject
    (_confirmation_to_dict), и батч-списком (_list_confirmation_dicts),
    и /check (purchase_paid_confirmations_check.py) — ПРАВИЛО №6."""
    from app.routers.purchase_transitions import STATUS_LABELS
    return {
        "id": p.id,
        "registry_number": p.registry_number,
        "subject": p.subject,
        "contractor_name": contractor_name,
        "contract_price": float(p.contract_price) if p.contract_price is not None else None,
        "payment_amount": float(p.payment_amount) if p.payment_amount is not None else None,
        "status": p.status,
        "status_label": STATUS_LABELS.get(p.status, p.status),
    }


def _base_confirmation_dict(
    c: PurchasePaidConfirmation, purchase_dict: Optional[dict], payments_dict: list[dict],
    *, blocked_reason: Optional[str], plan_excess_warning: Optional[str], checked: bool,
) -> dict:
    """Общая форма ответа для списка/одиночного GET/confirm/reject —
    отличаются только тем, откуда взялись blocked_reason/plan_excess_warning/
    checked (симуляция или персистентная колонка)."""
    return {
        "id": c.id,
        "purchase_id": c.purchase_id,
        "subsidy_id": c.subsidy_id,
        "status": c.status,
        "requested_at": c.requested_at.isoformat() if c.requested_at else None,
        "amount_confirmed": float(c.amount_confirmed) if c.amount_confirmed is not None else None,
        "decided_by": c.decided_by,
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "comment": c.comment,
        "blocked_reason": blocked_reason,
        "plan_excess_warning": plan_excess_warning,
        "checked": checked,
        "purchase": purchase_dict,
        "payments": payments_dict,
    }


async def _confirmation_to_dict(db: AsyncSession, c: PurchasePaidConfirmation, current_user) -> dict:
    """Одна строка (GET по закупке, ответ confirm/reject) — симулирует
    цепочку для pending, как и раньше. НЕ использовать в списке по субсидии
    (там N строк — батч без симуляции, см. _list_confirmation_dicts)."""
    p = await db.get(Purchase, c.purchase_id)
    contractor_name = None
    if p and p.contractor_id:
        contractor = await db.get(Contractor, p.contractor_id)
        contractor_name = contractor.name if contractor else None
    payments = []
    if p:
        payments = (await db.execute(
            select(Payment).where(
                Payment.purchase_id == p.id,
                Payment.confirmed_by_statement == True,  # noqa: E712
            ).order_by(Payment.payment_date)
        )).scalars().all()
    payments_dict = _confirmation_payments_dict(payments)

    # ВАЖНО: все нужные поля `p` читаются в purchase_dict ЗДЕСЬ, ДО вызова
    # _simulate_confirm_chain ниже — тот гоняет штатный переход внутри
    # SAVEPOINT прямо на этом же объекте `p` и откатывает его, из-за чего `p`
    # становится expired (см. докстринг _simulate_confirm_chain); обращаться
    # к p.* ПОСЛЕ него нельзя.
    purchase_dict = _build_purchase_dict(p, contractor_name) if p is not None else None

    # Согласующий видит ЗАРАНЕЕ, что confirm упрётся в гейт (например, нет
    # закрывающих документов) — «сухой» прогон той же цепочки, без записи.
    # Только для pending — решённым это уже не актуально, для них
    # plan_excess_warning читается из персистентной колонки (записана
    # РЕАЛЬНЫМ confirm в момент решения, если было обойдено превышение).
    # ВЫЗЫВАТЬ ПОСЛЕДНИМ (см. предупреждение выше) — после этого `p` expired.
    blocked_reason = None
    plan_excess_warning = c.plan_excess_warning
    checked = c.status != "pending"
    if p is not None and c.status == "pending":
        blocked_reason, plan_excess_warning = await _simulate_confirm_chain(db, p, current_user)
        checked = True

    return _base_confirmation_dict(
        c, purchase_dict, payments_dict,
        blocked_reason=blocked_reason, plan_excess_warning=plan_excess_warning, checked=checked,
    )


async def _list_confirmation_dicts(db: AsyncSession, rows: list[PurchasePaidConfirmation]) -> list[dict]:
    """Батч-версия для GET /api/subsidies/{id}/paid-confirmations — НИКОГДА
    не вызывает _simulate_confirm_chain (это и было причиной 40-60+ с на
    ~120 строках, см. докстринг модуля). Purchase/Contractor/Payment грузятся
    по ОДНОМУ select с IN на каждую таблицу, а не по строке (N+1). pending-
    строки отдаются с checked=false — фронт дозапрашивает проверку порциями
    через POST .../paid-confirmations/check."""
    purchase_ids = {c.purchase_id for c in rows}
    purchases: dict[int, Purchase] = {}
    if purchase_ids:
        purchases = {
            p.id: p for p in (await db.execute(
                select(Purchase).where(Purchase.id.in_(purchase_ids))
            )).scalars().all()
        }

    contractor_ids = {p.contractor_id for p in purchases.values() if p.contractor_id}
    contractor_names: dict[int, str] = {}
    if contractor_ids:
        contractor_names = {
            co.id: co.name for co in (await db.execute(
                select(Contractor).where(Contractor.id.in_(contractor_ids))
            )).scalars().all()
        }

    payments_by_purchase: dict[int, list[Payment]] = {pid: [] for pid in purchase_ids}
    if purchase_ids:
        all_payments = (await db.execute(
            select(Payment).where(
                Payment.purchase_id.in_(purchase_ids),
                Payment.confirmed_by_statement == True,  # noqa: E712
            ).order_by(Payment.payment_date)
        )).scalars().all()
        for pay in all_payments:
            payments_by_purchase.setdefault(pay.purchase_id, []).append(pay)

    items = []
    for c in rows:
        p = purchases.get(c.purchase_id)
        purchase_dict = _build_purchase_dict(p, contractor_names.get(p.contractor_id)) if p is not None else None
        payments_dict = _confirmation_payments_dict(payments_by_purchase.get(c.purchase_id, []))
        items.append(_base_confirmation_dict(
            c, purchase_dict, payments_dict,
            blocked_reason=None, plan_excess_warning=c.plan_excess_warning,
            checked=c.status != "pending",
        ))
    return items


@router.get("/api/subsidies/{subsidy_id}/paid-confirmations")
async def list_subsidy_paid_confirmations(
    subsidy_id: int,
    status: Optional[str] = Query("pending"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(subsidy_id, db)
    await _assert_can_decide(current_user, db, subsidy_id)

    q = select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.subsidy_id == subsidy_id)
    if status:
        q = q.where(PurchasePaidConfirmation.status == status)
    q = q.order_by(PurchasePaidConfirmation.requested_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return {"items": await _list_confirmation_dicts(db, rows)}


@router.get("/api/purchases/{pid}/paid-confirmation")
async def get_purchase_paid_confirmation(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Последний (по requested_at) запрос подтверждения для карточки закупки —
    null, если не было ни одного. Видимость — как у самой закупки (любой
    залогиненный с доступом к закупке; жёсткая проверка прав только на
    confirm/reject ниже)."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    row = (await db.execute(
        select(PurchasePaidConfirmation)
        .where(PurchasePaidConfirmation.purchase_id == pid)
        .order_by(PurchasePaidConfirmation.requested_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    return await _confirmation_to_dict(db, row, current_user)


class _RejectBody(BaseModel):
    comment: str


@router.post("/api/paid-confirmations/{confirmation_id}/confirm")
async def confirm_paid_confirmation(
    confirmation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    c = await db.get(PurchasePaidConfirmation, confirmation_id)
    if not c:
        raise HTTPException(404, "Запрос подтверждения не найден")
    if c.status != "pending":
        raise HTTPException(409, f"Запрос уже решён (статус «{c.status}»)")
    await _assert_can_decide(current_user, db, c.subsidy_id)

    result = await db.execute(
        select(Purchase)
        .where(Purchase.id == c.purchase_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    from app.services.purchase_payments import PAID_CONFIRMATION_ELIGIBLE_STATUSES
    if p.status not in PAID_CONFIRMATION_ELIGIBLE_STATUSES:
        raise HTTPException(
            409,
            f"Закупка больше не в статусе, из которого подтверждается оплата (сейчас «{p.status}») — "
            "подтверждение устарело, обновите список",
        )

    from app.routers.purchase_transitions import STATUS_LABELS
    from app.services.purchase_transition_core import _notify_status_change

    # Доработка приёмки (04.10, затем «confirm атомарен»): закупка может быть
    # на contracted/ordered, не только delivered — штатный переход не умеет
    # прыгать через гейты нескольких статусов разом, поэтому идём ПОШАГОВО.
    # Атомарность: commit=False/send_notification=False на каждом шаге — ни
    # один шаг НЕ коммитит и НЕ уведомляет (apply_purchase_status_transition.
    # commit() коммитит ВСЮ сессию целиком, а не только свою часть — проверено
    # эмпирически; значит нельзя коммитить раньше, чем прошла вся цепочка).
    # Если шаг заблокирован (чаще всего delivered — нет закрывающих
    # документов) — db.rollback() отменяет ВСЕ уже пройденные шаги разом
    # (ничего не было закоммичено), закупка остаётся как была, запрос pending,
    # 409 с причиной гейта. Если цепочка прошла целиком — ОДИН commit внизу, и
    # уведомления шлём ПОСЛЕ него, по одному на каждый реально пройденный шаг
    # (_notify_status_change — тот же текст/логика, что обычный ручной переход,
    # ПРАВИЛО №6, не вторая копия).
    # Владелец (доработка «оплата из выписки — факт»): превышение плана по
    # категории ФЭО НЕ блокирует confirm — _walk_to_paid идёт со
    # skip_plan_excess_gates=True (внутри), а тексты обойдённых гейтов
    # собираются сюда для plan_excess_warning (п.2 задачи).
    plan_excess_messages: list[str] = []
    visited, blocked = await _walk_to_paid(
        db, p, current_user, commit=False, send_notification=False,
        plan_excess_messages_out=plan_excess_messages,
    )
    if blocked is not None:
        await db.rollback()
        next_status, detail = blocked
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
        label = STATUS_LABELS.get(next_status, next_status)
        raise HTTPException(
            409,
            f"Нельзя перевести закупку в «{label}» для подтверждения оплаты: {message}",
        )

    c.status = "confirmed"
    c.decided_by = current_user.id
    c.plan_excess_warning = _format_plan_excess_warning(plan_excess_messages)
    from datetime import datetime, timezone
    c.decided_at = datetime.now(timezone.utc)
    await db.commit()

    for visited_status in visited:
        await _notify_status_change(p, p.id, visited_status, current_user, db)

    return await _confirmation_to_dict(db, c, current_user)


@router.post("/api/paid-confirmations/{confirmation_id}/reject")
async def reject_paid_confirmation(
    confirmation_id: int,
    body: _RejectBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    c = await db.get(PurchasePaidConfirmation, confirmation_id)
    if not c:
        raise HTTPException(404, "Запрос подтверждения не найден")
    if c.status != "pending":
        raise HTTPException(409, f"Запрос уже решён (статус «{c.status}»)")
    await _assert_can_decide(current_user, db, c.subsidy_id)
    if not body.comment or not body.comment.strip():
        raise HTTPException(422, "Укажите причину отклонения")

    # «Не та оплата» — отвязываем ВСЕ платежи-из-выписки этой закупки (тот же
    # штатный механизм откатa, что app/routers/bank_statements_registry.py::
    # unbind_bank_payment использует для одной строки — здесь нужно снять все,
    # т.к. именно их появление и подняло payment_amount до порога).
    from app.services.purchase_payments import recompute_purchase_payments

    payments = (await db.execute(
        select(Payment).where(
            Payment.purchase_id == c.purchase_id,
            Payment.confirmed_by_statement == True,  # noqa: E712
            Payment.bank_payment_id.isnot(None),
        )
    )).scalars().all()
    bank_payment_ids = {pay.bank_payment_id for pay in payments if pay.bank_payment_id}

    # Доработка плана 2026-10-04-fadm-statement: запомнить отклонённую пару
    # (эта закупка, эта строка выписки) — иначе следующий авто-match-payments
    # тут же снова привязал бы ту же строку и переоткрыл тот же запрос по кругу
    # (владелец, после первого прохода). Ручная привязка человеком через
    # attach-payments остаётся доступна — см. app/services/payment_lookup.py.
    from app.models.purchase_paid_confirmation_rejection import PurchasePaidConfirmationRejection
    for bp_id in bank_payment_ids:
        already = (await db.execute(
            select(PurchasePaidConfirmationRejection.id).where(
                PurchasePaidConfirmationRejection.purchase_id == c.purchase_id,
                PurchasePaidConfirmationRejection.bank_payment_id == bp_id,
            ).limit(1)
        )).scalar_one_or_none()
        if already is None:
            db.add(PurchasePaidConfirmationRejection(
                confirmation_id=c.id, purchase_id=c.purchase_id, bank_payment_id=bp_id,
            ))
    await db.flush()

    for pay in payments:
        await db.delete(pay)
    await db.flush()

    if bank_payment_ids:
        from app.models.bank_statement import BankPayment
        for bp_id in bank_payment_ids:
            bp = await db.get(BankPayment, bp_id)
            if bp is not None:
                # Если это была ЕДИНСТВЕННАЯ субсидия, матчившая эту строку —
                # matched_confirmed снимается; если строку уже использовала
                # (или использует) ещё одна субсидия по тому же соглашению
                # (bank_payment_subsidy_scope.py), оставляем True — там платёж
                # остаётся разнесённым правомерно.
                still_used = (await db.execute(
                    select(Payment.id).where(Payment.bank_payment_id == bp_id).limit(1)
                )).scalar_one_or_none()
                if still_used is None:
                    bp.matched_confirmed = False

    await recompute_purchase_payments(db, c.purchase_id)

    c.status = "rejected"
    c.decided_by = current_user.id
    c.comment = body.comment.strip()
    from datetime import datetime, timezone
    c.decided_at = datetime.now(timezone.utc)
    await db.commit()

    return await _confirmation_to_dict(db, c, current_user)
