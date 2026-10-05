"""stage_cumulative.py — решение владельца 05.10.2026: карточки этапов
«Заключён договор / Заказано / Поставлено / Оплачено» считаются НАКОПИТЕЛЬНО
для ВСЕХ закупок: «Заключён договор» ⊇ «Заказано» ⊇ «Поставлено» ⊇ «Оплачено»
(минус оплаченные авансом и ещё не поставленные) — ПО ПОСТРОЕНИЮ, не
постфактум-проверкой (см. tests/test_stage_cumulative_contractless.py::
test_contracted_ge_ordered_ge_delivered_invariant).

«Заказано»/«Поставлено»/«Оплачено» уже были накопительными в
dashboard_charts.py (widget.ordered включает delivered+paid, widget.delivered
включает paid, paid_declared/paid_confirmed — app/services/subsidy_paid_
breakdown.py, по отметке/выписке независимо от статуса) — не трогаем,
ПРАВИЛО №6, не второй расчёт.

Разрыв (владелец, правка 05.10.2026 после находки «на стенде Заключён
19,05М < Заказано 22,2М») — «Заключён договор» (widget.contracts/
contracts_map в dashboard_charts.py) строился ТОЛЬКО по записям Contract со
status='active' (contract_single_q/contract_fc_q), ДВЕ независимые причины
разрыва на практике (проверено живыми данными стенда, субсидия «ХО»,
id=75):

  1. committed-закупка (committed_status_predicate) НЕ подкреплена активной
     записью Contract нужного типа вовсе — contract_id IS NULL, контракт
     удалён/неактивен, либо contract_type не один из трёх распознаваемых
     (single/framework_with_amount/framework_cumulative). Функция
     committed_uncounted_by_subsidy() ниже — добавочное слагаемое, Σ
     effective_amount_expr() по таким закупкам.

  2. РЕАЛЬНАЯ причина основного разрыва на «ХО»: Contract.contract_type=
     'single', status='active' (контракт СУЩЕСТВУЕТ и формально учтён
     cs_rows), но Contract.max_amount IS NULL (поле не заполнено при
     создании) — cs_rows прежде складывал `Contract.max_amount` буквально,
     SQL SUM игнорирует NULL-строки, поэтому ВСЕ 16 single-договоров «ХО» (их
     закупки на 4 777 721,20 ₽ суммарно) давали 0 в «Заключено договоров»,
     хотя эти же закупки честно входили в «Заказано»/«Поставлено»/
     «Оплачено» по статусу. single_contract_topup_by_subsidy() ниже чинит
     это ТЕМ ЖЕ приёмом, что уже применён к framework_with_amount в
     dashboard_charts.py (`greatest(max_amount, Σ реальных закупок)`,
     _fwa_children_sum) — единственное отличие: здесь считается ДОБАВКА
     (актуальная Σ минус уже учтённый max_amount, не ниже 0), а не замена
     формулы cs_rows целиком (Правило №6 — не переписываем cs_rows второй
     раз, только досчитываем недостающее тем же принципом «максимум из
     двух оценок»).

committed_uncounted_by_subsidy() и single_contract_topup_by_subsidy() вместе
гарантируют «Заключён договор» ⊇ Σ по всем committed-закупкам ПО
ПОСТРОЕНИЮ: либо закупка уже учтена активным Contract известного типа с
реальным max_amount/Σ заказов (cs_rows/cfc_rows), либо она попадает в одну
из этих двух добавок. Двойного счёта нет: committed_uncounted_expr()
намеренно исключает контракты, УЖЕ учтённые (active + известный тип), а
топ-ап считает РАЗНИЦУ (actual − recorded), не Σ заново.

Сумма — effective_amount_expr() (та же величина, что остальные корзины
widgets в dashboard_charts.py), НЕ purchase_item_fact_amount (committed_
amounts.py — это отдельная метрика «деньги субсидии», здесь — показатель
КПИ-карточки, Правило №6 не требует единой суммы между разными по смыслу
метриками, только единого НАБОРА СТАТУСОВ, который и переиспользован).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_ as sqland, func, not_ as sqlnot, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.services.committed_amounts import committed_status_predicate
from app.services.purchase_amounts import effective_amount_expr

# Контракты этих трёх типов (и ТОЛЬКО этих, СО status='active') уже учтены
# dashboard_charts.py::contract_single_q/contract_fc_q — единственный список,
# больше нигде не копируется (Правило №6, эта константа — предикат «уже
# посчитан где-то ещё», а не самостоятельный бизнес-смысл).
_COUNTED_ELSEWHERE_CONTRACT_TYPES = ("single", "framework_with_amount", "framework_cumulative")


def committed_uncounted_expr():
    """SQL boolean: закупка committed (committed_status_predicate), но её
    Contract НЕ покрыт существующими запросами dashboard_charts.py (причина
    1 докстринга модуля). ТРЕБУЕТ outerjoin(Contract, Purchase.contract_id ==
    Contract.id) в вызывающем запросе."""
    return sqland(
        committed_status_predicate(Purchase),
        sqlor(
            Purchase.contract_id.is_(None),
            Contract.id.is_(None),  # contract_id указывает на несуществующую запись (осиротевший FK)
            Contract.status != "active",
            sqlnot(Contract.contract_type.in_(_COUNTED_ELSEWHERE_CONTRACT_TYPES)),
        ),
    )


async def committed_uncounted_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "count": int}} — причина 1, см.
    докстринг модуля. `subsidy_ids` — список субсидий УЖЕ отфильтрованных по
    видимости/org/sandbox вызывающим кодом (Правило №6 — не второй фильтр
    видимости)."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    stmt = (
        select(
            Purchase.subsidy_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
            func.count(Purchase.id).label("cnt"),
        )
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.stopped_at.is_(None))
        .where(committed_uncounted_expr())
        .group_by(Purchase.subsidy_id)
    )
    rows = (await db.execute(stmt)).all()
    for r in rows:
        result[r.subsidy_id] = {"amount": float(r.amt), "count": int(r.cnt)}
    return result


async def single_contract_topup_by_subsidy(
    db: AsyncSession,
    *,
    subsidy_ids: Optional[list[int]] = None,
) -> dict[int, dict]:
    """{subsidy_id: {"amount": float, "count": int}} — причина 2, см.
    докстринг модуля: активные Contract(contract_type='single') чья реальная
    Σ committed-закупок (committed_status_predicate, effective_amount_expr)
    ПРЕВЫШАЕТ учтённый cs_rows Contract.max_amount (в т.ч. max_amount IS
    NULL → учтено как 0, SQL SUM молча теряет такие строки целиком — именно
    это произошло на «ХО», 16 договоров, 4 777 721,20 ₽). Добавка = разница
    (actual − recorded), НЕ дублирует то, что cs_rows уже посчитал —
    `greatest()`-приём, идентичный framework_with_amount (_fwa_children_sum,
    dashboard_charts.py), применённый теперь и к single."""
    result: dict[int, dict] = {}
    if not subsidy_ids:
        return result

    stmt = (
        select(
            Contract.subsidy_id,
            Contract.id,
            Contract.max_amount,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("actual"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(Contract.status == "active")
        .where(Contract.contract_type == "single")
        .where(committed_status_predicate(Purchase))
        .where(Purchase.stopped_at.is_(None))
        .group_by(Contract.subsidy_id, Contract.id, Contract.max_amount)
    )
    rows = (await db.execute(stmt)).all()
    for r in rows:
        actual = float(r.actual or 0)
        recorded = float(r.max_amount) if r.max_amount is not None else 0.0
        topup = actual - recorded
        if topup > 0.005:
            d = result.setdefault(r.subsidy_id, {"amount": 0.0, "count": 0})
            d["amount"] += topup
            d["count"] += 1
    return result
