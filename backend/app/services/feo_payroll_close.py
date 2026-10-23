"""feo_payroll_close.py — «Закрыть ФОТ по статье» (владелец, 22.10.2026, план
humble-stirring-emerson.md, шаг 1, вариант (в)).

Повод: шаг 1 этого же плана защищает статьи ФОТ от замещения «заказ вместо
плана» (feo_plan_common._order_substituted_plan(is_payroll=True)) — пока
зарплата/отчисления/командировочные не выплачены ПОЛНОСТЬЮ, их план
НЕ становится «экономией». Но когда владелец САМ решил, что по этой статье
больше ничего не будет (год закрыт, остаток реально свободен) — нужен способ
снять защиту ИМЕННО с этой статьи, одной кнопкой, с историей «кто/когда/
сколько высвободил». «Отменить закрытие» возвращает защиту (план снова
полный, невыплаченный остаток снова входит в «Запланировано»/«Можно
перераспределить» строкой «ФОТ»).

Технически — FeoCategory.payroll_closed (True = защита снята для ЭТОЙ
статьи, compute_feo_plan_tree/_payroll_block_ids читает его САМ, ПРАВИЛО №6
— вторая формула plan НЕ пишется здесь, функция ниже только переключает флаг
и считает «сколько изменилось» ДВУМЯ вызовами ОДНОГО source of truth
(compute_feo_plan_tree) — до и после переключения, в той же транзакции).

История — существующий механизм app.services.feo_history (entity_changes),
ПРАВИЛО №6, вторая таблица не заводится."""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services import feo_history


async def _own_plan_amount(db: AsyncSession, cat: FeoCategory) -> float:
    """node['plan'] ТОЛЬКО этой статьи (compute_feo_plan_tree, ПРАВИЛО №6) —
    используется ДО и ПОСЛЕ переключения payroll_closed, чтобы посчитать
    «сколько высвобождено»/«сколько вернулось в план» без переизобретения
    формулы замещения здесь."""
    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    node = tree.get(cat.id)
    return float(node.get("plan", 0.0)) if node else 0.0


async def is_effectively_payroll(db: AsyncSession, cat: FeoCategory) -> bool:
    """Статья ФОТ эффективно (своя или ЛЮБОЙ предок) — ЕДИНЫЙ резолвер
    app.services.feo_payroll.payroll_category_ids (ПРАВИЛО №6)."""
    from app.services.feo_payroll import payroll_category_ids
    ids = await payroll_category_ids(db, [cat.subsidy_id])
    return cat.id in ids


async def set_payroll_closed(
    db: AsyncSession, user, cat: FeoCategory, closed: bool,
) -> dict:
    """Переключает FeoCategory.payroll_closed, пишет историю, возвращает
    {old_plan, new_plan, delta} — delta>0 при закрытии (план статьи упал,
    разница ушла в «Свободно»), delta<0 при «Отменить закрытие» (защита
    вернулась, план снова вырос). Не коммитит — вызывающий роутер коммитит
    сам (как и остальные write-эндпоинты feo_categories/feo_tree_ops)."""
    if bool(cat.payroll_closed) == bool(closed):
        old_plan = await _own_plan_amount(db, cat)
        return {"old_plan": old_plan, "new_plan": old_plan, "delta": 0.0}

    old_plan = await _own_plan_amount(db, cat)
    old_values = {
        "payroll_closed": str(cat.payroll_closed),
        "plan_amount": f"{old_plan:.2f}",
    }

    cat.payroll_closed = closed
    cat.payroll_closed_by_user_id = getattr(user, "id", None) if closed else None
    from datetime import datetime, timezone
    cat.payroll_closed_at = datetime.now(timezone.utc) if closed else None
    await db.flush()

    new_plan = await _own_plan_amount(db, cat)
    new_values = {
        "payroll_closed": str(closed),
        "plan_amount": f"{new_plan:.2f}",
    }

    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_CATEGORY, cat.id, user,
        old_values, new_values, source=feo_history.SOURCE_MANUAL, commit=False,
    )
    return {"old_plan": old_plan, "new_plan": new_plan, "delta": old_plan - new_plan}
