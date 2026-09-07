"""generate_document: contract date parts, amounts and VAT computation.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).

NOTE (deliberately preserved bug, per refactor instructions — do NOT fix):
resolve_vat_exemption_article() below reproduces the pre-existing
UnboundLocalError on `art` that occurs when vat_applicable=False and
purchase_method='advance'. `art` is only assigned inside its final `else`
branch; when the `elif is_advance` branch runs instead, the closing
`return "" if vat_app else art` references an unassigned local and raises
UnboundLocalError — same as the original inline code's
`"vat_exemption_article": ("" if vat_app else art)` did while building the
big docxtpl context dict (the ternary's short-circuit meant vat_app=True
never touched `art` at all — that must stay true here too, so `art` is
NOT put in compute_amounts_and_vat()'s returned dict; see its comment).
Neither function is wrapped in a try/except by the orchestrator (mirrors
the original, where this segment sat before the try/except added at the
"Phase 26-U" block), so the exception propagates uncaught into a generic
FastAPI 500, exactly as before.
"""
from datetime import date
from decimal import Decimal

from app.models.purchase import Purchase
from app.services.documents.contexts import _resolve_doc_amount
from app.services.documents.templates import _resolve_vat_exemption_basis
from app.services.documents.formatting import _fmt_money_plain


def contract_date_parts(p: Purchase):
    d = p.contract_date
    if not d:
        return "", "", ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return "", "", ""
    months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return str(d.day).zfill(2), months_ru[d.month - 1], str(d.year)


def short_name(full_name: str) -> str:
    """Unused-in-practice helper preserved verbatim from the original function
    (never called at the original call site either — kept for byte-parity)."""
    import re
    m = re.search(r'[«""]([^»""]+)[»""]', full_name)
    if m:
        return m.group(1)
    parts = full_name.split()
    return parts[-1] if parts else full_name


def compute_amounts_and_vat(p: Purchase, doc_type: str) -> dict:
    # Сумма закупки для документов.
    # items_sum_val — сумма ПЛАНОВЫХ позиций, нужна только как последний
    # фолбэк для total_nmcd/total_nmck/nmck ниже (они остаются плановыми
    # полями всегда, независимо от doc_type — НМЦК по определению начальная
    # плановая цена).
    # doc_amount_val/amount_is_planned — сумма ДОКУМЕНТА: для
    # CONTRACT_FAMILY_DOC_TYPES («Плановые не равно Договор») — ТОЛЬКО
    # p.contract_price / сумма ContractItem, без отката на НМЦК/план. Для
    # остальных типов — старое поведение (план/НМЦК до заключения договора).
    items_sum_val = float(sum(Decimal(str(it.total_price or 0)) for it in (p.items or [])))
    doc_amount_val, amount_is_planned = _resolve_doc_amount(p, doc_type)

    # VAT calculations.
    # Ставка берётся ТОЛЬКО из того, что ввёл пользователь — никаких
    # придуманных значений по умолчанию (владелец, 2026-09-04: «нет НДС
    # 20 — сами ставим процент НДС, он у всех разный»). None означает
    # «не указана», 0 — валидная ставка НДС 0%; `or 20` раньше путал эти
    # два случая. Для doc_type, которые реально печатают ставку,
    # None+vat_applicable уже отбит выше в _require_vat_rate_for_doc —
    # сюда с таким сочетанием можно дойти только для остальных doc_type,
    # где vat_rate/vat_info_line в шаблоне не используются.
    vat_app = bool(p.vat_applicable)
    vat_rate_val = p.vat_rate
    price_val = doc_amount_val
    if vat_app and price_val and vat_rate_val is not None:
        vat_amount_val = price_val * vat_rate_val / (100 + vat_rate_val)
    else:
        vat_amount_val = 0.0

    # НДС info for approval sheet
    # Phase 26-TT: для авансового отчёта не придумывать «НДС не облагается» если
    # в чеке/items нет данных VAT — пишем только то, что реально есть.
    is_advance = (p.purchase_method == 'advance')
    items_with_vat = [it for it in (p.items or []) if getattr(it, 'vat_rate', None)]

    if vat_app:
        if vat_rate_val is not None:
            vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
        else:
            # doc_type, печатающие ставку, уже отбиты раньше в
            # _require_vat_rate_for_doc — сюда попадают только те, где
            # vat_info_line в шаблоне не используется; не выдумываем число.
            vat_info_line = "НДС (ставка не указана)"
    elif is_advance:
        # Авансовый: данные из чеков ФНС; если в чеке нет НДС — не пишем ничего лишнего.
        if items_with_vat:
            # Per-item VAT — показать сводку по факту
            unique_rates = sorted({str(it.vat_rate) for it in items_with_vat if it.vat_rate})
            vat_info_line = f"НДС по позициям: {', '.join(unique_rates)}"
        else:
            vat_info_line = ""  # пусто — не придумываем
    else:
        # Основание — введённое человеком ИЛИ определённое автоматически
        # (самозанятый контрагент / договор ГПХ с физлицом), см.
        # _resolve_vat_exemption_basis. Для doc_type из VAT_RATE_PRINTED_DOC_TYPES
        # пустое основание уже отбито раньше в _require_vat_rate_for_doc —
        # сюда с пустым основанием можно дойти только для остальных doc_type.
        art = _resolve_vat_exemption_basis(p)
        vat_info_line = f"НДС не облагается" + (f" ({art})" if art else "")

    return {
        "items_sum_val": items_sum_val,
        "doc_amount_val": doc_amount_val,
        "amount_is_planned": amount_is_planned,
        "vat_app": vat_app,
        "vat_rate_val": vat_rate_val,
        "vat_amount_val": vat_amount_val,
        "is_advance": is_advance,
        "vat_info_line": vat_info_line,
        # NOTE: `art` is intentionally NOT put in this dict. In the original
        # code `art` was referenced inside a ternary
        # ("" if vat_app else art) — Python only evaluates/needs `art` when
        # vat_app is False, so the vat_app=True case never touched it. Putting
        # "art": art here unconditionally would evaluate `art` on EVERY call
        # (including vat_app=True), turning a narrow pre-existing bug into a
        # 500 for the common vat_app=True case — a regression, not a
        # preserved bug. See resolve_vat_exemption_article() below, which
        # reproduces the original ternary's short-circuit exactly.
    }


def resolve_vat_exemption_article(p: Purchase, vat_app: bool, is_advance: bool) -> str:
    """Mirrors the original inline `"vat_exemption_article": ("" if vat_app
    else art)` computation exactly, including the preserved
    UnboundLocalError('art') bug when vat_app=False and is_advance=True —
    `art` is assigned only in the final `else` branch below, exactly like
    the original function-level `art` was assigned only in its `else`
    branch (see compute_amounts_and_vat above)."""
    if vat_app:
        pass
    elif is_advance:
        pass
    else:
        art = _resolve_vat_exemption_basis(p)
    return "" if vat_app else art
