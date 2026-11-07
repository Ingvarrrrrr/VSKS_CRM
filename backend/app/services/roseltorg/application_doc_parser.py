"""Парсер документов заявок, ТКП участников и протоколов с ЭТП (Росэлторг / Фабрикант).

Поддерживаемые форматы:
- .doc (бинарный OLE2 Word протокол с Росэлторга);
- .pdf (протоколы и ТКП участников с попозиционными таблицами и аналогами);
- .docx (форма заявки / ТКП участника и протокол);
- .xlsx (многоколоночные сводные таблицы со сравнением предложений участников и аналогов);
- .zip (архивы с набором протоколов и заявок участников).

ПРАВИЛО №5: компактный модульный файл (< 400 строк).
ПРАВИЛО №6: переиспользование recalculate_places и format_vat_label из results.py.
ПРАВИЛО №8: безопасная обработка без 500 (только 422 с понятным русским описанием).
"""
import io
import os
import re
import zipfile
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from .analog_matcher import (
    build_rejection_reason_for_analogs,
    clean_str,
    detect_alternative,
    parse_num,
    parse_ru_date,
)
from .results import recalculate_places
from .xlsx_protocol_parser import parse_xlsx_multi_protocol


def extract_ole2_text(content: bytes) -> str:
    """Извлекает текст из OLE2 .doc файла через декодирование UTF-16LE фрагментов."""
    raw_blocks: List[str] = []
    for m in re.finditer(b"(?:[\x20-\x7e\x0a\x0d\x09]\x00|[\x00-\xff][\x04])+", content):
        try:
            chunk = m.group(0).decode("utf-16le")
            if len(chunk.strip()) > 1:
                raw_blocks.append(chunk.strip())
        except Exception:
            pass
    return "\n".join(raw_blocks)


def parse_doc_protocol(content: bytes) -> Dict[str, Any]:
    """Парсит OLE2 .doc протокол с Росэлторга."""
    text = extract_ole2_text(content)
    if not text or "ПРОТОКОЛ" not in text:
        raise HTTPException(status_code=422, detail="Файл .doc не содержит распознаваемого протокола площадки")

    reg_number = ""
    m_not = re.search(r"Извещение\s*№?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
    if m_not:
        reg_number = m_not.group(1).strip()

    notice_date = ""
    m_nd = re.search(r"Извещение\s*№?\s*[A-Za-z0-9_-]+\s*от\s*(\d{2}\.\d{2}\.\d{4})", text, re.IGNORECASE)
    if m_nd:
        d_raw = m_nd.group(1)
        notice_date = f"{d_raw[6:10]}-{d_raw[3:5]}-{d_raw[0:2]}"

    protocol_number = ""
    m_pnum = re.search(r"ПРОТОКОЛ\s*№?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
    if m_pnum:
        p_val = m_pnum.group(1).strip()
        protocol_number = f"№{p_val}" if not p_val.startswith("№") else p_val
        if not reg_number:
            reg_number = p_val[:-2] if p_val.endswith("-1") else p_val

    protocol_date = ""
    m_pdate = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})\s*г", text)
    if m_pdate:
        protocol_date = parse_ru_date(m_pdate.group(0)) or ""

    meeting_time = "16:30"
    meeting_address = ""
    m_meet = re.search(r"Место и время проведения заседания Комиссии:\s*(.+?)(?:\s+в\s+(\d{1,2}:\d{2}))", text)
    if m_meet:
        meeting_address = clean_str(m_meet.group(1))
        meeting_time = m_meet.group(2)

    commission_order_number = ""
    commission_order_date = ""
    m_ord = re.search(r"приказом\s*№?\s*([0-9А-Яа-яA-Za-z/-]+)\s+от\s+([0-9\s«»\"'а-яёА-ЯЁ\.]+?)(?:г\.|\s+в\s+составе|\n|$)", text)
    if m_ord:
        commission_order_number = m_ord.group(1).strip()
        commission_order_date = parse_ru_date(m_ord.group(2)) or ""

    members: List[Dict[str, str]] = []
    for m in re.finditer(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s*\n\s*(Председатель Комиссии|Член Комиссии|Секретарь Комиссии|Заместитель председателя Комиссии)", text):
        fio = clean_str(m.group(1))
        role = clean_str(m.group(2))
        if fio and not any(x["full_name"] == fio for x in members):
            members.append({"full_name": fio, "role": role})

    return {
        "registration_number": reg_number,
        "notice_date": notice_date,
        "protocol_number": protocol_number or (f"№{reg_number}-1" if reg_number else ""),
        "protocol_date": protocol_date or date.today().isoformat(),
        "submission_deadline": "",
        "meeting_address": meeting_address,
        "meeting_time": meeting_time,
        "commission_order_number": commission_order_number,
        "commission_order_date": commission_order_date,
        "commission_members": members,
        "applications": [],
        "total_applications": 0,
        "admitted_count": 0,
        "rejected_count": 0,
    }


def parse_pdf_document(content: bytes, filename: str, purchase_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Разбирает PDF файл: сначала стандартизированный бланк ТКП, либо как протокол/заявку."""
    from .pdf_tkp_parser import parse_standardized_tkp_pdf
    tkp_res = parse_standardized_tkp_pdf(content, purchase_items)
    if tkp_res is not None:
        return tkp_res

    try:
        import fitz
    except ImportError:
        raise HTTPException(status_code=500, detail="Библиотека PyMuPDF (fitz) не установлена на сервере")

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось открыть PDF документ: {e}")

    full_text = "\n".join(page.get_text() for page in doc)

    is_protocol = "ПРОТОКОЛ" in full_text and ("РАБОТЫ КОМИССИИ" in full_text or "Комиссия" in full_text)
    is_tkp_or_application = any(kw in full_text for kw in [
        "Форма технико-коммерческого предложения",
        "технико-коммерческого предложения",
        "ФОРМА ЗАЯВКИ",
        "ЗАЯВКА НА УЧАСТИЕ",
        "Предложение о функциональных",
        "ОТ КОГО:",
    ])

    if is_protocol and not is_tkp_or_application:
        return _parse_pdf_protocol_full(doc, full_text)
    else:
        return _parse_pdf_tkp_application(doc, full_text, filename, purchase_items)


def _parse_pdf_protocol_full(doc: Any, full_text: str) -> Dict[str, Any]:
    reg_number = ""
    m_not = re.search(r"Извещение\s*№?\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
    if m_not:
        reg_number = m_not.group(1).strip()

    notice_date = ""
    m_nd = re.search(r"Извещение\s*№?\s*[A-Za-z0-9_-]+\s*от\s*(\d{2}\.\d{2}\.\d{4})", full_text, re.IGNORECASE)
    if m_nd:
        d_raw = m_nd.group(1)
        notice_date = f"{d_raw[6:10]}-{d_raw[3:5]}-{d_raw[0:2]}"

    p_num = f"№{reg_number}-1" if reg_number else ""
    p_date = ""
    m_pdate = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})\s*г", full_text)
    if m_pdate:
        p_date = parse_ru_date(m_pdate.group(0)) or ""

    members: List[Dict[str, str]] = []
    applications: List[Dict[str, Any]] = []

    for page in doc:
        for tab in page.find_tables():
            df = tab.extract()
            if not df:
                continue
            hdr = [clean_str(c).lower() for c in df[0]]
            if any("фио" in h for h in hdr) and any("роль" in h for h in hdr):
                for row in df[1:]:
                    if len(row) >= 2 and clean_str(row[0]):
                        members.append({"full_name": clean_str(row[0]), "role": clean_str(row[1]) or "Член Комиссии"})
            elif any("заявк" in h or "№" in h for h in hdr) and any("наименование" in h or "организаци" in h for h in hdr):
                for r_idx, row in enumerate(df[1:], start=1):
                    if len(row) < 3 or not any(row):
                        continue
                    col0 = clean_str(row[0]).rstrip(".")
                    col1 = clean_str(row[1])
                    col2 = clean_str(row[2]) if len(row) > 2 else ""
                    col3 = clean_str(row[3]) if len(row) > 3 else ""
                    if not col1 and not col2:
                        continue
                    m_inn = re.search(r"(\d{10,12})", col1 + " " + col2)
                    inn = m_inn.group(1) if m_inn else ""
                    m_kpp = re.search(r"КПП[:\s]*(\d{9})", col1 + " " + col2)
                    kpp = m_kpp.group(1) if m_kpp else ""
                    price = parse_num(col2)
                    is_adm = "признать не" not in col3.lower() and "отклон" not in col3.lower()
                    applications.append({
                        "app_id": col0 or str(r_idx),
                        "application_number": col0 or str(r_idx),
                        "supplier_name": col1.split("ИНН")[0].strip().rstrip(",;/ "),
                        "inn": inn,
                        "kpp": kpp,
                        "price_with_vat": price,
                        "price_without_vat": price,
                        "vat_label": "Без НДС" if "без ндс" in col2.lower() else "с НДС",
                        "admitted": is_adm,
                        "rejection_reason": col3 if not is_adm else "",
                        "decision_text": col3 or ("Признать соответствующей" if is_adm else "Не соответствует"),
                        "positions": [],
                        "documents": [],
                    })

    recalc = recalculate_places(applications)
    return {
        "registration_number": reg_number,
        "notice_date": notice_date,
        "protocol_number": p_num,
        "protocol_date": p_date or date.today().isoformat(),
        "commission_members": members,
        "applications": recalc,
        "total_applications": len(recalc),
        "admitted_count": sum(1 for a in recalc if a.get("admitted")),
        "rejected_count": sum(1 for a in recalc if not a.get("admitted")),
    }


def _parse_pdf_tkp_application(doc: Any, full_text: str, filename: str, purchase_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    supp_name = ""
    inn = ""
    m_from = re.search(r"ОТ\s+КОГО:\s*(.+?)(?:ИНН|\n|$)", full_text, re.IGNORECASE)
    if m_from:
        supp_name = clean_str(m_from.group(1)).rstrip(",; ")
    m_inn = re.search(r"ИНН[:\s]*(\d{10,12})", full_text)
    if m_inn:
        inn = m_inn.group(1)

    positions: List[Dict[str, Any]] = []
    total_sum = 0.0

    all_table_rows: List[List[str]] = []
    for page in doc:
        for tab in page.find_tables():
            df = tab.extract()
            if df:
                all_table_rows.extend(df)

    for row in all_table_rows:
        if not row or len(row) < 5:
            continue
        c0 = clean_str(row[0])
        if "итого" in c0.lower() or (len(row) > 1 and "итого" in clean_str(row[1]).lower()):
            total_sum = parse_num(row[-1])
            continue
        if not c0.isdigit():
            continue
        # Пропускаем строку нумерации колонок таблицы [1, 2, 3, 4, 5, 6, 7, 8]
        if len(row) > 2 and clean_str(row[1]) == "2" and clean_str(row[2]) == "3":
            continue

        item_idx = int(c0)
        req_name = clean_str(row[1]) if len(row) > 1 else ""
        if "название" in req_name.lower() or "наименование" in req_name.lower() or "требования" in req_name.lower():
            continue
        req_specs = clean_str(row[2]) if len(row) > 2 else ""
        off_specs = clean_str(row[3]) if len(row) > 3 else ""
        off_name = off_specs.split("\n")[0].strip() if off_specs else req_name
        unit = clean_str(row[4]) if len(row) > 4 else "шт."
        qty = parse_num(row[5]) if len(row) > 5 else 1.0
        unit_price = parse_num(row[6]) if len(row) > 6 else 0.0
        row_total = parse_num(row[7]) if len(row) > 7 else (qty * unit_price)

        is_alt, alt_reason = detect_alternative(req_name, req_specs, off_name, off_specs)
        p_item_id = purchase_items[item_idx - 1].get("id") if purchase_items and item_idx <= len(purchase_items) else None

        positions.append({
            "item_num": item_idx,
            "purchase_item_id": p_item_id,
            "requested_name": req_name,
            "requested_specs": req_specs,
            "offered_name": off_name or req_name,
            "offered_specs": off_specs,
            "unit": unit,
            "quantity": qty,
            "unit_price": unit_price,
            "total_price": row_total,
            "is_alternative": is_alt,
            "compliance_status": "analog_accepted" if is_alt else "compliant",
            "compliance_note": alt_reason if is_alt else "",
        })

    if not total_sum and positions:
        total_sum = sum(p["total_price"] for p in positions)

    app_data = {
        "supplier_name": supp_name or (f"Участник {inn}" if inn else "Участник закупки"),
        "inn": inn,
        "kpp": "",
        "price_with_vat": total_sum,
        "price_without_vat": total_sum,
        "vat_label": "с НДС" if "в т.ч. ндс" in full_text.lower() else "Без НДС",
        "admitted": True,
        "rejection_reason": "",
        "decision_text": "Признать соответствующей требованиям закупочной документации.",
        "positions": positions,
        "documents": [{"name": filename, "source": "uploaded"}],
    }
    return {"is_single_application": True, "application": app_data}


def parse_docx_application(content: bytes, filename: str, purchase_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Разбирает Word-файл (.docx) как заявку участника ('Форма заявки')."""
    try:
        import docx
    except ImportError:
        raise HTTPException(status_code=500, detail="Библиотека python-docx не установлена")

    try:
        doc = docx.Document(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось открыть документ .docx: {e}")

    supp_info = {"supplier_name": "", "inn": "", "kpp": "", "address": "", "phone": "", "email": ""}

    if doc.tables:
        t0 = doc.tables[0]
        for row in t0.rows:
            if len(row.cells) >= 2:
                k = clean_str(row.cells[0].text).lower()
                v = clean_str(row.cells[1].text)
                if not v:
                    continue
                if "наименование" in k or "фио" in k:
                    if not supp_info["supplier_name"]:
                        supp_info["supplier_name"] = v
                elif "инн" in k:
                    supp_info["inn"] = v
                elif "кпп" in k:
                    supp_info["kpp"] = v
                elif "адрес" in k or "место нахождения" in k:
                    supp_info["address"] = v
                elif "телефон" in k:
                    supp_info["phone"] = v
                elif "почта" in k or "e-mail" in k:
                    supp_info["email"] = v

    positions: List[Dict[str, Any]] = []
    if len(doc.tables) > 1:
        t1 = doc.tables[1]
        for row in t1.rows[1:]:
            cells = [clean_str(c.text) for c in row.cells]
            if not cells or not cells[0].rstrip(".").isdigit():
                continue
            idx = int(cells[0].rstrip("."))
            name = cells[1] if len(cells) > 1 else ""
            unit = cells[2] if len(cells) > 2 else "шт"
            qty = parse_num(cells[3]) if len(cells) > 3 else 1.0
            u_price = parse_num(cells[4]) if len(cells) > 4 else 0.0
            t_price = parse_num(cells[5]) if len(cells) > 5 else (qty * u_price)
            note = cells[6] if len(cells) > 6 else ""

            is_alt = any(w in note.lower() for w in ["аналог", "эквивалент", "замена"]) or any(
                w in name.lower() for w in ["аналог", "эквивалент", "замена"]
            )
            p_item_id = purchase_items[idx - 1].get("id") if purchase_items and idx <= len(purchase_items) else None

            positions.append({
                "item_num": idx,
                "purchase_item_id": p_item_id,
                "requested_name": name,
                "requested_specs": "",
                "offered_name": name,
                "offered_specs": note,
                "unit": unit,
                "quantity": qty,
                "unit_price": u_price,
                "total_price": t_price,
                "is_alternative": is_alt,
                "compliance_status": "analog_accepted" if is_alt else "compliant",
                "compliance_note": note,
            })

    total_sum = sum(p["total_price"] for p in positions)
    app_data = {
        **supp_info,
        "price_with_vat": total_sum,
        "price_without_vat": total_sum,
        "vat_label": "Без НДС",
        "admitted": True,
        "rejection_reason": "",
        "decision_text": "Признать соответствующей требованиям закупочной документации.",
        "positions": positions,
        "documents": [{"name": filename, "source": "uploaded"}],
    }
    return {"is_single_application": True, "application": app_data}


def parse_zip_bundle(content: bytes, filename: str) -> List[Tuple[str, bytes]]:
    """Распаковывает ZIP-архив и возвращает список пар (вложенное_имя, байты)."""
    extracted: List[Tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for zip_info in zf.infolist():
                if zip_info.is_dir():
                    continue
                fname = zip_info.filename
                if "__MACOSX" in fname or os.path.basename(fname).startswith("."):
                    continue
                extracted.append((os.path.basename(fname), zf.read(zip_info)))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось распаковать ZIP-архив {filename}: {e}")
    return extracted
