"""wish_approval_ceiling_preview.py — предпросмотр жёсткого потолка субсидии
ДО нажатия «Согласовать» на заявке (владелец, 19.10.2026, решение по п.1
задания «заметнее»: согласующий обязан увидеть сумму превышения ДО решения,
не только после).

ПРАВИЛО №6 (один источник истины): формула потолка — ОДНА,
app.services.subsidy_ceiling.subsidy_ceiling_state (та же, что у плитки
«Запланировано», app.services.subsidy_money_summary, и у жёсткого гейта
перехода закупки, app.services.purchase_transition_core через
app.services.feo_plan_excess.assert_no_unapproved_excess). Этот модуль НЕ
пересчитывает «на сколько заявка нарастит план» второй формулой — вместо
этого реально выполняет РЕАЛЬНЫЙ путь создания закупок из заявки
(app.services.wish_distribution._distribute_wish_to_purchases — то же самое,
что произойдёт при настоящем согласовании) внутри SAVEPOINT с безусловным
откатом в finally. Тот же приём, что и app.services.subsidy_revision_preview
(apply_ops внутри db.begin_nested()).

Откат — ТОЛЬКО на уровне БД (SAVEPOINT); Python-атрибуты объекта `wish`,
изменённые внутри сухого прогона, после этого не трогаем и не используем —
вызывающий код (роутер) обязан просто вернуть результат, не продолжать
работу с тем же объектом `wish` в этом же запросе."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish import Wish
from app.models.user import User


async def preview_wish_approval_ceiling(db: AsyncSession, wish: Wish, current_user: User) -> dict:
    """Возвращает:
      {"applicable": bool,
       "subsidy_id": int | None, "subsidy_name": str | None,
       "ceiling": float | None,
       "total_plan_before": float | None, "total_plan_after": float | None,
       "over_amount": float,   # сколько план станет выше потолка ФЭО ПОСЛЕ этой заявки (0 — не станет)
       "error": str | None}

    applicable=False — превью нечего показать (у заявки нет субсидии, нет
    позиций, или по заявке уже есть закупки — повторное согласование уже
    изменённого плана этим превью не считается, достаточно уже существующего
    excess_warnings/plan_over_ceiling_amount плитки «Запланировано»), либо
    сухой прогон упал на каком-то гейте (error — текст причины, ТА ЖЕ, что
    покажет настоящее нажатие «Согласовать» — вторая формулировка не
    заводится): в обоих случаях согласование не блокируется этим эндпоинтом —
    он только читает, ничего не решает."""
    out: dict = {
        "applicable": False,
        "subsidy_id": wish.subsidy_id,
        "subsidy_name": None,
        "ceiling": None,
        "total_plan_before": None,
        "total_plan_after": None,
        "over_amount": 0.0,
        "error": None,
    }
    if not wish.subsidy_id or not wish.items:
        return out

    from app.models.purchase import Purchase
    from sqlalchemy import select
    existing = (await db.execute(
        select(Purchase.id).where(Purchase.wish_id == wish.id).limit(1)
    )).scalar()
    if existing is not None:
        return out

    from app.services.feo_plan_tree import compute_feo_plan_tree
    from app.services.subsidy_ceiling import subsidy_ceiling_state
    from app.models.subsidy import Subsidy

    subsidy_row = await db.get(Subsidy, wish.subsidy_id)
    out["subsidy_name"] = subsidy_row.name if subsidy_row else f"#{wish.subsidy_id}"

    tree_before = await compute_feo_plan_tree(db, [wish.subsidy_id])
    state_before = await subsidy_ceiling_state(db, wish.subsidy_id, tree=tree_before)
    out["total_plan_before"] = state_before["total_plan"]
    out["ceiling"] = state_before["ceiling"]

    nested = await db.begin_nested()
    try:
        from app.services.wish_distribution import _distribute_wish_to_purchases
        await _distribute_wish_to_purchases(wish, db, current_user, split=False)
        tree_after = await compute_feo_plan_tree(db, [wish.subsidy_id])
        state_after = await subsidy_ceiling_state(db, wish.subsidy_id, tree=tree_after)
        out["total_plan_after"] = state_after["total_plan"]
        out["ceiling"] = state_after["ceiling"]
        out["over_amount"] = state_after["over_amount"]
        out["applicable"] = True
    except HTTPException as e:
        detail = e.detail
        out["error"] = detail.get("message") if isinstance(detail, dict) else str(detail)
    except Exception as e:  # сухой прогон не должен ронять ответ превью
        out["error"] = str(e)
    finally:
        await nested.rollback()

    return out
