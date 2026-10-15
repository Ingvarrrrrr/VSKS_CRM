"""subsidy_ceiling.py — жёсткий потолок субсидии (план по ФЭО не выше потолка).

Вынесено из app.services.feo_plan_excess.assert_no_unapproved_excess (задача
владельца 15.10.2026, ПРАВИЛО №6 — один источник истины): раньше потолок
проверялся ТОЛЬКО там, но ручная ручка согласования превышения
(app.routers.plan_excess — POST "" и POST "/{id}/decide") его не проверяла
вовсе — владелец 15.10.2026 согласовал превышение «услуги» 40 730 ₽, хотя план
субсидии «ФАДМ 2026_3» уже был выше потолка ФЭО (15 920 830 > 15 880 100).

Формула (ceiling, total_plan, entered_node_ids) — ОДНА, из
app.services.subsidy_budget.feo_entered_ceiling_and_plan (та же, что и
app.services.feo_tree_write.align_budget_to_plan использует, решение владельца
07.10.2026). Эта функция здесь НЕ пересчитывает ceiling/total_plan заново —
только оборачивает feo_entered_ceiling_and_plan числом adding_amount и текстом
ошибки, который был раньше внутри assert_no_unapproved_excess дословно (текст
и код ответа 409 PLAN_OVER_SUBSIDY_CEILING не меняются).

Задача владельца п.3 (2026-08-12, «жёсткий потолок»): «общий план по всем
подкатегориям не должен превышать общую сумму ФЭО — критично, ни при каких
обстоятельствах». НЕ участвует в согласовании через PlanExcessApproval вообще
— ни admin_override, ни обход для OWNER_ROLES.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feo_plan_tree import compute_feo_plan_tree


async def subsidy_ceiling_state(
    db: AsyncSession,
    subsidy_id: int,
    tree: dict | None = None,
    feo_category_id: int | None = None,
    adding_amount: Decimal | float = Decimal("0"),
) -> dict:
    """Числа потолка БЕЗ исключения — {ceiling, total_plan, over_amount}.
    over_amount > 0 означает, что план (с учётом adding_amount) превышает
    потолок финансирования по ФЭО субсидии.

    tree — уже посчитанный compute_feo_plan_tree(db, [subsidy_id]) того же
    вызова (если нет — считается здесь). feo_category_id — узел, на который
    совершается adding_amount: adding_amount применяется к total_plan ТОЛЬКО
    если его поддерево входит в один из «верхних введённых» узлов (см.
    докстринг feo_entered_ceiling_and_plan); без feo_category_id (ручной
    запрос/решение согласования — там действие не добавляет план, а лишь
    согласует уже существующий) adding_amount по умолчанию 0 и применяется
    безусловно."""
    if tree is None:
        tree = await compute_feo_plan_tree(db, [subsidy_id])

    from app.services.subsidy_budget import feo_entered_ceiling_and_plan
    ceiling, total_plan_now, entered_node_ids = await feo_entered_ceiling_and_plan(db, subsidy_id, tree)

    _adding = Decimal(str(adding_amount))
    if feo_category_id is not None and _adding != 0:
        # adding_amount прибавляется к total_plan_now ТОЛЬКО если категория,
        # на которую совершается действие, сама лежит в поддереве одного из
        # «верхних введённых» узлов (себя или предка) — иначе её поддерево и
        # так не участвует ни в одной из сторон сравнения.
        _node_id = feo_category_id
        _in_counted_subtree = _node_id in entered_node_ids
        while not _in_counted_subtree:
            _parent_id = (tree.get(_node_id) or {}).get("parent_id")
            if _parent_id is None:
                break
            _node_id = _parent_id
            _in_counted_subtree = _node_id in entered_node_ids
        if not _in_counted_subtree:
            _adding = Decimal("0")

    total_plan_after_d = Decimal(str(total_plan_now)) + _adding
    ceiling_d = Decimal(str(ceiling or 0))
    over_d = total_plan_after_d - ceiling_d
    if ceiling_d <= 0 or over_d <= Decimal("0.005"):
        over_d = Decimal("0")
    return {
        "ceiling": float(ceiling_d),
        "total_plan": float(total_plan_after_d),
        "over_amount": float(over_d),
    }


async def assert_subsidy_ceiling(
    db: AsyncSession,
    subsidy_id: int,
    tree: dict | None = None,
    feo_category_id: int | None = None,
    adding_amount: Decimal | float = Decimal("0"),
) -> None:
    """Бросает HTTPException 409 PLAN_OVER_SUBSIDY_CEILING, если план субсидии
    (с учётом adding_amount) превышает жёсткий потолок ФЭО. См. docstring
    модуля и subsidy_ceiling_state. Текст и код ответа — дословно те же, что
    были раньше внутри app.services.feo_plan_excess.assert_no_unapproved_excess
    (эта функция вызывается оттуда и ничего в её поведении не меняет)."""
    state = await subsidy_ceiling_state(
        db, subsidy_id, tree=tree, feo_category_id=feo_category_id, adding_amount=adding_amount,
    )
    if state["over_amount"] <= 0:
        return

    from app.models.subsidy import Subsidy
    from app.services.documents.formatting import _fmt_money as _fmt_rub_num

    subsidy_row = await db.get(Subsidy, subsidy_id)
    subsidy_name = subsidy_row.name if subsidy_row else f"#{subsidy_id}"
    total_plan_after_d = Decimal(str(state["total_plan"]))
    ceiling_d = Decimal(str(state["ceiling"]))
    over_d = Decimal(str(state["over_amount"]))
    raise HTTPException(
        409,
        {
            "code": "PLAN_OVER_SUBSIDY_CEILING",
            "message": (
                f"Жёсткий потолок ФЭО по субсидии «{subsidy_name}»: всего запланировано "
                f"{_fmt_rub_num(total_plan_after_d)} ₽, финансирование по ФЭО (потолок) "
                f"{_fmt_rub_num(ceiling_d)} ₽, превышение {_fmt_rub_num(over_d)} ₽. Это "
                f"ограничение НЕ согласуется ни при каких обстоятельствах — уменьшите план "
                f"по какой-либо подкатегории минимум на {_fmt_rub_num(over_d)} ₽."
            ),
            "subsidy_id": subsidy_id,
            "total_plan": float(total_plan_after_d),
            "ceiling": float(ceiling_d),
            "over_amount": float(over_d),
        },
    )
