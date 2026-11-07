"""Парсер интерактивного заполняемого PDF-бланка ТКП «Приложение_2_Форма_ТКП.pdf».

Поддерживает:
1. 100%-точный roundtrip через AcroForm widgets (`fitz` / PyMuPDF);
2. Fallback при печати в плоский PDF («Print to PDF») через разбор таблиц и текста.

ПРАВИЛО №5: компактный модуль (< 300 строк).
ПРАВИЛО №6: единый расчет форматирования НДС и выявления аналогов.
"""
import json
import re
from typing import Any, Dict, List, Optional

import fitz

from .analog_matcher import clean_str, detect_alternative, parse_num
from .results import format_vat_label
from .winner_apply_service import normalize_item_vat_rate

TKP_PDF_MARKER = "GALA_TKP_PDF_V1"


def parse_standardized_tkp_pdf(
    file_bytes: bytes,
    purchase_items: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Проверяет и разбирает заполненный PDF-бланк ТКП («Приложение_2_Форма_ТКП.pdf»)."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        return None

    widgets: Dict[str, str] = {}
    full_text_list: List[str] = []
    for page in doc:
        full_text_list.append(page.get_text() or "")
        for w in (page.widgets() or []):
            if w.field_name:
                widgets[w.field_name] = (w.field_value or "").strip()

    full_text = "\n".join(full_text_list)
    has_marker = (
        TKP_PDF_MARKER in full_text
        or "ФОРМА ТЕХНИКО-КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ" in full_text.upper()
    )
    has_widgets = bool(
        "supplier_name" in widgets or "inn" in widgets or "item_0_unit_price" in widgets or "item_0_meta" in widgets
    )
    if not has_marker and not has_widgets:
        return None

    if has_widgets:
        return _parse_from_widgets(widgets, purchase_items)
    return _parse_from_flat_pdf(doc, full_text, purchase_items)


def _build_protocol_dict(
    supplier_name: str,
    inn: str,
    kpp: str,
    contacts: str,
    outgoing_ref: str,
    validity_days: Optional[int],
    vat_label: str,
    admitted: bool,
    rejection_reason: str,
    positions: List[Dict[str, Any]],
    explicit_total: Optional[float] = None,
) -> Dict[str, Any]:
    total = explicit_total or round(sum((p.get("total_price") or 0.0) for p in positions), 2)
    dec_text = (
        "Признать соответствующей требованиям закупочной документации."
        if admitted
        else f"Не соответствует. {rejection_reason}"
    )
    app = {
        "app_id": "1",
        "application_number": "1",
        "app_number": 1,
        "supplier_name": supplier_name or "Участник (Форма ТКП)",
        "supplier_short_name": "",
        "inn": inn,
        "kpp": kpp,
        "contacts": contacts,
        "outgoing_ref": outgoing_ref,
        "validity_days": validity_days,
        "submitted_at": outgoing_ref,
        "price": total if total > 0 else None,
        "price_with_vat": total,
        "price_without_vat": total,
        "vat_label": vat_label,
        "admitted": admitted,
        "rejection_reason": rejection_reason,
        "decision_text": dec_text,
        "place": 1 if admitted else None,
        "positions": positions,
        "documents": [],
    }
    return {
        "procedure_number": "",
        "lot_name": "",
        "protocol_date": None,
        "is_single_application": True,
        "application": app,
        "applications": [app],
    }


def _parse_from_widgets(
    widgets: Dict[str, str],
    purchase_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    supplier_name = clean_str(widgets.get("supplier_name", ""))
    inn = re.sub(r"\D", "", clean_str(widgets.get("inn", "")))
    kpp = re.sub(r"\D", "", clean_str(widgets.get("kpp", "")))
    contacts = clean_str(widgets.get("contacts", ""))
    vat_label = format_vat_label(clean_str(widgets.get("vat_rate", "")) or "Без НДС")
    validity_raw = widgets.get("validity_days", "30")
    outgoing_ref = clean_str(widgets.get("outgoing_ref", ""))

    validity_days = None
    if validity_raw:
        try:
            validity_days = int(parse_num(validity_raw))
        except (ValueError, TypeError):
            validity_days = None

    admitted = True
    rejection_reason = ""
    if validity_days is not None and validity_days < 30:
        admitted = False
        rejection_reason = (
            f"Срок действия технико-коммерческого предложения составляет {int(validity_days)} раб. дн. "
            f"(по условиям документации о закупке требуется не менее 30 рабочих дней)"
        )

    positions: List[Dict[str, Any]] = []
    idx = 0
    while True:
        meta_k = f"item_{idx}_meta"
        price_k = f"item_{idx}_unit_price"
        if meta_k not in widgets and price_k not in widgets and not (purchase_items and idx < len(purchase_items)):
            break

        req_name, req_specs, unit, qty, p_item_id = "", "", "шт.", 0.0, None
        if meta_k in widgets and widgets[meta_k]:
            try:
                meta = json.loads(widgets[meta_k])
                req_name = clean_str(meta.get("name", ""))
                req_specs = clean_str(meta.get("description", ""))
                unit = clean_str(meta.get("unit", "шт.")) or "шт."
                qty = float(meta.get("quantity", 0.0))
                p_item_id = meta.get("item_id")
            except Exception:
                pass

        if not req_name and purchase_items and idx < len(purchase_items):
            p_it = purchase_items[idx]
            req_name = clean_str(p_it.get("name") or p_it.get("item_name") or "")
            req_specs = clean_str(p_it.get("description") or "")
            unit = clean_str(p_it.get("unit") or "шт.") or "шт."
            qty = float(p_it.get("quantity") or 0.0)
            p_item_id = p_it.get("id")

        offer_type = clean_str(widgets.get(f"item_{idx}_offer_type", "По ТЗ Заказчика"))
        offered_specs = clean_str(widgets.get(f"item_{idx}_offered_specs", ""))
        vat_pos = normalize_item_vat_rate(widgets.get(f"item_{idx}_vat_rate"), vat_label)
        u_price = parse_num(widgets.get(f"item_{idx}_unit_price"))
        t_price = parse_num(widgets.get(f"item_{idx}_total_price"))
        if (t_price <= 0.0 or not t_price) and u_price > 0 and qty > 0:
            t_price = round(qty * u_price, 2)

        offer_lower = (offer_type or "").lower()
        is_alt = ("аналог" in offer_lower or "эквивалент" in offer_lower)
        if not is_alt and offered_specs:
            alt_res, _ = detect_alternative(req_name, req_specs, offered_specs, offered_specs)
            if alt_res:
                is_alt = True

        offered_name = offered_specs.split("\n")[0].strip()[:250] if (is_alt and offered_specs) else req_name
        positions.append({
            "item_num": idx + 1,
            "purchase_item_id": p_item_id,
            "requested_name": req_name,
            "requested_specs": req_specs,
            "offered_name": offered_name,
            "offered_specs": offered_specs or req_specs,
            "unit": unit,
            "quantity": qty,
            "unit_price": u_price,
            "total_price": t_price,
            "vat_rate": vat_pos,
            "is_alternative": is_alt,
            "compliance_status": "analog_pending" if is_alt else "compliant",
            "compliance_note": ("Указан эквивалент / аналог" if is_alt else ""),
            "decision": "analog_pending" if is_alt else "accepted",
        })
        idx += 1

    explicit_tot = parse_num(widgets.get("grand_total_price")) or None
    return _build_protocol_dict(
        supplier_name=supplier_name,
        inn=inn,
        kpp=kpp,
        contacts=contacts,
        outgoing_ref=outgoing_ref,
        validity_days=validity_days,
        vat_label=vat_label,
        admitted=admitted,
        rejection_reason=rejection_reason,
        positions=positions,
        explicit_total=explicit_tot,
    )


def _parse_from_flat_pdf(
    doc: Any,
    full_text: str,
    purchase_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Разбор распечатанного в плоский PDF бланка ТКП."""
    m_name = re.search(r"Наименование участника[^\n:]*:\s*(.+?)(?:\n|ИНН|$)", full_text, re.IGNORECASE)
    m_inn = re.search(r"ИНН[^\d]*(\d{10,12})", full_text)
    m_kpp = re.search(r"КПП[^\d]*(\d{9})", full_text)
    m_vat = re.search(r"Ставка НДС[^\n:]*:\s*(.+?)(?:\n|Срок|$)", full_text, re.IGNORECASE)
    m_val = re.search(r"Срок действия[^\d]*(\d+)", full_text, re.IGNORECASE)

    val_days = int(m_val.group(1)) if m_val else 30
    admitted = val_days >= 30
    rej = "" if admitted else f"Срок действия технико-коммерческого предложения составляет {val_days} раб. дн. (требуется не менее 30)"

    all_rows: List[List[str]] = []
    for page in doc:
        for tab in page.find_tables():
            df = tab.extract()
            if df:
                all_rows.extend(df)

    positions: List[Dict[str, Any]] = []
    for r in all_rows:
        if not r or len(r) < 6:
            continue
        c0 = clean_str(r[0])
        if not c0.isdigit():
            continue
        idx = int(c0)
        p_item_id = int(r[1]) if len(r) > 1 and clean_str(r[1]).isdigit() else idx
        req_name = clean_str(r[2]) if len(r) > 2 else ""
        req_specs = clean_str(r[3]) if len(r) > 3 else ""
        unit = clean_str(r[4]) if len(r) > 4 else "шт."
        qty = parse_num(r[5]) if len(r) > 5 else 1.0

        off_type = clean_str(r[6]) if len(r) > 6 else ""
        off_specs = clean_str(r[7]) if len(r) > 7 else ""
        vat_fallback = format_vat_label(clean_str(m_vat.group(1)) if m_vat else "Без НДС")
        if len(r) >= 11:
            vat_pos = normalize_item_vat_rate(clean_str(r[8]), vat_fallback)
            u_price = parse_num(r[9])
            t_price = parse_num(r[10]) or round(qty * u_price, 2)
        else:
            vat_pos = normalize_item_vat_rate("", vat_fallback)
            u_price = parse_num(r[8]) if len(r) > 8 else 0.0
            t_price = parse_num(r[9]) if len(r) > 9 else round(qty * u_price, 2)

        is_alt = ("аналог" in off_type.lower() or "эквивалент" in off_type.lower())
        if not is_alt and off_specs:
            alt_res, _ = detect_alternative(req_name, req_specs, off_specs, off_specs)
            if alt_res:
                is_alt = True

        positions.append({
            "item_num": idx,
            "purchase_item_id": p_item_id,
            "requested_name": req_name,
            "requested_specs": req_specs,
            "offered_name": off_specs.split("\n")[0].strip()[:250] if (is_alt and off_specs) else req_name,
            "offered_specs": off_specs or req_specs,
            "unit": unit,
            "quantity": qty,
            "unit_price": u_price,
            "total_price": t_price,
            "vat_rate": vat_pos,
            "is_alternative": is_alt,
            "compliance_status": "analog_pending" if is_alt else "compliant",
            "compliance_note": ("Указан эквивалент / аналог" if is_alt else ""),
            "decision": "analog_pending" if is_alt else "accepted",
        })

    return _build_protocol_dict(
        supplier_name=clean_str(m_name.group(1)) if m_name else "",
        inn=m_inn.group(1) if m_inn else "",
        kpp=m_kpp.group(1) if m_kpp else "",
        contacts="",
        outgoing_ref="",
        validity_days=val_days,
        vat_label=format_vat_label(clean_str(m_vat.group(1)) if m_vat else "Без НДС"),
        admitted=admitted,
        rejection_reason=rej,
        positions=positions,
    )
