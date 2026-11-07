"""Парсер файлов протоколов с площадок (Росэлторг / Фабрикант) .docx / .xlsx.

ПРАВИЛО №5: компактный модуль (< 420 строк).
ПРАВИЛО №6: переиспользование recalculate_places и format_vat_label из results.py.
ПРАВИЛО №8: валидные HTTP-коды и понятные русские сообщения об ошибках (не 500).
"""
import io
import re
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .results import recalculate_places, format_vat_label
from .application_doc_parser import (
    parse_doc_protocol,
    parse_pdf_document,
    parse_docx_application,
    parse_zip_bundle,
)
from .xlsx_protocol_parser import parse_xlsx_multi_protocol, parse_standardized_tkp_workbook

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _parse_ru_date(text: str) -> Optional[str]:
    """Разбирает русские даты вида «12» мая 2026 г., 14 августа 2025, 05.08.2025 в YYYY-MM-DD."""
    if not text:
        return None
    # 05.08.2025
    m_num = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m_num:
        return f"{m_num.group(3)}-{m_num.group(2)}-{m_num.group(1)}"
    # «12» мая 2026 г. / "15" августа 2025
    m_text = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})", text)
    if m_text:
        day = int(m_text.group(1))
        month_name = m_text.group(2).lower()
        year = int(m_text.group(3))
        month = RU_MONTHS.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).replace("\xa0", " ").strip()


def parse_protocol_file(
    filename: str,
    content: bytes,
    purchase_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Парсит файл протокола закупки или заявки (.docx, .doc, .xlsx, .pdf, .zip)."""
    fname_lower = (filename or "").lower()
    if fname_lower.endswith(".docx"):
        # Проверяем, не форма ли это заявки/ТКП участника
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            full_text = "\n".join(p.text for p in doc.paragraphs)
            if "форма заявки" in full_text.lower() or any(
                len(t.rows) > 0 and "наименование" in _clean_str(t.rows[0].cells[0].text).lower()
                for t in doc.tables[:1]
            ):
                return parse_docx_application(content, filename, purchase_items)
        except Exception:
            pass
        return _parse_docx_protocol(content)
    elif fname_lower.endswith(".xlsx"):
        # Сначала проверяем стандартизированную форму ТКП (Приложение № 2)
        tkp_res = parse_standardized_tkp_workbook(content)
        if tkp_res:
            return tkp_res
        # Затем пробуем многоколоночный протокол со сравнением предложений
        multi_res = parse_xlsx_multi_protocol(content, filename, purchase_items)
        if multi_res and multi_res.get("applications"):
            return multi_res
        return _parse_xlsx_protocol(content)
    elif fname_lower.endswith(".doc"):
        if content.startswith(b"PK\x03\x04"):
            return _parse_docx_protocol(content)
        # OLE2 бинарный протокол Росэлторга
        return parse_doc_protocol(content)
    elif fname_lower.endswith(".pdf"):
        return parse_pdf_document(content, filename, purchase_items)
    elif fname_lower.endswith(".zip"):
        files = parse_zip_bundle(content, filename)
        if not files:
            raise HTTPException(status_code=422, detail="Архив .zip пуст или не содержит файлов")
        combined: Dict[str, Any] = {"applications": []}
        for sub_name, sub_content in files:
            try:
                sub_res = parse_protocol_file(sub_name, sub_content, purchase_items)
                if sub_res.get("is_single_application"):
                    app = sub_res["application"]
                    app["documents"] = [{"name": sub_name, "source": "zip"}]
                    combined["applications"].append(app)
                elif sub_res.get("applications"):
                    for k in ("registration_number", "notice_date", "protocol_number", "protocol_date", "commission_members", "commission_order_number", "commission_order_date", "meeting_address", "meeting_time"):
                        if sub_res.get(k) and not combined.get(k):
                            combined[k] = sub_res[k]
                    combined["applications"].extend(sub_res["applications"])
            except Exception:
                continue
        combined["applications"] = recalculate_places(combined["applications"])
        combined["total_applications"] = len(combined["applications"])
        combined["admitted_count"] = sum(1 for a in combined["applications"] if a.get("admitted"))
        combined["rejected_count"] = sum(1 for a in combined["applications"] if not a.get("admitted"))
        return combined
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Неподдерживаемый формат файла: {filename}. Допустимы .docx, .doc, .xlsx, .pdf, .zip.",
        )


def _parse_docx_protocol(content: bytes) -> Dict[str, Any]:
    try:
        import docx
    except ImportError:
        raise HTTPException(status_code=500, detail="Библиотека python-docx не установлена на сервере")

    try:
        doc = docx.Document(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось открыть файл как документ Word (.docx): {e}")

    full_text = "\n".join(p.text for p in doc.paragraphs)

    # 1. Номер извещения
    reg_number = ""
    m_notice = re.search(r"Извещение\s*№?\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
    if m_notice:
        reg_number = m_notice.group(1).strip()
    else:
        m_proto = re.search(r"ПРОТОКОЛ\s*№\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if m_proto:
            p_val = m_proto.group(1).strip()
            # Отсекаем суффикс -1 если это номер протокола вида B0508251030394-1
            reg_number = p_val[:-2] if p_val.endswith("-1") else p_val

    # 2. Дата извещения
    notice_date = ""
    m_ndate = re.search(r"Извещение\s*№?\s*[A-Za-z0-9_-]+\s*от\s*(\d{2}\.\d{2}\.\d{4})", full_text, re.IGNORECASE)
    if m_ndate:
        d_raw = m_ndate.group(1)
        notice_date = f"{d_raw[6:10]}-{d_raw[3:5]}-{d_raw[0:2]}"

    # 3. Номер и дата протокола
    protocol_number = ""
    m_pnum = re.search(r"ПРОТОКОЛ\s*(№\s*[A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
    if m_pnum:
        protocol_number = m_pnum.group(1).replace(" ", "")

    protocol_date = ""
    m_pdate = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})\s*г", full_text)
    if m_pdate:
        protocol_date = _parse_ru_date(m_pdate.group(0)) or ""

    # 4. Срок окончания подачи заявок
    deadline = ""
    m_dead = re.search(r"Срок окончания подачи заявок[^\n\.]+?(\d{1,2}:\d{2}[^\n\.]*)", full_text, re.IGNORECASE)
    if m_dead:
        deadline = _clean_str(m_dead.group(1))

    # 5. Место и время проведения заседания Комиссии
    meeting_address = ""
    meeting_time = "16:30"
    m_meet = re.search(r"Место и время проведения заседания Комиссии:\s*(.+?)(?:\s+в\s+(\d{1,2}:\d{2}))", full_text, re.IGNORECASE)
    if m_meet:
        meeting_address = _clean_str(m_meet.group(1))
        meeting_time = m_meet.group(2)
    else:
        m_meet_simple = re.search(r"Место и время проведения заседания Комиссии:\s*(.+)", full_text, re.IGNORECASE)
        if m_meet_simple:
            meeting_address = _clean_str(m_meet_simple.group(1))

    # 6. Номер и дата приказа о создании комиссии
    commission_order_number = ""
    commission_order_date = ""
    m_ord = re.search(r"приказом\s+[^№]+?№\s*([0-9А-Яа-яA-Za-z/-]+)\s+от\s+([0-9\s«»\"'а-яёА-ЯЁ\.]+)", full_text, re.IGNORECASE)
    if m_ord:
        commission_order_number = m_ord.group(1).strip()
        commission_order_date = _parse_ru_date(m_ord.group(2)) or ""

    # 7. Извлечение членов комиссии из таблиц (Таблица с колонками ФИО / Роль)
    commission_members: List[Dict[str, str]] = []
    for t in doc.tables:
        if len(t.rows) > 1 and len(t.columns) == 2:
            hdr0 = _clean_str(t.rows[0].cells[0].text).lower()
            hdr1 = _clean_str(t.rows[0].cells[1].text).lower()
            if "фио" in hdr0 and "роль" in hdr1:
                for row in t.rows[1:]:
                    fio = _clean_str(row.cells[0].text)
                    role = _clean_str(row.cells[1].text)
                    if fio:
                        commission_members.append({"full_name": fio, "role": role or "Член Комиссии"})
                break

    # 8. Извлечение заявок из таблицы рассмотрения
    applications: List[Dict[str, Any]] = []
    for t in doc.tables:
        if len(t.rows) < 2 or len(t.columns) < 4:
            continue
        hdr_texts = [_clean_str(c.text).lower() for c in t.rows[0].cells]
        has_app_num = any("№" in h or "заявк" in h for h in hdr_texts)
        has_supplier = any("наименование" in h or "организаци" in h or "фамилия" in h for h in hdr_texts)
        has_decision = any("решение" in h or "принятое" in h for h in hdr_texts)

        if has_app_num and has_supplier and has_decision:
            for r_idx, row in enumerate(t.rows[1:], start=1):
                col0 = _clean_str(row.cells[0].text).rstrip(".")
                col1 = _clean_str(row.cells[1].text)
                col2 = _clean_str(row.cells[2].text)
                col3 = _clean_str(row.cells[3].text)

                if not col1 and not col2:
                    continue

                app_num = col0 or str(r_idx)

                # ИНН / КПП
                inn = ""
                kpp = ""
                m_inn = re.search(r"ИНН(?:\s*/\s*КПП)?\s*[:/]?\s*(\d{10,12})", col1)
                if m_inn:
                    inn = m_inn.group(1).strip()
                m_kpp = re.search(r"КПП\s*[:/]?\s*(\d{9})", col1)
                if m_kpp:
                    kpp = m_kpp.group(1).strip()

                # Имя поставщика без хвоста ИНН/КПП
                supplier_name = col1
                if inn:
                    supplier_name = re.split(r"ИНН", supplier_name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                supplier_name = supplier_name.rstrip(" ,;/-")

                # Дата/время подачи
                submitted_at = ""
                m_sub = re.search(r"(\d{2}\.\d{2}\.\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)", col2)
                after_sub = col2
                if m_sub:
                    submitted_at = m_sub.group(1).strip()
                    after_sub = col2[m_sub.end():]

                # Цена
                price_val = 0.0
                m_price = re.search(r"([\d\s\u00a0]+(?:[,\.]\d{2})?)\s*(?:руб|₽|р\.)", after_sub, re.IGNORECASE)
                if not m_price:
                    m_price = re.search(r"([\d\s\u00a0]+(?:[,\.]\d{2})?)\s*(?=\()", after_sub)
                if m_price:
                    raw_p = m_price.group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")
                    try:
                        price_val = float(raw_p)
                    except ValueError:
                        price_val = 0.0

                # НДС
                vat_raw = ""
                m_vat = re.search(r"\((.*?)\)", col2)
                if m_vat:
                    vat_raw = m_vat.group(1).strip()
                elif "без ндс" in col2.lower():
                    vat_raw = "Без НДС"
                vat_label = format_vat_label(vat_raw)

                # Решение комиссии
                c3_lower = col3.lower()
                is_admitted = "признать соответствующей" in c3_lower and "не соответствующей" not in c3_lower
                rejection_reason = ""
                if not is_admitted:
                    # Извлечь причину отклонения
                    m_reas = re.search(r"(?:Не соответствует|не соответствующей[^\.]*?\.)\s*(.*)", col3, re.IGNORECASE | re.DOTALL)
                    if m_reas and m_reas.group(1).strip():
                        rejection_reason = m_reas.group(1).strip()
                    else:
                        rejection_reason = col3

                decision_text = col3 if col3 else ("Признать соответствующей требованиям закупочной документации." if is_admitted else "Не соответствует")

                applications.append({
                    "app_id": app_num,
                    "application_number": app_num,
                    "supplier_name": supplier_name,
                    "supplier_short_name": "",
                    "inn": inn,
                    "kpp": kpp,
                    "ogrn": "",
                    "address": "",
                    "phone": "",
                    "email": "",
                    "submitted_at": submitted_at,
                    "price_with_vat": price_val,
                    "price_without_vat": price_val if "без ндс" in vat_label.lower() else 0.0,
                    "vat_raw": vat_raw,
                    "vat_label": vat_label,
                    "positions": [],
                    "documents": [],
                    "platform_rejected": not is_admitted,
                    "platform_decline_reason": rejection_reason,
                    "admitted": is_admitted,
                    "rejection_reason": rejection_reason,
                    "decision_text": decision_text,
                })
            break

    recalculated = recalculate_places(applications)

    return {
        "registration_number": reg_number,
        "notice_date": notice_date,
        "protocol_number": protocol_number,
        "protocol_date": protocol_date or date.today().isoformat(),
        "submission_deadline": deadline,
        "meeting_address": meeting_address,
        "meeting_time": meeting_time,
        "commission_order_number": commission_order_number,
        "commission_order_date": commission_order_date,
        "commission_members": commission_members,
        "applications": recalculated,
        "total_applications": len(recalculated),
        "admitted_count": sum(1 for a in recalculated if a.get("admitted")),
        "rejected_count": sum(1 for a in recalculated if not a.get("admitted")),
    }


def _parse_xlsx_protocol(content: bytes) -> Dict[str, Any]:
    tkp_res = parse_standardized_tkp_workbook(content)
    if tkp_res:
        return tkp_res

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="Библиотека openpyxl не установлена на сервере")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Не удалось открыть файл как таблицу Excel (.xlsx): {e}")

    ws = wb.active
    if ws is None:
        return {"applications": [], "total_applications": 0, "admitted_count": 0, "rejected_count": 0}

    applications: List[Dict[str, Any]] = []
    header_row_idx = None
    col_map: Dict[str, int] = {}

    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        row_str = " ".join(_clean_str(c).lower() for c in row if c is not None)
        if any("№" in row_str or "заявк" in row_str for _ in [1]) and any("поставщик" in row_str or "участник" in row_str or "наименование" in row_str for _ in [1]):
            header_row_idx = row_idx
            for c_idx, cell in enumerate(row):
                c_text = _clean_str(cell).lower()
                if "№" in c_text or "заявк" in c_text:
                    col_map["num"] = c_idx
                elif "наименование" in c_text or "поставщик" in c_text or "участник" in c_text or "фио" in c_text:
                    col_map["supplier"] = c_idx
                elif "инн" in c_text:
                    col_map["inn"] = c_idx
                elif "кпп" in c_text:
                    col_map["kpp"] = c_idx
                elif "цена" in c_text:
                    col_map["price"] = c_idx
                elif "решение" in c_text or "статус" in c_text:
                    col_map["decision"] = c_idx
            break

    if header_row_idx is not None:
        for r_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True), start=1):
            if not any(row):
                continue
            num_val = _clean_str(row[col_map.get("num", 0)] if col_map.get("num") is not None else r_idx)
            supp_val = _clean_str(row[col_map.get("supplier", 1)] if col_map.get("supplier") is not None else "")
            if not supp_val:
                continue

            inn_val = _clean_str(row[col_map.get("inn", 2)] if col_map.get("inn") is not None else "")
            kpp_val = _clean_str(row[col_map.get("kpp", 3)] if col_map.get("kpp") is not None else "")
            if not inn_val:
                m_inn = re.search(r"\d{10,12}", supp_val)
                if m_inn:
                    inn_val = m_inn.group(0)

            price_raw = row[col_map.get("price", 4)] if col_map.get("price") is not None else 0.0
            try:
                price_val = float(price_raw or 0.0)
            except (ValueError, TypeError):
                price_val = 0.0

            dec_val = _clean_str(row[col_map.get("decision", 5)] if col_map.get("decision") is not None else "")
            is_admitted = "отклон" not in dec_val.lower() and "не соотв" not in dec_val.lower()

            applications.append({
                "app_id": num_val or str(r_idx),
                "application_number": num_val or str(r_idx),
                "supplier_name": supp_val,
                "supplier_short_name": "",
                "inn": inn_val,
                "kpp": kpp_val,
                "ogrn": "",
                "address": "",
                "phone": "",
                "email": "",
                "submitted_at": "",
                "price_with_vat": price_val,
                "price_without_vat": price_val,
                "vat_raw": "Без НДС",
                "vat_label": "Без НДС",
                "positions": [],
                "documents": [],
                "platform_rejected": not is_admitted,
                "platform_decline_reason": dec_val if not is_admitted else "",
                "admitted": is_admitted,
                "rejection_reason": dec_val if not is_admitted else "",
                "decision_text": dec_val or ("Признать соответствующей" if is_admitted else "Отклонить"),
            })

    recalculated = recalculate_places(applications)
    return {
        "registration_number": "",
        "notice_date": "",
        "protocol_number": "",
        "protocol_date": date.today().isoformat(),
        "submission_deadline": "",
        "meeting_address": "",
        "meeting_time": "16:30",
        "commission_order_number": "",
        "commission_order_date": "",
        "commission_members": [],
        "applications": recalculated,
        "total_applications": len(recalculated),
        "admitted_count": sum(1 for a in recalculated if a.get("admitted")),
        "rejected_count": sum(1 for a in recalculated if not a.get("admitted")),
    }
