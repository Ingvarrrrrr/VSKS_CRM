"""Контрольные суммы «выписка ↔ закупки» по субсидии.

План .planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1. Читает
строки через app/services/payment_control_sources/ (единственный адаптер
сейчас — закупки, is_procurement=true), ПРАВИЛО №6 — сам денег не считает
по-новому, использует существующие кирпичи:
  - subsidy_scope_clause() — app/services/bank_payment_subsidy_scope.py
  - EXECUTED_STATUSES — app/services/bank_statement_parser.py
  - ExpenseCode — справочник кодов расходов

Контракт ответа GET /api/subsidies/{id}/payment-control — см. промпт задачи/
PLAN.md; схема НЕ меняется без согласования с фронтом (контракт API).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.expense_code import ExpenseCode
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.subsidy_payment_control_code import SubsidyPaymentControlCode
from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_control_near_miss import build_near_miss
from app.services.purchase_sheet_ref import resolve_sheet_ref

AMOUNT_TOL = Decimal("0.02")
_NO_CODE = "__NO_CODE__"


# ---------------------------------------------------------------------------
# Коды, по которым субсидия ищет закупку (выбор субсидии, умолчание = is_procurement)
# ---------------------------------------------------------------------------

async def get_search_codes(db: AsyncSession, subsidy_id: int) -> tuple[set[str], bool]:
    """Возвращает (коды, is_default). is_default=True — у субсидии ещё нет
    явного выбора, действует умолчание (все коды с is_procurement=true)."""
    rows = (await db.execute(
        select(SubsidyPaymentControlCode.code).where(SubsidyPaymentControlCode.subsidy_id == subsidy_id)
    )).scalars().all()
    if rows:
        return set(rows), False
    default_rows = (await db.execute(
        select(ExpenseCode.code).where(ExpenseCode.is_procurement.is_(True))
    )).scalars().all()
    return set(default_rows), True


async def set_search_codes(db: AsyncSession, subsidy_id: int, codes: list[str]) -> None:
    """Заменяет выбор субсидии целиком. commit — на вызывающем."""
    await db.execute(
        SubsidyPaymentControlCode.__table__.delete().where(
            SubsidyPaymentControlCode.subsidy_id == subsidy_id
        )
    )
    for code in sorted(set(c.strip() for c in codes if c and c.strip())):
        db.add(SubsidyPaymentControlCode(subsidy_id=subsidy_id, code=code))


# ---------------------------------------------------------------------------
# Сверка
# ---------------------------------------------------------------------------

@dataclass
class _Row:
    key: str
    bank_payment_ids: list
    payment_number: Optional[str]
    payment_date: Optional[str]
    payee_name: Optional[str]
    payee_inn: Optional[str]
    amount: float
    purpose_text: Optional[str]
    expense_code: Optional[str]
    expense_name: Optional[str]
    status: str
    purchases: list
    amount_diff: float
    unknown_code: bool
    duplicate_with: list
    near_miss: list
    other_subsidy: Optional[dict] = None


def _purchase_brief(p: Purchase, amount: Decimal) -> dict:
    return {
        "id": p.id,
        "registry_number": p.registry_number,
        "subject": p.subject or p.item_name,
        "amount": float(amount),
        # План 2026-10-06-statement-control, контракт API: номер закупки/
        # заказа из таблицы владельца, если есть (ПРАВИЛО №6 — один резолв,
        # app/services/purchase_sheet_ref.py, тот же для экспорта).
        "sheet_ref": resolve_sheet_ref(p),
    }


async def build_payment_control(db: AsyncSession, subsidy: Subsidy) -> dict:
    search_codes, _is_default = await get_search_codes(db, subsidy.id)

    # Справочник кодов — один SELECT, используется и для kind/name, и для
    # unknown_code (код встретился в выписке, но отсутствует в справочнике).
    code_rows = (await db.execute(select(ExpenseCode))).scalars().all()
    code_map: dict[str, ExpenseCode] = {c.code: c for c in code_rows}

    # Исполненные строки выписки, видные субсидии (правило bank_payment_subsidy_scope).
    bp_rows = (await db.execute(
        select(BankPayment).where(subsidy_scope_clause(subsidy))
    )).scalars().all()
    executed = [bp for bp in bp_rows if (bp.status or "").upper().strip() in EXECUTED_STATUSES]
    not_executed = [bp for bp in bp_rows if bp not in executed]

    # Payment-ы закупок ЭТОЙ субсидии, подтверждённые выпиской — индекс по bank_payment_id.
    pay_rows = (await db.execute(
        select(Payment).join(Purchase, Purchase.id == Payment.purchase_id).where(
            Purchase.subsidy_id == subsidy.id,
            Payment.confirmed_by_statement.is_(True),
            Payment.bank_payment_id.isnot(None),
        )
    )).scalars().all()
    payments_by_bp: dict[int, list[Payment]] = defaultdict(list)
    for pay in pay_rows:
        payments_by_bp[pay.bank_payment_id].append(pay)

    purchase_ids = {pay.purchase_id for pay in pay_rows if pay.purchase_id}
    purchase_map: dict[int, Purchase] = {}
    if purchase_ids:
        prows = (await db.execute(select(Purchase).where(Purchase.id.in_(purchase_ids)))).scalars().all()
        purchase_map = {p.id: p for p in prows}

    # ------------------------------------------------------------------
    # Строки выписки, уже «пойманные» закупкой ДРУГОЙ субсидии (инцидент
    # 06.10: ФАДМ 2026_2/id 89 и ФАДМ_2026/id 7 — общий номер соглашения,
    # subsidy_scope_clause() видит одни и те же 122 строки обеим; у 89 есть
    # закупки с payments.bank_payment_id на эти строки, у 7 — нет, и 7 считала
    # их «без закупки», хотя они просто принадлежат 89). Один SELECT, тот же
    # bp_rows-скоуп, без повторного запроса subsidy_scope_clause.
    other_bp_ids = [bp.id for bp in bp_rows if bp.id not in payments_by_bp]
    other_subsidy_by_bp: dict[int, dict] = {}
    other_subsidies_totals: dict[int, dict] = {}
    if other_bp_ids:
        other_rows = (await db.execute(
            select(Payment.bank_payment_id, Payment.amount, Purchase.subsidy_id, Subsidy.name)
            .join(Purchase, Purchase.id == Payment.purchase_id)
            .join(Subsidy, Subsidy.id == Purchase.subsidy_id)
            .where(
                Payment.confirmed_by_statement.is_(True),
                Payment.bank_payment_id.in_(other_bp_ids),
                Purchase.subsidy_id != subsidy.id,
            )
        )).all()
        for bank_payment_id, _pay_amount, other_subsidy_id, other_subsidy_name in other_rows:
            # Первое найденное совпадение на bank_payment_id — этого достаточно
            # для подсказки «уже в закупке субсидии X»; несколько совпадений на
            # одну строку выписки в разных ДРУГИХ субсидиях — редкий край
            # случай, не наш контроль (у него своя сверка).
            other_subsidy_by_bp.setdefault(bank_payment_id, {
                "id": other_subsidy_id, "name": other_subsidy_name,
            })

    rows: list[_Row] = []
    counts: dict[str, int] = defaultdict(int)
    article_stat: dict[str, dict] = {}
    from_payment_unrefined_count = 0
    # Контрольный лист (план 2026-10-06-statement-control, п.3): «привязано N
    # из M платёжек, сумма A из B, не хватает C» — считается тут же, в одном
    # проходе по исполненным строкам выписки, а не вторым запросом.
    stmt_search_count = 0
    attached_count = 0
    unattached_count = 0
    unattached_total = Decimal(0)
    unattached_numbers: list[str] = []

    def _article_bucket(code: Optional[str]) -> dict:
        key = code or _NO_CODE
        if key not in article_stat:
            meta = code_map.get(code) if code else None
            is_unknown = code is not None and meta is None
            # Код без пары в справочнике — ищем закупку по умолчанию (владелец:
            # «деньги не прятать», план PLAN.md раздел 1), как и строки совсем
            # без кода; код ИЗ справочника — по явному выбору субсидии.
            search_purchase = True if (not code or is_unknown) else (code in search_codes)
            article_stat[key] = {
                "code": code,
                "name": (meta.name if meta else ("Без кода расходов" if not code else f"Код {code} — не в справочнике")),
                "kind": meta.kind if meta else None,
                "is_procurement": bool(meta.is_procurement) if meta else None,
                "search_purchase": search_purchase,
                "unknown": is_unknown,
                "statement_total": Decimal(0),
                "statement_count": 0,
                "matched_total": Decimal(0),
            }
        return article_stat[key]

    for bp in executed:
        code = bp.expense_code
        bucket = _article_bucket(code)
        amount = Decimal(str(bp.amount or 0))
        bucket["statement_total"] += amount
        bucket["statement_count"] += 1

        search_this = bucket["search_purchase"]
        unknown = bucket["unknown"]

        linked = payments_by_bp.get(bp.id, [])
        matched_amount = sum((Decimal(str(pay.amount or 0)) for pay in linked), Decimal(0))
        diff = amount - matched_amount
        # Только для строк, которые эта субсидия ВООБЩЕ ищет среди закупок
        # (search_this) и не нашла у себя (not linked) — иначе not_reconciled
        # (код не отмечен для поиска) неверно попадал бы в other_subsidies и
        # вычитался из reconciled_total, которого для него и не было.
        other_subsidy_info = other_subsidy_by_bp.get(bp.id) if (search_this and not linked) else None

        if search_this and not other_subsidy_info:
            stmt_search_count += 1
            if linked:
                attached_count += 1
            else:
                unattached_count += 1
                unattached_total += amount
                unattached_numbers.append(bp.payment_number or f"№{bp.id}")

        if other_subsidy_info and not linked:
            # Уже найдена в закупке ДРУГОЙ субсидии — не «без закупки» этой
            # субсидии, в difference/alarm/unattached не попадает (вычитается
            # из reconciled_total ниже, ПРАВИЛО №6 — тот же difference, не
            # второй расчёт).
            status = "in_other_subsidy"
            diff = Decimal(0)
            agg = other_subsidies_totals.setdefault(other_subsidy_info["id"], {
                "id": other_subsidy_info["id"], "name": other_subsidy_info["name"],
                "count": 0, "total": Decimal(0),
            })
            agg["count"] += 1
            agg["total"] += amount
        elif not search_this:
            status = "not_reconciled"
        elif linked:
            bucket["matched_total"] += matched_amount
            status = "match" if abs(diff) <= AMOUNT_TOL else "amount_mismatch"
        else:
            status = "registry_only"
        counts[status] += 1

        purchases_out = []
        for pay in linked:
            p = purchase_map.get(pay.purchase_id)
            if p is not None:
                purchases_out.append(_purchase_brief(p, Decimal(str(pay.amount or 0))))

        rows.append(_Row(
            key=f"bp-{bp.id}",
            bank_payment_ids=[bp.id],
            payment_number=bp.payment_number,
            payment_date=bp.payment_date.isoformat() if bp.payment_date else None,
            payee_name=bp.payee_name,
            payee_inn=bp.payee_inn,
            amount=float(amount),
            purpose_text=bp.purpose_text,
            expense_code=code,
            expense_name=bucket["name"],
            status=status,
            purchases=purchases_out,
            amount_diff=float(diff) if search_this else 0.0,
            unknown_code=unknown,
            duplicate_with=[],
            near_miss=[],
            other_subsidy=other_subsidy_info if status == "in_other_subsidy" else None,
        ))

    # ------------------------------------------------------------------
    # Дубли
    # ------------------------------------------------------------------
    # (а) ≥2 исполненные строки выписки субсидии с одинаковыми payee_inn + amount + payment_date
    by_triplet: dict[tuple, list[_Row]] = defaultdict(list)
    for r in rows:
        if r.payee_inn and r.payment_date:
            by_triplet[(r.payee_inn, round(r.amount, 2), r.payment_date)].append(r)
    for triplet, group in by_triplet.items():
        if len(group) > 1:
            for r in group:
                if r.status != "duplicate":
                    counts[r.status] -= 1
                r.status = "duplicate"
                r.duplicate_with = [o.payment_number or str(o.bank_payment_ids) for o in group if o is not r]
                counts["duplicate"] += 1

    # (б) одна строка выписки → Payment у ≥2 закупок одной субсидии
    for bp_id, linked in payments_by_bp.items():
        distinct_purchases = {pay.purchase_id for pay in linked if pay.purchase_id}
        if len(distinct_purchases) > 1:
            for r in rows:
                if bp_id in r.bank_payment_ids and r.status != "duplicate":
                    counts[r.status] -= 1
                    r.status = "duplicate"
                    r.duplicate_with = [
                        (purchase_map[pid].registry_number or f"закупка №{pid}")
                        for pid in distinct_purchases if pid in purchase_map
                    ]
                    counts["duplicate"] += 1

    # (в) ≥2 закупки субсидии с одинаковым контрагентом и суммой договора без пары в выписке
    #
    # Задача 2026-10-05 («разбор сверки ФАДМ 2026_2», п.2): заказы ОДНОГО рамочного
    # договора (общий parent_purchase_id — дочерние заказы головы, ИЛИ общий
    # Contract.id) с одинаковой суммой — это ПОМЕСЯЦЕВЫЕ заказы (Ростелеком, Предрейсовый,
    # Егорова и т.п.), не дубли; framework_key ниже группирует их отдельно и такие
    # бакеты (framework_key is not None) в дубли не попадают.
    all_subsidy_purchases = (await db.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()
    matched_purchase_ids = {pay.purchase_id for pay in pay_rows if pay.purchase_id}
    by_contractor_amount: dict[tuple, list[Purchase]] = defaultdict(list)
    for p in all_subsidy_purchases:
        if p.id in matched_purchase_ids or not p.contractor_id or p.contract_price is None:
            continue
        framework_key = p.parent_purchase_id or p.contract_id
        by_contractor_amount[(p.contractor_id, round(float(p.contract_price), 2), framework_key)].append(p)
    duplicate_purchase_rows = []
    for key, plist in by_contractor_amount.items():
        _contractor_id, _amount, framework_key = key
        if framework_key is not None:
            continue  # заказы одного рамочного договора — не дубли, см. примечание выше
        if len(plist) > 1:
            for p in plist:
                duplicate_purchase_rows.append(_Row(
                    key=f"purchase-{p.id}",
                    bank_payment_ids=[],
                    payment_number=None,
                    payment_date=None,
                    payee_name=None,
                    payee_inn=None,
                    amount=float(p.contract_price or 0),
                    purpose_text=None,
                    expense_code=None,
                    expense_name=None,
                    status="duplicate",
                    purchases=[_purchase_brief(p, p.contract_price or Decimal(0))],
                    amount_diff=0.0,
                    unknown_code=False,
                    duplicate_with=[
                        (o.registry_number or f"закупка №{o.id}") for o in plist if o is not p
                    ],
                    near_miss=[],
                ))
            counts["duplicate"] += len(plist)
    rows.extend(duplicate_purchase_rows)

    # ------------------------------------------------------------------
    # near_miss — подсказки к непривязанным строкам (план п.4). После дублей,
    # чтобы считать только для строк, ОСТАВШИХСЯ registry_only.
    # ------------------------------------------------------------------
    for r in rows:
        if r.status == "registry_only":
            r.near_miss = await build_near_miss(
                db, subsidy.id, Decimal(str(r.amount)), r.payee_inn, r.purpose_text, purchase_ids,
            )

    # ------------------------------------------------------------------
    # declared_unconfirmed — заявлено человеком, выпиской не подтверждено (для закупок этой субсидии)
    # ------------------------------------------------------------------
    declared_rows = (await db.execute(
        select(Payment).join(Purchase, Purchase.id == Payment.purchase_id).where(
            Purchase.subsidy_id == subsidy.id,
            Payment.payment_source == "manual",
            Payment.confirmed_by_statement.is_(False),
        )
    )).scalars().all()
    for pay in declared_rows:
        counts["declared_unconfirmed"] += 1
        p = purchase_map.get(pay.purchase_id)
        if p is None:
            p = await db.get(Purchase, pay.purchase_id)
        rows.append(_Row(
            key=f"declared-{pay.id}",
            bank_payment_ids=[],
            payment_number=pay.document_number,
            payment_date=pay.payment_date.isoformat() if pay.payment_date else None,
            payee_name=None,
            payee_inn=None,
            amount=float(pay.amount or 0),
            purpose_text=pay.payment_purpose,
            expense_code=pay.expense_code,
            expense_name=None,
            status="declared_unconfirmed",
            purchases=[_purchase_brief(p, Decimal(str(pay.amount or 0)))] if p else [],
            amount_diff=0.0,
            unknown_code=False,
            duplicate_with=[],
            near_miss=[],
        ))

    # ------------------------------------------------------------------
    # from_payment_unrefined_count — закупки созданные по платёжке, 1 позиция (не уточнены)
    # ------------------------------------------------------------------
    from app.models.purchase_item import PurchaseItem
    created_from_bp = (await db.execute(
        select(Purchase.id).where(
            Purchase.subsidy_id == subsidy.id,
            Purchase.created_from_bank_payment_id.isnot(None),
        )
    )).scalars().all()
    for pid in created_from_bp:
        item_count = (await db.execute(
            select(PurchaseItem.id).where(PurchaseItem.purchase_id == pid)
        )).scalars().all()
        if len(item_count) <= 1:
            from_payment_unrefined_count += 1

    # ------------------------------------------------------------------
    # Итоги
    # ------------------------------------------------------------------
    executed_total = sum((Decimal(str(bp.amount or 0)) for bp in executed), Decimal(0))
    reconciled_total = sum(
        (b["statement_total"] for b in article_stat.values() if b["search_purchase"]), Decimal(0),
    )
    found_in_purchases = sum(
        (b["matched_total"] for b in article_stat.values() if b["search_purchase"]), Decimal(0),
    )
    not_reconciled_total = sum(
        (b["statement_total"] for b in article_stat.values() if not b["search_purchase"]), Decimal(0),
    )
    unknown_code_total = sum(
        (b["statement_total"] for b in article_stat.values() if b["unknown"]), Decimal(0),
    )
    # Строки, пойманные закупкой другой субсидии, лежат внутри bucket["statement_total"]
    # (код статьи общий), но это не «наши» деньги без закупки — вычитаем их из
    # reconciled_total, чтобы difference/alarm не врали (ПРАВИЛО №6: один difference,
    # не второй расчёт параллельно с этим).
    in_other_subsidies_total = sum((a["total"] for a in other_subsidies_totals.values()), Decimal(0))
    in_other_subsidies_count = sum((a["count"] for a in other_subsidies_totals.values()), 0)
    difference = (reconciled_total - in_other_subsidies_total) - found_in_purchases

    not_executed_total = sum((Decimal(str(bp.amount or 0)) for bp in not_executed), Decimal(0))

    as_of = max((bp.payment_date for bp in executed if bp.payment_date), default=None)

    alarm = (
        abs(difference) > AMOUNT_TOL
        or counts.get("registry_only", 0) > 0
        or counts.get("amount_mismatch", 0) > 0
        or counts.get("duplicate", 0) > 0
    )

    articles_out = []
    for key, b in article_stat.items():
        articles_out.append({
            "code": b["code"],
            "name": b["name"],
            "kind": b["kind"],
            "is_procurement": b["is_procurement"],
            "search_purchase": b["search_purchase"],
            "unknown": b["unknown"],
            "statement_total": float(b["statement_total"]),
            "statement_count": b["statement_count"],
            "matched_total": float(b["matched_total"]),
            "difference": float(b["statement_total"] - b["matched_total"]) if b["search_purchase"] else 0.0,
        })
    articles_out.sort(key=lambda a: (a["code"] or "~"))

    def _row_to_dict(r: _Row) -> dict:
        return {
            "key": r.key,
            "bank_payment_ids": r.bank_payment_ids,
            "payment_number": r.payment_number,
            "payment_date": r.payment_date,
            "payee_name": r.payee_name,
            "payee_inn": r.payee_inn,
            "amount": r.amount,
            "purpose_text": r.purpose_text,
            "expense_code": r.expense_code,
            "expense_name": r.expense_name,
            "status": r.status,
            "purchases": r.purchases,
            "amount_diff": r.amount_diff,
            "unknown_code": r.unknown_code,
            "duplicate_with": r.duplicate_with,
            "near_miss": r.near_miss,
            "other_subsidy": r.other_subsidy,
        }

    status_order = {
        "amount_mismatch": 0, "registry_only": 1, "duplicate": 2, "declared_unconfirmed": 3,
        "not_reconciled": 4, "purchases_only": 5, "match": 6, "in_other_subsidy": 7,
    }
    rows.sort(key=lambda r: (status_order.get(r.status, 99), r.payment_number or ""))

    not_executed_out = [
        {
            "id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "status": bp.status,
            "payee_name": bp.payee_name,
            "amount": float(bp.amount or 0),
        }
        for bp in not_executed
    ]

    return {
        "as_of": as_of.isoformat() if as_of else None,
        "alarm": alarm,
        "totals": {
            "executed_total": float(executed_total),
            "executed_count": len(executed),
            "reconciled_total": float(reconciled_total),
            "found_in_purchases": float(found_in_purchases),
            "difference": float(difference),
            "not_reconciled_total": float(not_reconciled_total),
            "not_executed_count": len(not_executed),
            "not_executed_total": float(not_executed_total),
            "unknown_code_total": float(unknown_code_total),
            "from_payment_unrefined_count": from_payment_unrefined_count,
            # Контракт API, план 2026-10-06-statement-control, п.3 — «привязано
            # N из M платёжек, сумма A из B, не хватает C».
            "statement_count": stmt_search_count,
            "attached_count": attached_count,
            "unattached_count": unattached_count,
            "unattached_total": float(unattached_total),
            "unattached_numbers": unattached_numbers,
            # Задача 06.10 (ФАДМ 2026_2 ↔ ФАДМ_2026) — платёжки, уже привязанные
            # к закупке ДРУГОЙ субсидии; не входят ни в unattached, ни в difference.
            "in_other_subsidies_count": in_other_subsidies_count,
            "in_other_subsidies_total": float(in_other_subsidies_total),
        },
        "counts": {
            "match": counts.get("match", 0),
            "amount_mismatch": counts.get("amount_mismatch", 0),
            "registry_only": counts.get("registry_only", 0),
            "purchases_only": counts.get("purchases_only", 0),
            "duplicate": counts.get("duplicate", 0),
            "not_reconciled": counts.get("not_reconciled", 0),
            "declared_unconfirmed": counts.get("declared_unconfirmed", 0),
        },
        "articles": articles_out,
        "rows": [_row_to_dict(r) for r in rows],
        "not_executed": not_executed_out,
        "other_subsidies": [
            {"id": a["id"], "name": a["name"], "count": a["count"], "total": float(a["total"])}
            for a in sorted(other_subsidies_totals.values(), key=lambda a: a["name"] or "")
        ],
    }
