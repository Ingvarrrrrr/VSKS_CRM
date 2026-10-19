"""purchase_ceiling_block.py — значок «закупка стоит: план субсидии выше
потолка ФЭО» на карточке/в списке закупок (владелец, 19.10.2026, решение по
жёсткому потолку субсидии, п.2 задания «заметнее»).

ПРАВИЛО №6 (один источник истины): сумма превышения — ТА ЖЕ, что у плитки
«Запланировано» (app.services.subsidy_money_summary::plan_over_ceiling_amount),
которая считается через app.services.subsidy_ceiling.subsidy_ceiling_state
(жёсткий потолок ФЭО по субсидии целиком, НЕ по категории — см. докстринг
того модуля). Эта функция формулу потолка повторно не пишет — только зовёт
subsidy_ceiling_state на каждую субсидию, затронутую списком закупок (batch,
без N+1 — тот же общий tree на все субсидии страницы, если он уже посчитан
вызывающим кодом), и решает, актуален ли значок для КОНКРЕТНОЙ закупки.

Значок актуален, только пока закупка ещё НЕ прошла стадию, на которой
app.services.purchase_transition_core вызывает жёсткий гейт (переход вперёд,
target_idx > current_idx, уже на статусе 'contracted' и позже гейт отработал
при входе в него) — т.е. для статусов 'wishes'/'plan_schedule'/
'work_in_progress': именно они «стоят» (не могут продвинуться), пока план
субсидии выше потолка."""
from sqlalchemy.ext.asyncio import AsyncSession

# Статусы ДО «Заключён договор» (включая авансовый 'wishes') — именно на них
# закупка «стоит», потому что следующий forward-переход упрётся в
# assert_subsidy_ceiling. Начиная с 'contracted' закупка этот гейт уже
# прошла — значок ей не нужен (её дальнейшие переходы обычный факт/оплата,
# не рост плана). Публичное имя (без подчёркивания) — app.routers.purchases
# использует его, чтобы построить ЗАУЖЕННОЕ дерево ФЭО только по субсидиям
# этих статусов (перф 20.10.2026, см. комментарий в list_purchases), не по
# всем субсидиям страницы.
PRE_CONTRACT_STATUSES = {"wishes", "plan_schedule", "work_in_progress"}

_EMPTY = {"ceiling_blocked": False, "ceiling_over_amount": None}


async def compute_purchase_ceiling_block(
    db: AsyncSession, purchases: list, tree: dict | None = None,
) -> dict:
    """Возвращает {purchase_id: {"ceiling_blocked": bool, "ceiling_over_amount": float | None}}
    на КАЖДУЮ закупку из `purchases`. `tree` — опционально уже посчитанный
    compute_feo_plan_tree(db, subsidy_ids) этого же запроса на ВСЕ субсидии
    страницы/карточки (ПРАВИЛО №6 — второй раз дерево не строим, если
    вызывающий код его уже построил; без аргумента subsidy_ceiling_state
    построит его сама на каждую субсидию по отдельности)."""
    result: dict = {p.id: dict(_EMPTY) for p in purchases}
    candidates = [p for p in purchases if p.subsidy_id and p.status in PRE_CONTRACT_STATUSES]
    if not candidates:
        return result

    subsidy_ids = sorted({p.subsidy_id for p in candidates})
    from app.services.subsidy_ceiling import subsidy_ceiling_state

    state_by_subsidy: dict[int, dict] = {}
    for sid in subsidy_ids:
        state_by_subsidy[sid] = await subsidy_ceiling_state(db, sid, tree=tree)

    for p in candidates:
        state = state_by_subsidy.get(p.subsidy_id) or {}
        over = float(state.get("over_amount") or 0.0)
        if over > 0:
            result[p.id] = {"ceiling_blocked": True, "ceiling_over_amount": over}
    return result
