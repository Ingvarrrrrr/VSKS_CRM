"""Сверка НДС закупки с НДС, распознанным в платежах выписки.

Задача владельца (2026-09-26): «надо проверять НДС по выгрузке платежей: если
в платежах НДС указан другой, то об этом надо сообщать, давать ссылки на
закупки, где не соответствует НДС, и предлагать приравнять НДС тому, что в
выгрузках платежей».

ПРАВИЛО №6 — единственное место сверки. Разбор текста платежа —
app/services/payment_vat.py::parse_payment_vat (не дублировать). Формула
«НДС из суммы, включающей НДС» для позиций закупки (per_item режим) — та же,
что в app/services/documents/stages_amounts.py (_parse_vat_rate_percent /
_item_vat_amount), которая уже используется генератором документов и
composables/useVatCalc.ts на фронте — переиспользуем её, вторую копию не
заводим.

Источники платежей закупки (владелец, доработка 2026-09-26 — «на проде
подтверждённых Payment почти нет, а ставку в выписке мы знаем»), ДВА, без
двойного счёта:
  1. Payment.purchase_id + Payment.matched_confirmed == True — подтверждённые
     (тот же фильтр, что app/services/payment_target.py, payment_lookup.py,
     match_candidates.py, bank_statements_registry.py). confirmed=True.
  2. BankPayment.matched_purchase_id == закупка — предложение авто-матчера
     (app/services/payment_matcher.py::auto_match), ЕЩЁ не подтверждённое
     пользователем. confirmed=False. Исключаются те BankPayment, чей id уже
     фигурирует как Payment.bank_payment_id среди подтверждённых платежей ЭТОЙ
     же закупки — иначе один и тот же реальный платёж считался бы дважды.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import Purchase
from app.models.payment import Payment
from app.models.bank_statement import BankPayment
from app.models.subsidy import Subsidy
from app.models.user_subsidy_access import UserSubsidyAccess
from app.auth.jwt import get_org_filter, ADMIN_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids
from app.services.payment_vat import parse_payment_vat, format_vat_label
from app.services.documents.stages_amounts import _parse_vat_rate_percent, _item_vat_amount

SHARE_TOLERANCE = Decimal("1")     # п.п. — допуск сравнения долей НДС для смешанного режима
RATE_TOLERANCE = Decimal("0.5")    # п.п. — допуск сравнения ставки закупки со ставкой платежей


@dataclass
class PaymentSource:
    """Унифицированный платёж закупки — либо подтверждённый Payment, либо
    ещё не подтверждённое предложение матчера BankPayment.matched_purchase_id."""
    id: int
    number: Optional[str]
    date: object
    amount: Optional[Decimal]
    purpose_text: Optional[str]
    confirmed: bool


def _sources_from_payments(rows: list[Payment]) -> list[PaymentSource]:
    return [
        PaymentSource(id=p.id, number=p.document_number, date=p.payment_date,
                      amount=p.amount, purpose_text=p.payment_purpose, confirmed=True)
        for p in rows
    ]


def _sources_from_bank_payments(rows: list[BankPayment], exclude_ids: set[int]) -> list[PaymentSource]:
    return [
        PaymentSource(id=bp.id, number=bp.payment_number, date=bp.payment_date,
                      amount=bp.amount, purpose_text=bp.purpose_text, confirmed=False)
        for bp in rows if bp.id not in exclude_ids
    ]


async def _purchase_payment_sources(db: AsyncSession, purchase_id: int) -> list[PaymentSource]:
    """Единая загрузка обоих источников платежей ОДНОЙ закупки (для эндпоинтов
    /{pid}/vat-payment-check и /{pid}/align-vat-to-payments — не N+1, т.к. один
    purchase_id, два простых запроса)."""
    confirmed = (await db.execute(
        select(Payment)
        .where(Payment.purchase_id == purchase_id, Payment.matched_confirmed == True)  # noqa: E712
        .order_by(Payment.payment_date)
    )).scalars().all()
    confirmed_bank_ids = {p.bank_payment_id for p in confirmed if p.bank_payment_id}

    unconfirmed = (await db.execute(
        select(BankPayment)
        .where(BankPayment.matched_purchase_id == purchase_id)
        .order_by(BankPayment.payment_date)
    )).scalars().all()

    return _sources_from_payments(confirmed) + _sources_from_bank_payments(unconfirmed, confirmed_bank_ids)


def _payment_row(src: PaymentSource) -> dict:
    parsed = parse_payment_vat(src.purpose_text, src.amount)
    return {
        "id": src.id,
        "number": src.number,
        "date": src.date,
        "amount": src.amount,
        "vat_amount": parsed["vat_amount"],
        "rate": parsed["rate"],
        "kind": parsed["kind"],
        "label": format_vat_label(parsed),
        "confirmed": src.confirmed,
    }


def _purchase_expected_vat(purchase: Purchase) -> dict:
    """Ожидаемый НДС закупки → {label, expected_rate, unspecified, mixed, share_pct}.

    vat_mode='uniform' (или не задан) — ставка из шапки закупки (vat_applicable/vat_rate).
    vat_mode='per_item' — ставка построчная (PurchaseItem.vat_rate); одна на все
    позиции → как uniform, разные → 'mixed' со сравнением ДОЛИ НДС в общей сумме
    закупки (та же формула, что и в генераторе документов).
    """
    vat_mode = getattr(purchase, "vat_mode", None) or "uniform"
    if vat_mode == "per_item":
        items = [it for it in (purchase.items or [])]
        items_with_vat = [it for it in items if getattr(it, "vat_rate", None)]
        if not items_with_vat:
            return {"label": "не указано", "expected_rate": None, "unspecified": True, "mixed": False, "share_pct": None}
        unique_rates = sorted({str(it.vat_rate) for it in items_with_vat})
        if len(unique_rates) == 1:
            rate_val = Decimal(str(_parse_vat_rate_percent(unique_rates[0])))
            return {"label": f"{rate_val:g}%", "expected_rate": rate_val, "unspecified": False, "mixed": False, "share_pct": None}
        total_gross = sum((Decimal(str(it.total_price or 0)) for it in items), Decimal("0"))
        total_vat = sum((Decimal(str(_item_vat_amount(it))) for it in items_with_vat), Decimal("0"))
        share_pct = (total_vat / total_gross * 100) if total_gross else Decimal("0")
        return {
            "label": f"смешанная НДС ~{share_pct:.1f}% (по позициям: {', '.join(unique_rates)})",
            "expected_rate": None, "unspecified": False, "mixed": True, "share_pct": share_pct,
        }

    vat_applicable = getattr(purchase, "vat_applicable", None)
    vat_rate = getattr(purchase, "vat_rate", None)
    if vat_applicable is False:
        return {"label": "без НДС", "expected_rate": Decimal("0"), "unspecified": False, "mixed": False, "share_pct": None}
    if vat_applicable is None:
        return {"label": "не указано", "expected_rate": None, "unspecified": True, "mixed": False, "share_pct": None}
    if vat_rate is None:
        return {"label": "не указано (ставка не задана)", "expected_rate": None, "unspecified": True, "mixed": False, "share_pct": None}
    return {"label": f"{vat_rate}%", "expected_rate": Decimal(str(vat_rate)), "unspecified": False, "mixed": False, "share_pct": None}


def _agreed_payments_vat(payments_rows: list[dict]) -> tuple[Optional[dict], list[dict]]:
    """Среди распознанных (kind != 'unknown') платежей — сходятся ли они к одной ставке.

    Возвращает (agreed | None, recognized_rows). agreed = {'rate': Decimal, 'kind': str}
    когда все распознанные платежи попадают в один и тот же грубый разряд ставки
    (округление до целого для 'rate', до 1 знака для 'nonstandard'; 'no_vat' → 0).
    None, если распознанных платежей нет ИЛИ они не сходятся (payments_disagree).
    Учитывает и подтверждённые, и неподтверждённые (matched_purchase_id) платежи —
    confirmed=False не исключается из сходимости ставки, но остаётся видимым в
    выдаче (см. поле "confirmed" в _payment_row).
    """
    recognized = [r for r in payments_rows if r["kind"] != "unknown"]
    if not recognized:
        return None, recognized
    keys = set()
    for r in recognized:
        if r["kind"] == "no_vat":
            keys.add(("no_vat", Decimal("0")))
        else:
            rate = r["rate"] if r["rate"] is not None else Decimal("-1")
            keys.add((r["kind"], rate.quantize(Decimal("0.1"))))
    if len(keys) != 1:
        return None, recognized
    kind, rate = next(iter(keys))
    return {"rate": rate, "kind": kind}, recognized


def check_purchase_vat(purchase: Purchase, payments: list) -> dict:
    """Единственная функция сверки НДС закупки с её платежами.

    payments — список PaymentSource (или ORM Payment — оставлено для обратной
    совместимости тестов/вызовов, у Payment тоже есть .id/.document_number/
    .payment_date/.amount/.payment_purpose, но не .confirmed — в этом случае
    считаем confirmed=True, старое поведение до доработки 2026-09-26).
    """
    def _row(p):
        if isinstance(p, PaymentSource):
            return _payment_row(p)
        # ORM Payment (или похожий объект без .confirmed) — трактуем как подтверждённый.
        return _payment_row(PaymentSource(
            id=p.id, number=getattr(p, "document_number", None), date=getattr(p, "payment_date", None),
            amount=getattr(p, "amount", None), purpose_text=getattr(p, "payment_purpose", None),
            confirmed=getattr(p, "confirmed", True),
        ))

    payments_rows = [_row(p) for p in payments]
    expected = _purchase_expected_vat(purchase)

    if not payments_rows:
        return {
            "status": "no_payments", "purchase_vat_label": expected["label"],
            "payments": [], "suggested": None,
        }

    agreed, recognized = _agreed_payments_vat(payments_rows)
    if not recognized:
        return {
            "status": "no_payments", "purchase_vat_label": expected["label"],
            "payments": payments_rows, "suggested": None,
        }
    if agreed is None:
        return {
            "status": "payments_disagree", "purchase_vat_label": expected["label"],
            "payments": payments_rows, "suggested": None,
        }

    agreed_rate = agreed["rate"]  # Decimal, 0 для no_vat
    suggested = {
        "vat_applicable": agreed_rate > 0,
        "vat_rate": int(agreed_rate) if agreed_rate == agreed_rate.to_integral_value() and agreed_rate > 0 else (float(agreed_rate) if agreed_rate > 0 else None),
    }

    if expected["unspecified"]:
        status = "unknown_purchase_vat"
    elif expected["mixed"]:
        # Сравниваем ДОЛЮ НДС в сумме позиций с ДОЛЕЙ НДС платежей (vat/amount), не со ставкой "сверху".
        payment_shares = []
        for r in recognized:
            if r["kind"] == "no_vat":
                payment_shares.append(Decimal("0"))
            elif r["vat_amount"] is not None and r["amount"]:
                payment_shares.append(Decimal(str(r["vat_amount"])) / Decimal(str(r["amount"])) * 100)
        avg_share = (sum(payment_shares) / len(payment_shares)) if payment_shares else None
        if avg_share is not None and expected["share_pct"] is not None and abs(avg_share - expected["share_pct"]) <= SHARE_TOLERANCE:
            status = "ok"
        else:
            status = "mismatch"
    else:
        if expected["expected_rate"] is not None and abs(agreed_rate - expected["expected_rate"]) <= RATE_TOLERANCE:
            status = "ok"
        else:
            status = "mismatch"

    return {
        "status": status,
        "purchase_vat_label": expected["label"],
        "payments": payments_rows,
        "suggested": suggested if status in ("mismatch", "unknown_purchase_vat") else None,
    }


async def find_vat_mismatches(db: AsyncSession, current_user, subsidy_id: Optional[int] = None) -> list[dict]:
    """Список закупок с расхождением НДС между шапкой и платежами (подтверждёнными
    и/или предложенными матчером, см. докстринг модуля).

    Видимость — та же композиция, что и в app/routers/purchases.py::list_purchases
    (org_filter + user_subsidy_access grants + build_visibility_clause + org-lead
    safety net на assigned_user_id IS NULL) — не заводим второй алгоритм видимости.
    """
    q = select(Purchase.id).join(Subsidy, Purchase.subsidy_id == Subsidy.id, isouter=True)

    org_ids = get_org_filter(current_user)
    granted_ids = set((await db.execute(
        select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == current_user.id)
    )).scalars().all())
    if org_ids is not None:
        q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))

    clause = await build_visibility_clause(current_user, db, 'purchase')
    if clause is not None:
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (current_user.role in ADMIN_ROLES or (vuids is not None and len(vuids) > 1))
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        q = q.where(clause)

    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)

    # Видимые закупки, у которых есть ХОТЬ ОДИН платёж любого из двух
    # источников — иначе find_vat_mismatches гонял бы check_purchase_vat по
    # всей видимой странице.
    q = q.where(or_(
        Purchase.id.in_(select(Payment.purchase_id).where(Payment.matched_confirmed == True, Payment.purchase_id.isnot(None))),  # noqa: E712
        Purchase.id.in_(select(BankPayment.matched_purchase_id).where(BankPayment.matched_purchase_id.isnot(None))),
    ))

    visible_ids_with_payments = (await db.execute(q)).scalars().all()
    if not visible_ids_with_payments:
        return []

    purchases = (await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id.in_(visible_ids_with_payments))
    )).scalars().all()

    subsidy_ids = {p.subsidy_id for p in purchases if p.subsidy_id}
    subsidy_names: dict[int, str] = {}
    if subsidy_ids:
        subsidy_names = dict((await db.execute(
            select(Subsidy.id, Subsidy.name).where(Subsidy.id.in_(subsidy_ids))
        )).all())

    # Источник 1 — подтверждённые Payment (2 запроса на ВСЮ выборку, не N+1).
    confirmed_rows = (await db.execute(
        select(Payment)
        .where(Payment.purchase_id.in_(visible_ids_with_payments), Payment.matched_confirmed == True)  # noqa: E712
        .order_by(Payment.payment_date)
    )).scalars().all()
    confirmed_by_purchase: dict[int, list[Payment]] = {}
    confirmed_bank_ids: set[int] = set()
    for pmt in confirmed_rows:
        confirmed_by_purchase.setdefault(pmt.purchase_id, []).append(pmt)
        if pmt.bank_payment_id:
            confirmed_bank_ids.add(pmt.bank_payment_id)

    # Источник 2 — BankPayment.matched_purchase_id, не превратившиеся в
    # подтверждённый Payment (дедуп через confirmed_bank_ids, без двойного счёта).
    unconfirmed_rows = (await db.execute(
        select(BankPayment)
        .where(BankPayment.matched_purchase_id.in_(visible_ids_with_payments))
        .order_by(BankPayment.payment_date)
    )).scalars().all()
    unconfirmed_by_purchase: dict[int, list[BankPayment]] = {}
    for bp in unconfirmed_rows:
        if bp.id in confirmed_bank_ids:
            continue
        unconfirmed_by_purchase.setdefault(bp.matched_purchase_id, []).append(bp)

    payments_by_purchase: dict[int, list[PaymentSource]] = {}
    for pid in visible_ids_with_payments:
        sources = _sources_from_payments(confirmed_by_purchase.get(pid, []))
        sources += _sources_from_bank_payments(unconfirmed_by_purchase.get(pid, []), confirmed_bank_ids)
        payments_by_purchase[pid] = sources

    out = []
    for p in purchases:
        result = check_purchase_vat(p, payments_by_purchase.get(p.id, []))
        if result["status"] in ("mismatch", "unknown_purchase_vat"):
            out.append({
                "id": p.id,
                "purchase_number": p.purchase_number,
                "subject": p.subject,
                "subsidy_id": p.subsidy_id,
                "subsidy_name": subsidy_names.get(p.subsidy_id),
                "purchase_vat_label": result["purchase_vat_label"],
                "payments": result["payments"],
                "suggested": result["suggested"],
                "status": result["status"],
            })
    return out
