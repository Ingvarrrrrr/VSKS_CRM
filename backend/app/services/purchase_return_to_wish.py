"""Единый хелпер «вернуть закупку в заявку» — текст следствий и допустимость.

Правило №6: и GET /api/purchases/{id}/return-to-wish/preview (фронт показывает
предупреждение ДО вызова), и POST .../return-to-wish (сама операция) читают
allowed/reason/consequences ИЗ ОДНОГО МЕСТА — тексты не дублируются между
предпросмотром и телом ответа мутации.

Решение владельца (21.09, corrections-21-09.md W3): третий вариант работы с
дублями строк ТЗ — «ошибка, вернуть на доработку» — закупка уходит обратно во
«Заявки», согласование закупки сбрасывается, заявка-источник помечается
'rejected' (та же семантика, что обычное отклонение заявки согласующим, см.
app/routers/wish_transitions.py::reject_wish).
"""
from app.models.purchase import Purchase

# Разрешённые стадии закупки для возврата в заявку — сознательно ШИРЕ, чем
# app.services.wish_distribution._withdraw_wish_from_plan (тот блокирует всё
# после plan_schedule): здесь владелец явно допустил ещё и work_in_progress,
# это отдельная операция уровня закупки, а не отзыв заявки целиком.
ALLOWED_STATUSES: tuple[str, ...] = ("plan_schedule", "work_in_progress")


def compute_return_to_wish_preview(p: Purchase) -> dict:
    """Возвращает {consequences: [...], allowed: bool, reason: str|None}."""
    if not p.wish_id:
        return {
            "consequences": [],
            "allowed": False,
            "reason": "У закупки нет исходной заявки — вернуть её в «Заявки» нельзя.",
        }
    if p.status not in ALLOWED_STATUSES:
        # Ленивый импорт — избегаем цикла purchases.py → purchase_return.py →
        # purchase_return_to_wish.py → purchase_transitions.py → purchases.py
        # (тот же приём, что app.services.wish_distribution._withdraw_wish_from_plan
        # применяет к своим циклическим импортам роутеров).
        from app.routers.purchase_transitions import STATUS_LABELS
        label = STATUS_LABELS.get(p.status, p.status)
        return {
            "consequences": [],
            "allowed": False,
            "reason": (
                f"Закупку на стадии «{label}» нельзя вернуть в заявку — "
                "доступно только для «План закупок» и «Ведётся работа»."
            ),
        }
    return {
        "consequences": [
            "Закупка вернётся в раздел «Заявки» (статус «Заявка»).",
            "Согласование закупки будет сброшено — потребуется пройти заново.",
            "Заявка-источник будет отмечена «На доработке» с указанной вами причиной.",
            "Инициатору заявки придёт уведомление.",
        ],
        "allowed": True,
        "reason": None,
    }
