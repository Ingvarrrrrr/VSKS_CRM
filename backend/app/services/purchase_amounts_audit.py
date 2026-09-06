"""purchase_amounts_audit.py — измерение расхождения девяти существующих
backend-формул «суммы закупки» против нового единого effective
(app.services.purchase_amounts.purchase_amounts). ТОЛЬКО ИЗМЕРЕНИЕ — ничего не
меняет ни в одном из 9 мест, ни в самих закупках; только читает.

Каждая формула ниже реализована ДОСЛОВНО (та же арифметика, тот же порядок
приоритетов/COALESCE/`or`-цепочек, включая Python-truthy баг там, где он есть
в оригинале — например `nmck or planned_total_price or 0` не отличает 0 от
None) — со ссылкой на файл:строку источника в докстринге функции.

Не для каждой закупки применима каждая формула (некоторые формулы в
оригинале гейтятся статусом/наличием категории — GROUP BY/WHERE в SQL просто
не производит строку). Там, где формула НЕ применяется к закупке, эта закупка
не входит ни в `applicable`, ни в `divergent` этой формулы (не путать с
«совпадает с effective» — это разные вещи).

Запуск (контейнер монтирует backend/app живьём, файл виден сразу):
  docker exec vsks_crm-backend_a-1 python -c "import asyncio; from
  app.services.purchase_amounts_audit import audit_cli; asyncio.run(audit_cli())"
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.feo_plan import purchase_item_fact_amount
from app.services.purchase_amounts import FRAMEWORK_TYPES, load_purchase_amounts


@dataclass
class _Ctx:
    """Batch-предзагруженные суммы позиций/договоров — без N+1, как в load_purchase_amounts."""
    contract_item_sum_by_purchase: dict
    purchase_item_sum_by_purchase: dict
    contract_item_sum_by_source_item: dict
    contract_max_by_id: dict
    contract_sum_by_contract: dict


async def _build_ctx(db: AsyncSession, purchases: list) -> _Ctx:
    ci_rows = (await db.execute(
        select(ContractItem.purchase_id, func.coalesce(func.sum(ContractItem.total), 0))
        .group_by(ContractItem.purchase_id)
    )).all()
    contract_item_sum_by_purchase = {pid: Decimal(str(t)) for pid, t in ci_rows}

    pi_rows = (await db.execute(
        select(PurchaseItem.purchase_id, func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .group_by(PurchaseItem.purchase_id)
    )).all()
    purchase_item_sum_by_purchase = {pid: Decimal(str(t)) for pid, t in pi_rows}

    ci_by_source_rows = (await db.execute(
        select(ContractItem.source_item_id, func.coalesce(func.sum(ContractItem.total), 0))
        .where(ContractItem.source_item_id.isnot(None))
        .group_by(ContractItem.source_item_id)
    )).all()
    contract_item_sum_by_source_item = {iid: Decimal(str(t)) for iid, t in ci_by_source_rows if t}

    contract_ids = {p.contract_id for p in purchases if p.contract_id}
    contract_max_by_id: dict = {}
    if contract_ids:
        rows = (await db.execute(select(Contract.id, Contract.max_amount).where(Contract.id.in_(contract_ids)))).all()
        contract_max_by_id = {cid: ma for cid, ma in rows}

    contract_sum_rows = (await db.execute(
        select(
            Purchase.contract_id,
            func.coalesce(func.sum(func.coalesce(
                Purchase.contract_price, Purchase.planned_total_price, Purchase.total_nmck, 0
            )), 0),
        ).where(Purchase.contract_id.isnot(None)).group_by(Purchase.contract_id)
    )).all()
    contract_sum_by_contract = {cid: Decimal(str(s)) for cid, s in contract_sum_rows}

    return _Ctx(
        contract_item_sum_by_purchase, purchase_item_sum_by_purchase,
        contract_item_sum_by_source_item, contract_max_by_id, contract_sum_by_contract,
    )


def _d(v) -> Optional[Decimal]:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


# dashboard.py:225,257,268,275,420,677,690,701 и др. — COALESCE(contract_price, planned_total_price).
# Применена без гейта по статусу (гейт есть в SQL каждого места вызова; здесь измеряется сама формула).
def _f_dashboard_contract_or_planned(p, ctx: _Ctx) -> Optional[Decimal]:
    c = _d(p.contract_price)
    return c if c is not None else _d(p.planned_total_price)


# dashboard.py:282,712 (ветка status=='paid') — COALESCE(payment_amount, contract_price, planned_total_price).
def _f_dashboard_payment_or_contract_or_planned(p, ctx: _Ctx) -> Optional[Decimal]:
    pay = _d(p.payment_amount)
    if pay is not None:
        return pay
    c = _d(p.contract_price)
    return c if c is not None else _d(p.planned_total_price)


# purchase_export.py:278 — `nmck or planned_total_price or 0` (Python truthy — 0/None одинаково проваливаются дальше).
def _f_purchase_export_nmck(p, ctx: _Ctx) -> Optional[Decimal]:
    nmck = _d(p.nmck)
    val = nmck if nmck else _d(p.planned_total_price)
    return val if val else Decimal("0")


# documents.py:1272-1274 — договорные doc_type: `contract_price or Σ ContractItem.total` (Python truthy).
def _f_documents_contract_family(p, ctx: _Ctx) -> Optional[Decimal]:
    c = _d(p.contract_price)
    if c:
        return c
    return ctx.contract_item_sum_by_purchase.get(p.id, Decimal("0"))


# documents.py:1275-1279 — прочие doc_type: `contract_price or total_nmck or nmck or planned_total_price
# or Σ PurchaseItem.total_price` (Python truthy — каждое звено, включая 0, проваливается дальше).
def _f_documents_other(p, ctx: _Ctx) -> Optional[Decimal]:
    items_sum = ctx.purchase_item_sum_by_purchase.get(p.id, Decimal("0"))
    for v in (p.contract_price, getattr(p, "total_nmck", None), p.nmck, p.planned_total_price):
        dv = _d(v)
        if dv:
            return dv
    return items_sum


# purchases.py:1402-1426/1850-1865 (рамочный итог) — применяется ТОЛЬКО если contract_id задан И
# purchase_contract_type в FRAMEWORK_TYPES (голова ИЛИ дочерняя — код не проверяет parent_purchase_id):
# Contract.max_amount, если задан, иначе Σ COALESCE(contract_price, planned_total_price, total_nmck, 0)
# по всем закупкам этого contract_id. None = формула не применима.
def _f_framework_total(p, ctx: _Ctx) -> Optional[Decimal]:
    if not p.contract_id or getattr(p, "purchase_contract_type", None) not in FRAMEWORK_TYPES:
        return None
    max_amount = _d(ctx.contract_max_by_id.get(p.contract_id))
    if max_amount is not None:
        return max_amount
    return ctx.contract_sum_by_contract.get(p.contract_id, Decimal("0"))


# purchase_payments.py:103 — `contract_price or planned_total_price or Decimal(0)` (Python truthy;
# это порог авто-paid, не «сумма закупки» по смыслу, но формула, которую читатель использует вместо effective).
def _f_payments_threshold(p, ctx: _Ctx) -> Optional[Decimal]:
    c = p.contract_price
    if c:
        return _d(c)
    pl = p.planned_total_price
    if pl:
        return _d(pl)
    return Decimal("0")


# feo_categories.py:242-244 — Σ COALESCE(final_total_amount, planned_total_price), ТОЛЬКО для
# status IN (delivered, paid) И feo_category_id IS NOT NULL (WHERE в оригинале) — иначе строка не
# попадает в SUM вовсе → формула не применима (None), а не 0.
def _f_feo_categories_purchase_totals(p, ctx: _Ctx) -> Optional[Decimal]:
    if p.status not in ("delivered", "paid") or p.feo_category_id is None:
        return None
    fta = _d(p.final_total_amount)
    return fta if fta is not None else _d(p.planned_total_price)


# feo_plan.py:95-159 purchase_item_fact_amount — ПЕРЕИСПОЛЬЗУЕТСЯ напрямую (не переписана, уже единый
# источник факта позиции), просуммирована по ВСЕМ позициям закупки той же пропорцией (ratio), что и
# ordered_consumption_by_category/fact_consumption_by_category. Нет items → None. Позиции, для которых
# сама функция вернула None, пропускаются (как в оригинальном цикле); если ВСЕ дали None → None целиком.
def _f_feo_plan_fact_amount(p, ctx: _Ctx) -> Optional[Decimal]:
    items = list(p.items or [])
    if not items:
        return None
    items_count = len(items)
    items_sum = sum((Decimal(str(it.total_price or 0)) for it in items), Decimal("0"))
    total = Decimal("0")
    got_any = False
    for it in items:
        item_total = Decimal(str(it.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)
        else:
            ratio = Decimal(1)
        contract_item_total = ctx.contract_item_sum_by_source_item.get(it.id)
        fact_amount, _allocated = purchase_item_fact_amount(
            it, p, ratio, items_count, contract_item_total=contract_item_total
        )
        if fact_amount is not None:
            total += fact_amount
            got_any = True
    return total if got_any else None


# subsidies.py:130-133 — Σ planned_total_price по закупкам субсидии, КРОМЕ cancelled (per-закупку вклад
# в SQL SUM; NULL planned_total_price вносит 0 — воспроизведено явно). cancelled → None (исключена WHERE).
def _f_subsidies_spent(p, ctx: _Ctx) -> Optional[Decimal]:
    if p.status == "cancelled":
        return None
    pl = _d(p.planned_total_price)
    return pl if pl is not None else Decimal("0")


FORMULAS: dict[str, Callable] = {
    "1_purchases_full_raw": None,  # особый случай — см. audit_divergences()
    "2a_dashboard_contract_or_planned": _f_dashboard_contract_or_planned,
    "2b_dashboard_payment_or_contract_or_planned": _f_dashboard_payment_or_contract_or_planned,
    "3_purchase_export_nmck": _f_purchase_export_nmck,
    "4a_documents_contract_family": _f_documents_contract_family,
    "4b_documents_other": _f_documents_other,
    "5_framework_total": _f_framework_total,
    "6_payments_threshold": _f_payments_threshold,
    "7_feo_categories_purchase_totals": _f_feo_categories_purchase_totals,
    "8_feo_plan_fact_amount": _f_feo_plan_fact_amount,
    "9_subsidies_spent": _f_subsidies_spent,
}

FORMULA_NOTE_1 = (
    "routers/purchases.py:_purchase_to_full (921-1010) — отдаёт СЫРЫЕ колонки "
    "Purchase без вычисления единого числа; выбор цепочки (напр. OrdersView "
    "`contract_price ?? total_nmck ?? planned_total_price`) — на фронте, вне "
    "backend. Нет скаляра для сравнения с effective — N/A, не входит в счёт."
)


async def audit_divergences(db: AsyncSession) -> dict:
    """Возвращает {total, formulas: {name: {applicable, divergent, examples}},
    extra_checks: {...}} — см. докстринг модуля."""
    purchases = (await db.execute(select(Purchase))).scalars().all()
    total = len(purchases)
    ids = [p.id for p in purchases]
    amounts = await load_purchase_amounts(db, ids)
    ctx = await _build_ctx(db, purchases)

    result: dict = {"total": total, "formulas": {}, "extra_checks": {}}
    result["formulas"]["1_purchases_full_raw"] = {"applicable": 0, "divergent": 0, "examples": [], "note": FORMULA_NOTE_1}

    for name, fn in FORMULAS.items():
        if fn is None:
            continue
        applicable = 0
        divergent = 0
        examples = []
        for p in purchases:
            val = fn(p, ctx)
            if val is None:
                continue
            applicable += 1
            eff = amounts[p.id].effective
            if eff is None or val != eff:
                divergent += 1
                if len(examples) < 10:
                    examples.append({
                        "id": p.id, "status": p.status, "formula_value": str(val),
                        "effective": str(eff) if eff is not None else None,
                        "effective_source": amounts[p.id].effective_source,
                    })
        result["formulas"][name] = {"applicable": applicable, "divergent": divergent, "examples": examples}

    # Доп. счётчики, явно запрошенные заданием.
    nmck_vs_total_nmck = 0
    contract_vs_contract_items = 0
    contract_vs_purchase_items = 0
    for p in purchases:
        if p.nmck is not None and getattr(p, "total_nmck", None) is not None and Decimal(str(p.nmck)) != Decimal(str(p.total_nmck)):
            nmck_vs_total_nmck += 1
        ci_sum = ctx.contract_item_sum_by_purchase.get(p.id)
        if ci_sum is not None and p.contract_price is not None and Decimal(str(p.contract_price)) != ci_sum:
            contract_vs_contract_items += 1
        if ci_sum is None:
            pi_sum = ctx.purchase_item_sum_by_purchase.get(p.id)
            if pi_sum is not None and p.contract_price is not None and Decimal(str(p.contract_price)) != pi_sum:
                contract_vs_purchase_items += 1
    result["extra_checks"] = {
        "nmck_ne_total_nmck_both_not_null": nmck_vs_total_nmck,
        "contract_price_ne_sum_contract_items_when_present": contract_vs_contract_items,
        "contract_price_ne_sum_purchase_items_when_no_contract_items": contract_vs_purchase_items,
    }
    return result


def _print_table(result: dict) -> None:
    total = result["total"]
    print(f"=== purchase_amounts_audit: M={total} закупок ===")
    print()
    for name, r in result["formulas"].items():
        note = f"  [{r['note']}]" if "note" in r else ""
        print(f"{name}: applicable={r['applicable']} divergent={r['divergent']}{note}")
        for ex in r["examples"][:10]:
            print(f"    id={ex['id']} status={ex['status']} formula={ex['formula_value']} "
                  f"effective={ex['effective']} ({ex['effective_source']})")
    print()
    print("extra_checks:")
    for k, v in result["extra_checks"].items():
        print(f"  {k}: {v}")


async def audit_cli() -> None:
    """Печатает читаемую таблицу. Запуск — см. докстринг модуля."""
    from app.database import async_session

    async with async_session() as db:
        result = await audit_divergences(db)
        _print_table(result)
