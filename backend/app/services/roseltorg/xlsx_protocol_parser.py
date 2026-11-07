"""Парсер многоколоночных сводных Excel-протоколов (например, 'Протокол итоговый.xlsx').

ПРАВИЛО №5: компактный модуль (< 200 строк).
ПРАВИЛО №6: единый расчет мест и форматирование НДС.
"""
import io
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .analog_matcher import clean_str, detect_alternative, parse_num
from .results import format_vat_label, recalculate_places


def parse_standardized_tkp_sheet(ws_val: Any, ws_formula: Any = None) -> Optional[Dict[str, Any]]:
    """Разбирает стандартизированную форму ТКП ('Приложение_2_Форма_ТКП.xlsx'),

    включая устойчивый поиск реквизитов и колонок, если поставщик скопировал
    таблицу в свой файл со сдвигом строк/колонок и без маркера GALA_TKP_V1.
    """
    if ws_val is None:
        return None

    # 1. Проверка прямого маркера GALA_TKP_V1 или заголовка
    marker_j1 = clean_str(ws_val.cell(1, 10).value)
    title_a1 = clean_str(ws_val.cell(1, 1).value).upper()
    is_standard = (marker_j1 == "GALA_TKP_V1" or "ФОРМА ТЕХНИКО-КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ" in title_a1)

    # 2. Если прямого маркера нет, ищем маркеры ТКП в первых 25 строках
    is_shifted = False
    if not is_standard:
        found_kw = 0
        for r in range(1, min(25, ws_val.max_row + 1)):
            for c in range(1, min(15, ws_val.max_column + 1)):
                val = clean_str(ws_val.cell(r, c).value).lower()
                if "наименование участника" in val:
                    found_kw += 2
                elif "инн участника" in val or val.startswith("инн"):
                    found_kw += 1
                elif "срок действия ткп" in val or "срок действия" in val:
                    found_kw += 1
                elif "форма технико-коммерческого" in val:
                    found_kw += 2
        if found_kw >= 2:
            is_shifted = True

    if not is_standard and not is_shifted:
        return None

    # Чтение реквизитов участника
    supplier_name = ""
    inn = ""
    kpp = ""
    contacts = ""
    vat_raw = ""
    validity_days = None
    outgoing_ref = ""

    if is_standard:
        supplier_name = clean_str(ws_val.cell(4, 3).value)
        inn = re.sub(r"\D", "", clean_str(ws_val.cell(5, 3).value))
        kpp = re.sub(r"\D", "", clean_str(ws_val.cell(6, 3).value))
        contacts = clean_str(ws_val.cell(7, 3).value)
        vat_raw = clean_str(ws_val.cell(8, 3).value)
        validity_days_raw = ws_val.cell(9, 3).value
        if validity_days_raw is not None:
            try:
                validity_days = int(parse_num(validity_days_raw))
            except (ValueError, TypeError):
                validity_days = None
        outgoing_ref = clean_str(ws_val.cell(10, 3).value)

    # Динамический поиск реквизитов (если сдвинуто или пустые поля)
    if not supplier_name or not inn or is_shifted:
        for r in range(1, min(25, ws_val.max_row + 1)):
            for c in range(1, min(15, ws_val.max_column + 1)):
                txt = clean_str(ws_val.cell(r, c).value)
                txt_l = txt.lower()
                if "наименование участника" in txt_l and not supplier_name:
                    if ":" in txt and len(txt.split(":", 1)[1].strip()) > 1:
                        supplier_name = txt.split(":", 1)[1].strip()
                    else:
                        for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                            v = clean_str(ws_val.cell(r, nc).value)
                            if v and "наименование" not in v.lower():
                                supplier_name = v
                                break
                elif ("инн участника" in txt_l or txt_l.startswith("инн")) and not inn:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        digits = re.sub(r"\D", "", clean_str(ws_val.cell(r, nc).value))
                        if len(digits) in (10, 12):
                            inn = digits
                            break
                    if not inn:
                        m_inn = re.search(r"(\d{10,12})", txt)
                        if m_inn:
                            inn = m_inn.group(1)
                elif "кпп" in txt_l and not kpp:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        digits = re.sub(r"\D", "", clean_str(ws_val.cell(r, nc).value))
                        if len(digits) == 9:
                            kpp = digits
                            break
                elif ("телефон" in txt_l or "контакт" in txt_l) and not contacts:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        v = clean_str(ws_val.cell(r, nc).value)
                        if v:
                            contacts = v
                            break
                elif ("ставка ндс" in txt_l or txt_l.startswith("ндс")) and not vat_raw:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        v = clean_str(ws_val.cell(r, nc).value)
                        if v:
                            vat_raw = v
                            break
                elif "срок действия" in txt_l and validity_days is None:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        n = parse_num(ws_val.cell(r, nc).value)
                        if n > 0:
                            validity_days = int(n)
                            break
                elif ("исходящ" in txt_l or "исх." in txt_l) and not outgoing_ref:
                    for nc in range(c + 1, min(c + 6, ws_val.max_column + 1)):
                        v = clean_str(ws_val.cell(r, nc).value)
                        if v:
                            outgoing_ref = v
                            break

    vat_label = format_vat_label(vat_raw or "Без НДС")
    if validity_days is None and not is_shifted:
        validity_days = 30

    admitted = True
    rejection_reason = ""
    if validity_days is not None and validity_days < 30:
        admitted = False
        rejection_reason = (
            f"Срок действия технико-коммерческого предложения составляет {int(validity_days)} раб. дн. "
            f"(по условиям документации о закупке требуется не менее 30 рабочих дней)"
        )

    # 3. Динамический поиск строки заголовка таблицы товаров
    hdr_row = 12 if is_standard else None
    col_map = {
        "num": 1, "id": 2, "name": 3, "desc": 4, "unit": 5,
        "qty": 6, "offer_type": 7, "offered_specs": 8, "unit_price": 9, "vat_rate": 10, "total_price": 11,
    }

    for r in range(1, min(30, ws_val.max_row + 1)):
        row_txt = " ".join(clean_str(ws_val.cell(r, c).value).lower() for c in range(1, ws_val.max_column + 1))
        if ("наименование" in row_txt or "название" in row_txt or "продукци" in row_txt) and ("цена" in row_txt or "стоимост" in row_txt):
            hdr_row = r
            break

    if hdr_row is not None:
        found_cols: Dict[str, int] = {}
        for c in range(1, ws_val.max_column + 1):
            h_val = clean_str(ws_val.cell(hdr_row, c).value).lower()
            if not h_val:
                continue
            if ("№" in h_val or "п/п" in h_val) and "num" not in found_cols:
                found_cols["num"] = c
            elif "id" in h_val and "id" not in found_cols:
                found_cols["id"] = c
            elif ("наименование" in h_val or "название" in h_val or "продукци" in h_val) and "предложен" not in h_val:
                found_cols["name"] = c
            elif ("требован" in h_val or "характеристик" in h_val or "тз" in h_val) and "предложен" not in h_val:
                found_cols["desc"] = c
            elif ("ед." in h_val or "измер" in h_val) and "unit" not in found_cols:
                found_cols["unit"] = c
            elif ("кол-во" in h_val or "количеств" in h_val) and "qty" not in found_cols:
                found_cols["qty"] = c
            elif "тип" in h_val or "аналог" in h_val:
                found_cols["offer_type"] = c
            elif "предложение участника" in h_val or "предлагаем" in h_val or "марка" in h_val or "модель" in h_val:
                found_cols["offered_specs"] = c
            elif ("ставка" in h_val or "ндс" in h_val) and "цена" not in h_val and "стоимост" not in h_val:
                found_cols["vat_rate"] = c
            elif "цена" in h_val and ("ед" in h_val or "штук" in h_val or "руб" in h_val):
                found_cols["unit_price"] = c
            elif "стоимост" in h_val or ("цена" in h_val and "всего" in h_val):
                found_cols["total_price"] = c

        if "name" in found_cols and ("unit_price" in found_cols or "total_price" in found_cols):
            col_map.update(found_cols)

    # Строки товаров
    positions: List[Dict[str, Any]] = []
    r = (hdr_row + 1) if hdr_row else 13
    while r <= ws_val.max_row:
        c1 = clean_str(ws_val.cell(r, col_map["num"]).value) if "num" in col_map else ""
        c3 = clean_str(ws_val.cell(r, col_map["name"]).value) if "name" in col_map else ""
        if "итого" in c1.lower() or "итого" in c3.lower():
            break

        if not c1 and not c3:
            r += 1
            continue

        item_num = int(c1) if c1.isdigit() else len(positions) + 1

        b_val = ws_val.cell(r, col_map["id"]).value if "id" in col_map else None
        p_item_id = None
        if isinstance(b_val, (int, float)) and int(b_val) > 0:
            p_item_id = int(b_val)
        elif isinstance(b_val, str) and b_val.strip().isdigit():
            p_item_id = int(b_val.strip())

        req_name = c3
        req_specs = clean_str(ws_val.cell(r, col_map["desc"]).value) if "desc" in col_map else ""
        unit = (clean_str(ws_val.cell(r, col_map["unit"]).value) if "unit" in col_map else "") or "шт."
        qty = parse_num(ws_val.cell(r, col_map["qty"]).value) if "qty" in col_map else 0.0
        offer_type = clean_str(ws_val.cell(r, col_map["offer_type"]).value) if "offer_type" in col_map else ""
        offered_text = clean_str(ws_val.cell(r, col_map["offered_specs"]).value) if "offered_specs" in col_map else ""
        unit_price = parse_num(ws_val.cell(r, col_map["unit_price"]).value) if "unit_price" in col_map else 0.0

        c10_val = ws_val.cell(r, col_map["total_price"]).value if "total_price" in col_map else None
        t_price = parse_num(c10_val)
        if (t_price == 0.0 or c10_val is None or str(c10_val).startswith("=")) and unit_price > 0 and qty > 0:
            t_price = round(qty * unit_price, 2)

        # Проверка на аналог
        offer_lower = offer_type.lower()
        is_alt = ("аналог" in offer_lower or "эквивалент" in offer_lower)
        if not is_alt and offered_text:
            alt_res, _ = detect_alternative(req_name, req_specs, offered_text, offered_text)
            if alt_res:
                is_alt = True

        if is_alt:
            offered_name = offered_text.split("\n")[0].strip()[:250] if offered_text else req_name
            offered_specs = offered_text or req_specs
            compliance_status = "analog_pending"
            decision = "analog_pending"
        else:
            offered_name = req_name
            offered_specs = offered_text or req_specs
            compliance_status = "compliant"
            decision = "accepted"

        vat_val = clean_str(ws_val.cell(r, col_map["vat_rate"]).value) if "vat_rate" in col_map else ""
        from .winner_apply_service import normalize_item_vat_rate
        pos_vat = normalize_item_vat_rate(vat_val, default_vat_label=vat_label)

        positions.append({
            "item_num": item_num,
            "purchase_item_id": p_item_id,
            "requested_name": req_name,
            "requested_specs": req_specs,
            "offered_name": offered_name,
            "offered_specs": offered_specs,
            "unit": unit,
            "quantity": qty,
            "unit_price": unit_price,
            "total_price": t_price,
            "vat_rate": pos_vat,
            "is_alternative": is_alt,
            "compliance_status": compliance_status,
            "compliance_note": ("Указан эквивалент / аналог" if is_alt else ""),
            "decision": decision,
        })
        r += 1

    total_app_price = round(sum((p.get("total_price") or 0.0) for p in positions), 2)
    decision_text = (
        "Признать соответствующей требованиям закупочной документации."
        if admitted
        else f"Не соответствует. {rejection_reason}"
    )

    app_data = {
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
        "price": total_app_price if total_app_price > 0 else None,
        "price_with_vat": total_app_price if total_app_price > 0 else 0.0,
        "price_without_vat": total_app_price if total_app_price > 0 else 0.0,
        "vat_label": vat_label,
        "admitted": admitted,
        "rejection_reason": rejection_reason,
        "decision_text": decision_text,
        "place": 1 if admitted else None,
        "positions": positions,
        "documents": [],
    }

    return {
        "procedure_number": "",
        "lot_name": clean_str(ws_val.cell(2, 3).value),
        "protocol_date": None,
        "is_single_application": True,
        "application": app_data,
        "applications": [app_data],
    }


def parse_standardized_tkp_workbook(content: bytes) -> Optional[Dict[str, Any]]:
    """Проверяет и парсит стандартизированную форму ТКП из байтов Excel-файла."""
    try:
        import openpyxl
    except ImportError:
        return None

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        return None

    for ws in wb.worksheets:
        res = parse_standardized_tkp_sheet(ws)
        if res is not None:
            return res

    return None


def parse_xlsx_multi_protocol(content: bytes, filename: str, purchase_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Разбирает многоколоночную сводную таблицу Excel (например, 'Протокол итоговый.xlsx')."""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="Библиотека openpyxl не установлена")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось открыть файл Excel: {e}")

    # Ищем лист с участниками среди всех листов книги
    target_ws = None
    participant_cols: List[Tuple[int, str]] = []
    header_row_idx = None

    for candidate_ws in wb.worksheets:
        cols_found = []
        h_row = None
        for r in range(1, 15):
            for c in range(1, candidate_ws.max_column + 1):
                val = clean_str(candidate_ws.cell(r, c).value)
                if "участник №" in val.lower():
                    h_row = r
                    cols_found.append((c, val))
        if cols_found:
            target_ws = candidate_ws
            participant_cols = cols_found
            header_row_idx = h_row
            break

    if not target_ws or not participant_cols or header_row_idx is None:
        return {}

    ws = target_ws

    items_start_row = header_row_idx + 2
    item_rows: List[Dict[str, Any]] = []
    r = items_start_row
    while r <= ws.max_row:
        c1 = clean_str(ws.cell(r, 1).value)
        c2 = clean_str(ws.cell(r, 2).value)
        if "итого" in c1.lower() or "итого" in c2.lower():
            break
        if c1.isdigit():
            item_rows.append({
                "num": int(c1),
                "name": c2,
                "unit": clean_str(ws.cell(r, 3).value),
                "qty": parse_num(ws.cell(r, 4).value),
                "row_idx": r,
            })
        r += 1

    summary_row_idx = r
    status_row_val = {}
    for sub_r in range(summary_row_idx + 1, min(summary_row_idx + 8, ws.max_row + 1)):
        lbl = clean_str(ws.cell(sub_r, 2).value).lower()
        if "предлагаемая продукция" in lbl or "характеристики" in lbl:
            for p_c, _ in participant_cols:
                v = clean_str(ws.cell(sub_r, p_c).value)
                if v and p_c not in status_row_val:
                    status_row_val[p_c] = v

    applications: List[Dict[str, Any]] = []
    for p_idx, (p_col, p_hdr) in enumerate(participant_cols, start=1):
        m_inn = re.search(r"ИНН[:\s]*(\d{10,12})", p_hdr)
        inn = m_inn.group(1) if m_inn else ""
        lines = [l.strip() for l in p_hdr.split("\n") if l.strip()]
        s_name = ""
        for line in lines:
            line_l = line.lower()
            if any(pfx in line_l for pfx in ["ооо", "ип ", "зао", "пао", "ао "]):
                s_name = line
                break
            if not any(skip in line_l for skip in ["участник", "от ", "инн", "тел", "e-mail", "mail"]):
                if not s_name and len(line) > 3:
                    s_name = line
        if not s_name:
            s_name = lines[0] if lines else f"Участник {p_idx}"
        if inn and "инн" in s_name.lower():
            s_name = s_name.split("ИНН")[0].strip()

        positions: List[Dict[str, Any]] = []
        for it in item_rows:
            r_idx = it["row_idx"]
            u_price = parse_num(ws.cell(r_idx, p_col).value)
            t_price = parse_num(ws.cell(r_idx, p_col + 1).value) if p_col + 1 <= ws.max_column else 0.0
            p_item_id = purchase_items[it["num"] - 1].get("id") if purchase_items and it["num"] <= len(purchase_items) else None

            positions.append({
                "item_num": it["num"],
                "purchase_item_id": p_item_id,
                "requested_name": it["name"],
                "requested_specs": "",
                "offered_name": it["name"],
                "offered_specs": "",
                "unit": it["unit"],
                "quantity": it["qty"],
                "unit_price": u_price,
                "total_price": t_price or (u_price * it["qty"]),
                "is_alternative": False,
                "compliance_status": "compliant",
                "compliance_note": "",
            })

        app_total = parse_num(ws.cell(summary_row_idx, p_col).value) or sum(p["total_price"] for p in positions)
        prod_status = status_row_val.get(p_col, "")
        is_admitted = True
        rej_reason = ""

        if "не соответств" in prod_status.lower() or "отказ" in prod_status.lower():
            is_admitted = False
            rej_reason = prod_status
            m_pts = re.findall(r"п\.?\s*(\d+)", prod_status)
            rejected_pts = [int(p) for p in m_pts]
            for pos in positions:
                if pos["item_num"] in rejected_pts:
                    pos["is_alternative"] = True
                    pos["compliance_status"] = "analog_rejected"
                    pos["compliance_note"] = "Не соответствует ТЗ Заказчика"
        elif "аналог" in prod_status.lower():
            for pos in positions:
                pos["is_alternative"] = True
                pos["compliance_status"] = "analog_accepted"

        applications.append({
            "app_id": str(p_idx),
            "application_number": str(p_idx),
            "supplier_name": s_name,
            "inn": inn,
            "kpp": "",
            "price_with_vat": app_total,
            "price_without_vat": app_total,
            "vat_label": "Без НДС" if "не облагается" in p_hdr.lower() else "с НДС",
            "admitted": is_admitted,
            "rejection_reason": rej_reason,
            "decision_text": ("Признать соответствующей требованиям закупочной документации." if is_admitted else f"Не соответствует. {rej_reason}"),
            "positions": positions,
            "documents": [{"name": filename, "source": "uploaded"}],
        })

    recalc = recalculate_places(applications)
    return {
        "registration_number": "",
        "notice_date": "",
        "protocol_number": "",
        "protocol_date": date.today().isoformat(),
        "applications": recalc,
        "total_applications": len(recalc),
        "admitted_count": sum(1 for a in recalc if a.get("admitted")),
        "rejected_count": sum(1 for a in recalc if not a.get("admitted")),
    }
