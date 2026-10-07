"""wish_tz_warnings.py — НЕблокирующее предупреждение «ТЗ позиции заявки дороже
её плановой позиции (FeoPlannedItem)» для карточки заявки (GET/PUT /api/wishes/{id}).

Владелец, 06.10.2026 (заявка №115, автор-исполнитель Цокало, статус rejected,
позиции 482 350 ₽ в категории ФЭО id 3699 при плане категории 254 046 ₽): «На
этапе Заявки превышение НЕ блокируется. Исполнитель должен мочь сохранить и
отправить заявку. Согласующий решает — согласует или перераспределит. Внутри
заявка обо всём кричит и говорит, что всё плохо — согласуй».

ПРАВИЛО №6 (один источник истины) — здесь НЕ заводится вторая формула
сравнения ТЗ с планом: единственный источник —
app.services.tz_excess_approval.collect_tz_over_plan_violations, та же
функция, которой уже пользуются согласование (wish_approvals.py) и конвертация
(wish_convert.py/wish_distribution.py) заявки для РЕГИСТРАЦИИ запроса на
согласование превышения. Этот модуль только ЧИТАЕТ её результат и приводит к
виду, удобному для карточки (резолвит имя категории ФЭО) — ничего не
регистрирует и не блокирует.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish import Wish
from app.services.tz_excess_approval import collect_tz_over_plan_violations

# Статусы заявки, для которых предупреждение не показываем — заявка уже
# ушла в закупку ('converted'), свои собственные контроли превышения там
# есть на уровне закупки (assert_no_pending_tz_excess и т.п.), дублировать
# смысла нет. Отдельного статуса 'cancelled' у Wish (в отличие от Purchase)
# нет (см. app/models/wish.py) — оставлено на случай, если он появится.
_NO_WARNING_STATUSES = {"converted", "cancelled"}


async def wish_tz_over_plan_warnings(db: AsyncSession, wish: Wish) -> list[dict]:
    """Список {item_name, feo_category_id, category_name, excess_amount, message}
    по позициям заявки, чья ТЗ-сумма превышает её плановую позицию (или план
    категории, если позиция ещё ни к какой плановой строке не привязана).

    Пустой список — превышений нет (или заявка уже в статусе, где
    предупреждение не показывается)."""
    if getattr(wish, "status", None) in _NO_WARNING_STATUSES:
        return []

    items = list(wish.items or [])
    if not items:
        return []

    violations = await collect_tz_over_plan_violations(
        db, items, fallback_category_id=getattr(wish, "feo_category_id", None),
    )
    if not violations:
        return []

    cat_ids = {v["feo_category_id"] for v in violations if v.get("feo_category_id")}
    cat_names: dict[int, str] = {}
    if cat_ids:
        from app.models.feo_category import FeoCategory

        for cid in cat_ids:
            cat = await db.get(FeoCategory, cid)
            cat_names[cid] = cat.name if cat else f"#{cid}"

    return [
        {
            "item_name": v["item_name"],
            "feo_category_id": v.get("feo_category_id"),
            "category_name": cat_names.get(v.get("feo_category_id"), ""),
            "excess_amount": v["excess_amount"],
            "message": v["message"],
            # reason (задача «превышение 0 ₽», владелец 07.10.2026) — текст
            # нарушенных величин («цена за единицу: план X, указано Y...»)
            # БЕЗ хвоста «Измените плановую позицию…» — карточка заявки
            # показывает его, когда excess_amount по сумме равен 0 (нарушено
            # количество или цена за единицу, а не сумма).
            "reason": v.get("reason", ""),
        }
        for v in violations
    ]
