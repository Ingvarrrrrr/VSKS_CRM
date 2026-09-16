"""generate_document: contract date parts, amounts and VAT computation.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).

NOTE: resolve_vat_exemption_article() previously reproduced a pre-existing
UnboundLocalError on `art` when vat_applicable=False and
purchase_method='advance' (`art` was only assigned in the final `else`
branch). Fixed 2026-09 — see the function's docstring; `art` is now always
resolved via `_resolve_vat_exemption_basis(p)` when vat_app is False,
regardless of is_advance, matching fabrikant_package.py's equivalent code
which never had this bug (`art` is NOT put in compute_amounts_and_vat()'s
returned dict for the same reason as before — the vat_app=True case never
needs it; see that function's comment).
"""
import re
from datetime import date
from decimal import Decimal

from app.models.purchase import Purchase
from app.services.documents.contexts import _resolve_doc_amount
from app.services.documents.templates import _resolve_vat_exemption_basis
from app.services.documents.formatting import _fmt_money_plain
from app.services.purchase_amounts import contract_amount as _contract_amount_fn, purchase_amounts as _purchase_amounts_fn


def _parse_vat_rate_percent(rate) -> float:
    """Числовой процент из строки ставки НДС позиции ('5%', '20', None).

    Тот же принцип, что и во фронтовом composables/useVatCalc.ts::
    parseVatRatePercent — единственное на бэке место, где нужна эта же
    математика (см. compute_amounts_and_vat ниже, ветка vat_mode='per_item').
    """
    if not rate:
        return 0.0
    m = re.match(r'^(\d+(?:\.\d+)?)\s*%?$', str(rate).strip())
    return float(m.group(1)) if m else 0.0


def _item_vat_amount(item) -> float:
    """НДС, выделенный из ВКЛЮЧАЮЩЕЙ НДС суммы позиции (total_price) — та же
    формула и то же допущение («total_price уже с НДС»), что и у
    composables/useVatCalc.ts::vatAmount на фронте."""
    total = float(getattr(item, "total_price", None) or 0)
    pct = _parse_vat_rate_percent(getattr(item, "vat_rate", None))
    if pct <= 0:
        return 0.0
    return round(total * pct / (100 + pct), 2)


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

    # ПРАВИЛО №6 (волна 4b-2d): total_nmcd/total_nmck/nmck в contexts_build.py
    # раньше собирались truthy-цепочкой `p.total_nmck or p.nmck or
    # p.planned_total_price or items_sum_val` — три поля-мирроры одного и того
    # же плана (см. app.services.purchase_money_writer: planned_total_price ==
    # total_nmck == nmck по построению) плюс `or`, который путал легитимный 0
    # с «пусто». Единственно нужное значение — purchase_amounts(p).plan (сырая
    # planned_total_price), с фолбэком на Σ плановых позиций для закупок, у
    # которых plan ещё не проставлен (та же семантика «до-договора» бакета
    # purchase_amounts, независимая от текущей стадии — комментарий владельца
    # «НМЦК по определению начальная плановая цена»).
    _plan_pa = _purchase_amounts_fn(
        p,
        items_total=Decimal(str(items_sum_val)) if (p.items or []) else None,
    )
    plan_amount_val = float(_plan_pa.plan) if _plan_pa.plan is not None else items_sum_val

    # "contract_price"/"contract_price_num"/"contract_price_words" — «цена
    # договора», раньше три отдельные копии `p.contract_price or doc_amount_val`
    # (тот же truthy-баг на contract_price=0). Единственный источник — та же
    # contract_amount(), что уже применяется в _resolve_doc_amount() для
    # CONTRACT_FAMILY_DOC_TYPES; фолбэк на doc_amount_val сохранён (владелец,
    # исходный комментарий: «если договор ещё не заключён»).
    _ci_for_contract = getattr(p, "contract_items", None) or []
    _ci_total_for_contract = (
        Decimal(str(sum((ci.total or 0) for ci in _ci_for_contract))) if _ci_for_contract else None
    )
    _contract_amount_raw = _contract_amount_fn(p, contract_items_total=_ci_total_for_contract)
    contract_amount_val = float(_contract_amount_raw) if _contract_amount_raw is not None else doc_amount_val

    # VAT calculations.
    # Ставка берётся ТОЛЬКО из того, что ввёл пользователь — никаких
    # придуманных значений по умолчанию (владелец, 2026-09-04: «нет НДС
    # 20 — сами ставим процент НДС, он у всех разный»). None означает
    # «не указана», 0 — валидная ставка НДС 0%; `or 20` раньше путал эти
    # два случая. Для doc_type, которые реально печатают ставку,
    # None+vat_applicable уже отбит выше в _require_vat_rate_for_doc —
    # сюда с таким сочетанием можно дойти только для остальных doc_type,
    # где vat_rate/vat_info_line в шаблоне не используются.
    is_advance = (p.purchase_method == 'advance')
    items_with_vat = [it for it in (p.items or []) if getattr(it, 'vat_rate', None)]
    vat_mode = (getattr(p, "vat_mode", None) or "uniform")

    if vat_mode == "per_item":
        # Режим «НДС для каждой позиции» (владелец, закупка РЕЕ-2026-00918,
        # 2026-09-16) — ставка не в шапке, а построчно в PurchaseItem.vat_rate.
        # _require_vat_rate_for_doc уже отбил случай, когда у части названных
        # позиций ставка пуста — сюда попадают только закупки, где у всех
        # позиций (или их вовсе нет) ставка проставлена. Переиспользуем ту же
        # формулу «НДС из суммы, ВКЛЮЧАЮЩЕЙ НДС», что и у построчных
        # vat_amount/total_with_vat во фронтовом composables/useVatCalc.ts —
        # см. _item_vat_amount выше, никакого нового расчёта не заводим.
        priced_items = [it for it in items_with_vat]
        if priced_items:
            vat_app = True
            vat_amount_val = round(sum(_item_vat_amount(it) for it in priced_items), 2)
            unique_rates = sorted({str(it.vat_rate) for it in priced_items})
            if len(unique_rates) == 1:
                vat_rate_val = int(_parse_vat_rate_percent(unique_rates[0]))
                vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
            else:
                # Разные ставки у разных позиций — единого числа для {{vat_rate}}
                # нет, полная картина только в vat_info_line (как и в advance-ветке
                # ниже для того же случая).
                vat_rate_val = None
                vat_info_line = f"НДС по позициям ({', '.join(unique_rates)}): {_fmt_money_plain(vat_amount_val)} руб."
        else:
            # Позиций с проставленной ставкой нет (пустая закупка) — не
            # придумываем ни ставку, ни основание освобождения.
            vat_app = False
            vat_rate_val = None
            vat_amount_val = 0.0
            vat_info_line = "НДС не облагается"
    else:
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
        "plan_amount_val": plan_amount_val,
        "contract_amount_val": contract_amount_val,
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
        # (including vat_app=True) — unnecessary work for a value that's
        # discarded when vat_app=True. See resolve_vat_exemption_article()
        # below, which preserves that same short-circuit.
    }


def resolve_vat_exemption_article(p: Purchase, vat_app: bool, is_advance: bool) -> str:
    """"vat_exemption_article" for the docxtpl context.

    Fix (2026-09): the previous version left `art` unassigned when
    vat_app=False and is_advance=True, causing an UnboundLocalError (500) on
    every advance-purchase document without VAT. `_resolve_vat_exemption_basis`
    is generic — it only looks at the manually entered article / contractor
    self-employment / GPH-individual contract form, none of which depend on
    purchase_method — so it applies identically for advance purchases, exactly
    like fabrikant_package.py already does (that function never special-cased
    is_advance here and always resolved `art` in its single `else` branch).
    `is_advance` is kept as a parameter for call-site/API compatibility even
    though it no longer changes this function's behaviour.
    """
    if vat_app:
        return ""
    return _resolve_vat_exemption_basis(p)
