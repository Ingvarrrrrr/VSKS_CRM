"""Финальное решение директора по авансовому отчёту: «Оплачено» / «Отказать
в оплате» — шаг 6 плана .planning/quick/2026-10-02-money-redistribution/PLAN.md
(вариант Б).

Владелец (02.10.2026): «До директора авансовый может долго доходить, и он
вообще не занимается финансированием. Начальник отдела и бухгалтер решают по
цепочке согласования заявки (см. app/routers/wish_approvals.py — переиспользуем
её как есть, ПРАВИЛО №6, второй цепочки не заводим). Директор, взвесив все за
и против, решит платить или нет — это будет в САМОМ КОНЦЕ, на стадии
"Поставлено, не оплачено", и на бумаге его подпись, т.к. ЭЦП пока не привязана
к проекту».

Право нажимать обе кнопки — ОДНА галочка-permission ('advance_payment_decision'),
не хардкод ролей (см. ПРАВИЛО проекта о правах через галочки). Дефолт
(app/startup/permission_seeds.py::_advance_payment_decision_action) зеркалит
роли, которым и так разрешено двигать статус закупки в 'paid' —
'purchase.status_change' (admin/org_admin/manager/account_owner/superadmin=True,
employee=False), см. app/routers/purchase_transitions.py::TRANSITION_REQUIRED.

Запись решения — ОТДЕЛЬНАЯ сущность, как просил владелец («кто, когда, решение,
основание»), но НЕ новая таблица: ПРАВИЛО №6 — на закупке уже есть журнал
переходов статуса PurchaseEvent (purchase_id, user_id, event_type, data JSONB,
created_at с server_default=now()) — тот же, которым
app/services/purchase_transition_core.py пишет event_type='status_changed'.
Новый event_type='advance_payment_decision' даёт нужные "кто"(user_id)/
"когда"(created_at)/"решение"+"основание"(data).

НА БУДУЩЕЕ (владелец, раздел PLAN.md «На будущее», сейчас НЕ делать): когда
ЭЦП будет привязана к проекту, подписанный документ и результат проверки
подписи лягут ДОПОЛНИТЕЛЬНЫМИ ключами в data этого же PurchaseEvent (например
data['signature'] = {...}) — запись решения уже отдельная сущность с
произвольным JSONB, под подпись НЕ потребуется ни вторая таблица, ни миграция.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import get_effective_actions, _active_org

ACTION_KEY = "advance_payment_decision"

# Решения, которые умеет фиксировать запись (см. record_advance_payment_decision).
DECISION_PAID = "paid"
DECISION_REFUSED = "refused"


async def assert_can_decide_advance_payment(current_user, db: AsyncSession) -> None:
    """403, если у current_user нет права 'advance_payment_decision'.

    superadmin обходит любые action-гейты (см. require_action/ require_tab —
    тот же принцип здесь, без заведения второй проверки). Остальным — ТОЛЬКО
    через явную галочку: умышленно НЕ используем can_manage_purchase/
    is_advance_owner-bypass (app/auth/permissions.py, app/routers/
    purchase_transitions.py) — тот бы разрешил автору авансового решить
    за директора вопрос оплаты своего же отчёта, что прямо противоречит
    задаче владельца (директор — отдельное лицо, не автор и не согласующий).
    """
    if current_user.role == "superadmin":
        return
    actions = await get_effective_actions(current_user, db, _active_org(current_user))
    if ACTION_KEY not in actions:
        raise HTTPException(
            403,
            f"Нет разрешения «Решение по оплате авансового отчёта» ({ACTION_KEY}) — "
            "обратитесь к администратору организации.",
        )


async def record_advance_payment_decision(
    db: AsyncSession,
    purchase,
    current_user,
    decision: str,
    comment: Optional[str] = None,
) -> None:
    """Пишет PurchaseEvent(event_type='advance_payment_decision') — кто решил
    (user_id), когда (created_at), что решил (data.decision) и основание
    (data.comment — «подпись на бумаге», номер акта и т.п.).

    Коммитит сам (вызывается уже ПОСЛЕ смены статуса/остановки закупки,
    которые коммитят свою часть отдельно — см. вызывающий код в
    purchase_transitions.py/purchase_stop.py)."""
    from app.models.purchase_event import PurchaseEvent

    db.add(PurchaseEvent(
        purchase_id=purchase.id,
        user_id=getattr(current_user, "id", None),
        event_type="advance_payment_decision",
        data={"decision": decision, "comment": comment},
    ))
    await db.commit()
