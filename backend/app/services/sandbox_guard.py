"""«Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б):
закупки песочницы (subsidies.is_sandbox=true) не должны слать уведомления и
заводить напоминания о дедлайнах — это эксперимент, а не реальная работа.

notifications.py НЕ трогаем (правит параллельная сессия) — гейт ставится в
точках вызова notify_*, см. вызывающих этого модуля: routers/purchase_approvals.py,
routers/purchase_members.py, services/purchase_transition_core.py,
background/deadline_reminders.py.

Один предикат (ПРАВИЛО №6) — не плодить вторую проверку is_sandbox по месту.
"""
from __future__ import annotations

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession


async def purchase_is_sandbox(db: AsyncSession, purchase) -> bool:
    """True, если закупка принадлежит субсидии-песочнице (копии для
    экспериментов) — её уведомления/задачи должны молчать."""
    subsidy_id = getattr(purchase, "subsidy_id", None)
    if not subsidy_id:
        return False
    from app.models.subsidy import Subsidy
    val = (await db.execute(
        select(Subsidy.is_sandbox).where(Subsidy.id == subsidy_id)
    )).scalar_one_or_none()
    return bool(val)


def not_sandbox_subsidy_ids(explicit_ids=None):
    """Подзапрос id субсидий, которые ПОКАЗЫВАЮТСЯ в агрегате: не-песочница,
    ПЛЮС (если передан explicit_ids) любая субсидия, явно запрошенная
    вызывающим — даже если она песочница.

    Правило владельца (план breezy-mixing-lovelace.md, Часть Б, правка после
    регрессии): «В самой субсидии-копии все цифры считаются как обычно» —
    песочницу исключать ТОЛЬКО когда запрос НЕ ограничен явно конкретными
    субсидиями (агрегат по множеству/всем видимым). Если запрос явно указывает
    subsidy_id (или список), включающий песочную субсидию — например, карточка
    самой копии дёргает дашборд-виджет с ?subsidy_id=<копия> — её закупки
    ДОЛЖНЫ учитываться, иначе виджет покажет 0 внутри собственной карточки
    копии.

    explicit_ids — id субсидий, явно запрошенных ПОЛЬЗОВАТЕЛЕМ через query-
    параметр (subsidy_id/subsidy_ids конкретного эндпоинта), а НЕ видимость
    (get_visible_subsidy_ids — тот список может включать сотни субсидий,
    видимых пользователю, это НЕ то же самое, что «явно запрошено»).

    ЕДИНЫЙ предикат (ПРАВИЛО №6) для итогов дашборда/аккаунта — переиспользуется
    во ВСЕХ агрегатах по нескольким субсидиям: routers/dashboard.py
    (_apply_purchase_org_filter), dashboard_charts.py (subsidy_q/feo_planned_q/
    contract_single_q/contract_fc_q/mp_q), dashboard_analytics.py (_pf/pf_q/
    economy-by-method), dashboard_type_drill.py и dashboard_financial_plan*.py
    (оба идут через _apply_purchase_org_filter, см. dashboard.py). Страница
    «Субсидии» (scope=managed) эту функцию НЕ зовёт — там копия должна
    оставаться видимой, иначе ею нечем управлять.

    .in_(not_sandbox_subsidy_ids()) на колонке subsidy_id — не на самой
    таблице Subsidy, поэтому возвращаем подзапрос id, а не булево выражение.
    """
    from app.models.subsidy import Subsidy
    if explicit_ids:
        return select(Subsidy.id).where(
            or_(Subsidy.is_sandbox == False, Subsidy.id.in_(explicit_ids))  # noqa: E712
        )
    return select(Subsidy.id).where(Subsidy.is_sandbox == False)  # noqa: E712


def sandbox_contract_clause():
    """Клауза «этот Contract принадлежит песочнице» — для query, где Contract
    уже есть в FROM (app.models.contract.Contract должен быть импортирован
    вызывающим; здесь не импортируем модель Contract напрямую, чтобы не
    создавать лишнюю связь импортов — клауза строится по *значению* колонки,
    переданной вызывающим, см. ниже).

    Договор считается принадлежащим песочнице, если:
      1) его собственный subsidy_id указывает на is_sandbox-субсидию, ИЛИ
      2) хотя бы одна закупка ссылается на него (Purchase.contract_id), и
         ВСЕ такие закупки — закупки песочных субсидий (ни одна настоящая
         закупка на него не ссылается).

    Используется ensure_contract_linked (services/contracts_linking.py) —
    настоящая закупка не должна находить (и дописывать) договор, который
    на самом деле принадлежит чьей-то копии-песочнице; обратное (чем именно
    может пользоваться сама закупка-песочница) см. sandbox_own_contract_clause().
    ПРАВИЛО №6 — один предикат, не вторая реализация по месту.
    """
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase
    from app.models.contract import Contract

    sandbox_subsidy_ids = select(Subsidy.id).where(Subsidy.is_sandbox == True)  # noqa: E712
    non_sandbox_purchase_contract_ids = select(Purchase.contract_id).where(
        Purchase.contract_id.isnot(None),
        or_(Purchase.subsidy_id.is_(None), Purchase.subsidy_id.notin_(sandbox_subsidy_ids)),
    )
    any_purchase_contract_ids = select(Purchase.contract_id).where(Purchase.contract_id.isnot(None))

    return or_(
        Contract.subsidy_id.in_(sandbox_subsidy_ids),
        and_(
            Contract.id.in_(any_purchase_contract_ids),
            Contract.id.notin_(non_sandbox_purchase_contract_ids),
        ),
    )


def sandbox_own_contract_clause(subsidy_id: int):
    """Клауза «этот Contract — свой для закупки песочницы subsidy_id»: либо
    его собственный subsidy_id указывает ровно на эту песочницу, либо на него
    ссылается (Purchase.contract_id) хотя бы одна закупка ЭТОЙ ЖЕ песочницы.
    Пара к sandbox_contract_clause() — закупка-песочница ищет договор ТОЛЬКО
    среди таких, не среди договоров оригинала или других песочниц."""
    from app.models.purchase import Purchase
    from app.models.contract import Contract

    return or_(
        Contract.subsidy_id == subsidy_id,
        Contract.id.in_(select(Purchase.contract_id).where(
            Purchase.subsidy_id == subsidy_id, Purchase.contract_id.isnot(None),
        )),
    )
