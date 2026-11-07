"""Генератор итогового протокола работы закупочной комиссии ВСКС (.docx).

Строго соответствует образцу «Протокол ВСКС new.docx» и реальным протоколам ЭТП.
ПРАВИЛО №5: модульный файл (< 420 строк).
ПРАВИЛО №6: переиспользование форматирования из app.services.documents.formatting
(_fmt_date, _fmt_money, _rubles_to_words, _fio_to_initials, _extract_city_from_address).
"""
import io
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Cm, Pt, RGBColor

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.documents.formatting import (
    _fmt_date,
    _fmt_money,
    _rubles_to_words,
    _fio_to_initials,
    _extract_city_from_address,
)
from app.services.documents.protocol_docx_helpers import (
    quote_ru_date as _quote_ru_date,
    style_run as _style_run,
    add_styled_p as _add_styled_p,
    style_table as _style_table,
)


def build_vsks_protocol_docx(
    purchase: Purchase,
    subsidy: Optional[Subsidy],
    customer_org: Any,
    customer_ctr: Any,
    results: Dict[str, Any],
) -> bytes:
    """Генерирует итоговый протокол закупки ВСКС в формате .docx."""
    from app.services.documents.protocol_docx_helpers import resolve_or_build_subsidy_protocol_base_doc
    subsidy_id = subsidy.id if subsidy else getattr(purchase, "subsidy_id", None)
    doc = resolve_or_build_subsidy_protocol_base_doc(subsidy_id)

    # Реквизиты Заказчика (единый источник через add_customer_context, ПРАВИЛО №6)
    from app.services.documents.contexts_extra import add_customer_context
    cust_ctx: dict[str, Any] = {}
    if customer_org or customer_ctr:
        add_customer_context(cust_ctx, customer_org, customer_ctr)

    customer_full_name = cust_ctx.get("customer_full_name") or ""
    customer_short_name = cust_ctx.get("customer_short_name") or ""
    customer_address = cust_ctx.get("customer_address") or ""

    if not customer_full_name:
        if customer_ctr:
            customer_full_name = getattr(customer_ctr, "full_name", None) or getattr(customer_ctr, "name", "")
            customer_short_name = getattr(customer_ctr, "name", "")
            customer_address = getattr(customer_ctr, "address", "") or getattr(customer_ctr, "legal_address", "")
        elif customer_org:
            customer_full_name = getattr(customer_org, "name", "")
            customer_short_name = getattr(customer_org, "short_name", "") or getattr(customer_org, "name", "")
            customer_address = getattr(customer_org, "address", "") or getattr(customer_org, "contract_address", "")

    if not customer_full_name:
        customer_full_name = results.get("customer_full_name") or "ВСЕРОССИЙСКАЯ ОБЩЕСТВЕННАЯ МОЛОДЕЖНАЯ ОРГАНИЗАЦИЯ «ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ»"
    if not customer_short_name:
        customer_short_name = results.get("customer_short_name") or "ВОМО «ВСКС»"

    # Город проведения
    city = results.get("city") or cust_ctx.get("customer_city") or _extract_city_from_address(customer_address) or "Москва"

    # Извещение и протокол
    notice_number = (
        results.get("registration_number")
        or results.get("notice_number")
        or getattr(purchase, "procurement_notice_number", None)
        or "________"
    )
    notice_date_raw = results.get("notice_date") or results.get("published_at")
    notice_date_str = _fmt_date(notice_date_raw) if notice_date_raw else _fmt_date(date.today())

    protocol_number = results.get("protocol_number") or f"№{notice_number}-1" if notice_number != "________" else "________"
    protocol_date_val = results.get("protocol_date") or date.today()
    protocol_date_quoted = _quote_ru_date(protocol_date_val)

    # Способ закупки
    purchase_method = (
        results.get("purchase_method_label")
        or ("запрос предложений" if getattr(purchase, "request_type", None) == "request_proposals" else "запрос цен")
    )
    subject = results.get("subject") or purchase.subject or "Поставка товаров / выполнение работ / оказание услуг"

    # НМЦД
    no_nmcd = results.get("no_nmcd") or getattr(purchase, "fabrikant_no_nmcd", False)
    est_price = (
        getattr(purchase, "estimated_price", None)
        or getattr(purchase, "nmck", None)
        or getattr(purchase, "planned_total_price", None)
        or getattr(purchase, "contract_price", None)
    )
    if no_nmcd or not est_price:
        nmcd_text = "не установлена"
    else:
        nmcd_text = f"{_fmt_money(est_price)} руб."

    # Место и время проведения заседания
    meeting_address = results.get("meeting_address") or customer_address or "г. Москва"
    meeting_time = results.get("meeting_time") or "16:30"

    # Срок окончания подачи заявок
    deadline_val = results.get("submission_deadline")
    deadline_time = "12:00"
    deadline_date_quoted = _quote_ru_date(notice_date_raw)
    if deadline_val:
        m_t = re.search(r"(\d{1,2}:\d{2})", str(deadline_val))
        if m_t:
            deadline_time = m_t.group(1)
        deadline_date_quoted = _quote_ru_date(deadline_val)

    # Приказ о комиссии
    commission_order_number = (
        results.get("commission_order_number")
        or (subsidy.commission_order_number if subsidy else "")
        or "86"
    )
    commission_order_date_raw = (
        results.get("commission_order_date")
        or (subsidy.commission_order_date if subsidy else "")
    )
    commission_order_date_text = _quote_ru_date(commission_order_date_raw) if commission_order_date_raw else "25 декабря 2024 г."

    # Члены комиссии (состав)
    raw_members = results.get("commission_members") or (subsidy.commission_members if subsidy else [])
    if isinstance(raw_members, str):
        try:
            import json
            raw_members = json.loads(raw_members)
        except Exception:
            raw_members = []
    commission_members = list(raw_members) if isinstance(raw_members, list) else []
    total_commission_count = len(commission_members) if commission_members else 4

    # Присутствующие члены комиссии для Таблицы 0 (в присутствии:) и блока подписей
    present_members = [
        m for m in commission_members
        if (m.get("present") is not False if isinstance(m, dict) else True)
    ] if commission_members else []

    members_to_show = present_members if present_members else (
        commission_members if commission_members else [
            {"full_name": "Цыганов Игорь Александрович", "role": "Председатель Комиссии"},
            {"full_name": "Иванова Ирина Владиславовна", "role": "Член Комиссии"},
            {"full_name": "Любарец Евгения Дмитриевна", "role": "Член Комиссии"},
        ]
    )

    # Заявки
    applications = list(results.get("applications", []))
    total_apps = len(applications)
    admitted_apps = [a for a in applications if a.get("admitted")]
    rejected_apps = [a for a in applications if not a.get("admitted")]
    admitted_count = len(admitted_apps)
    rejected_count = len(rejected_apps)

    # ── ШАПКА ──
    _add_styled_p(doc, f"ПРОТОКОЛ {protocol_number}", size_pt=11.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_styled_p(doc, "РАБОТЫ КОМИССИИ", size_pt=11.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_styled_p(doc, f"(Извещение № {notice_number} от {notice_date_str})", size_pt=11.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_styled_p(doc, "", space_after=4)

    # Город и дата
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(6)
    p_meta.paragraph_format.line_spacing = 1.0
    r_city = p_meta.add_run(f"г. {city}")
    _style_run(r_city, bold=True)
    # Табуляция для выравнивания даты по правому краю
    r_tab = p_meta.add_run("\t\t\t\t\t\t\t\t")
    r_date = p_meta.add_run(protocol_date_quoted)
    _style_run(r_date, bold=True)

    _add_styled_p(doc, "", space_after=4)

    # Реквизиты закупки
    def _add_prop(label: str, val: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        r_lbl = p.add_run(f"{label}: ")
        _style_run(r_lbl, bold=True)
        r_val = p.add_run(val)
        _style_run(r_val, bold=False)

    _add_prop("Заказчик", customer_full_name)
    _add_prop("Организатор закупки", customer_full_name)
    _add_prop("Способ закупки", purchase_method)
    _add_prop("Предмет закупки", subject)
    _add_prop("Начальная (максимальная) цена договора", nmcd_text)
    _add_prop("Место и время проведения заседания Комиссии", f"{meeting_address} в {meeting_time} (время московское)")

    _add_styled_p(doc, "", space_after=4)

    # ── 1. ОБЩАЯ ИНФОРМАЦИЯ ──
    _add_styled_p(doc, "1. Общая информация", bold=True, space_after=4)
    etp_url = "https://business.roseltorg.ru/" if (results.get("platform") == "roseltorg_rb" or str(notice_number).startswith("B")) else "https://www.fabrikant.ru/"
    _add_styled_p(
        doc,
        f"1.1. Извещение о проведении закупки № {notice_number} было размещено {notice_date_str} г., на сайте "
        f"электронной торговой площадки (далее – ЭТП) в информационно-коммуникационной сети интернет по адресу: {etp_url}",
        space_after=3,
    )
    _add_styled_p(
        doc,
        f"1.2. Срок окончания подачи заявок на участие в закупке {deadline_time} (время московское) {deadline_date_quoted}.",
        space_after=3,
    )
    _add_styled_p(
        doc,
        f"1.3. Рассмотрение заявок проводилось комиссией по проведению закупки (далее – Комиссия). "
        f"Состав Комиссии утвержден приказом {customer_short_name} №{commission_order_number} от {commission_order_date_text} "
        f"в составе {total_commission_count}-х человек.",
        space_after=3,
    )
    _add_styled_p(
        doc,
        f"1.4. Заседание проводится очно (по видеоконференцсвязи), в присутствии:",
        space_after=4,
    )

    # Таблица 0: Члены комиссии
    t0 = doc.add_table(rows=1, cols=2)
    _style_table(t0, [Cm(9.0), Cm(8.0)])
    hdr0 = t0.rows[0].cells
    hdr0[0].paragraphs[0].text = "ФИО"
    _style_run(hdr0[0].paragraphs[0].runs[0], bold=True)
    hdr0[1].paragraphs[0].text = "Роль в Комиссии / Должность"
    _style_run(hdr0[1].paragraphs[0].runs[0], bold=True)

    for m in members_to_show:
        row = t0.add_row().cells
        row[0].paragraphs[0].text = m.get("full_name") or ""
        _style_run(row[0].paragraphs[0].runs[0] if row[0].paragraphs[0].runs else row[0].paragraphs[0].add_run(""))
        role = (m.get("role") or "Член Комиссии").strip()
        pos = (m.get("position") or "").strip()
        if pos and pos.lower() != role.lower():
            role_text = f"{role} ({pos})"
        else:
            role_text = role
        row[1].paragraphs[0].text = role_text
        _style_run(row[1].paragraphs[0].runs[0] if row[1].paragraphs[0].runs else row[1].paragraphs[0].add_run(""))

    _add_styled_p(doc, "", space_after=3)
    _add_styled_p(doc, "1.5. Кворум имеется, Комиссия правомочна.", space_after=6)

    # ── 2. РАССМОТРЕНИЕ ЗАЯВОК ──
    _add_styled_p(doc, "2. Рассмотрение заявок", bold=True, space_after=4)
    _add_styled_p(doc, "2.1. Комиссия рассматривает поступившие заявки участников закупки на соответствие требованиям закупочной документации.", space_after=3)
    _add_styled_p(doc, f"2.2. Количество поданных на ЭТП заявок на участие в закупке: {total_apps}", space_after=3)
    _add_styled_p(doc, "2.3. Комиссия рассмотрела поступившие заявки и приняла следующие решения:", space_after=4)

    # Таблица 1: Заявки
    t1 = doc.add_table(rows=1, cols=4)
    _style_table(t1, [Cm(2.0), Cm(6.5), Cm(4.5), Cm(4.0)])
    hdr1 = t1.rows[0].cells
    hdr1[0].paragraphs[0].text = "№ заявки"
    hdr1[1].paragraphs[0].text = "Наименование организации (для юридических лиц); Фамилия Имя Отчество (для физических лиц);"
    hdr1[2].paragraphs[0].text = "Дата и время подачи заявки, цена предложения"
    hdr1[3].paragraphs[0].text = "Принятое решение"
    for c in hdr1:
        if c.paragraphs[0].runs:
            _style_run(c.paragraphs[0].runs[0], bold=True, size_pt=9.5)

    if not applications:
        r_empty = t1.add_row().cells
        for c in r_empty:
            c.paragraphs[0].text = "—"
            _style_run(c.paragraphs[0].runs[0], size_pt=9.5)
    else:
        for a in applications:
            r = t1.add_row().cells
            r[0].paragraphs[0].text = str(a.get("application_number") or "")

            supp_text = a.get("supplier_name") or ""
            inn_kpp = []
            if a.get("inn"):
                inn_kpp.append(f"ИНН {a['inn']}")
            if a.get("kpp"):
                inn_kpp.append(f"КПП {a['kpp']}")
            if inn_kpp:
                supp_text += f"\n{' / '.join(inn_kpp)}"
            r[1].paragraphs[0].text = supp_text

            p_val = a.get("price_with_vat") or a.get("price_without_vat") or 0.0
            vat_lbl = a.get("vat_label") or "Без НДС"
            sub_dt = a.get("submitted_at") or ""
            dt_price_text = f"{sub_dt}\n{_fmt_money(p_val)} руб. ({vat_lbl})" if sub_dt else f"{_fmt_money(p_val)} руб. ({vat_lbl})"
            r[2].paragraphs[0].text = dt_price_text

            r[3].paragraphs[0].text = a.get("decision_text") or ("Признать соответствующей требованиям закупочной документации." if a.get("admitted") else f"Не соответствует. {a.get('rejection_reason', '')}".strip())

            for c in r:
                if c.paragraphs[0].runs:
                    _style_run(c.paragraphs[0].runs[0], size_pt=9.5)

    _add_styled_p(doc, "", space_after=3)
    _add_styled_p(doc, f"2.4. Количество отклоненных заявок участников: {rejected_count}", space_after=3)
    _add_styled_p(doc, f"2.5. Количество заявок участников, признанных соответствующими требованиям закупочной документации: {admitted_count}", space_after=3)
    if admitted_count == 1:
        _add_styled_p(doc, "2.6. Закупка может быть признана несостоявшейся по причине наличия только одной заявки.", space_after=6)
    elif admitted_count == 0:
        _add_styled_p(doc, "2.6. Закупка признана несостоявшейся по причине отсутствия допущенных заявок.", space_after=6)

    # ── 3. ОЦЕНКА ЗАЯВОК ──
    _add_styled_p(doc, "3. Оценка заявок", bold=True, space_after=4)
    _add_styled_p(doc, "3.1. Порядок оценки и сопоставления заявок участников закупки установлен в закупочной документации.", space_after=3)
    _add_styled_p(doc, "3.2. Лучшим предложением по цене товара (работы, услуги) является предложение с наименьшей ценой исполнения договора.", space_after=3)
    _add_styled_p(doc, "3.3. Предложения поступившие от участников закупки:", space_after=4)

    # Таблица 2: Оценка (только допущенные заявки)
    t2 = doc.add_table(rows=1, cols=4)
    _style_table(t2, [Cm(2.0), Cm(7.0), Cm(4.5), Cm(3.5)])
    hdr2 = t2.rows[0].cells
    hdr2[0].paragraphs[0].text = "№ заявки"
    hdr2[1].paragraphs[0].text = "Наименование организации (для юридических лиц); Фамилия Имя Отчество (для физических лиц);"
    hdr2[2].paragraphs[0].text = "Цена исполнения договора"
    hdr2[3].paragraphs[0].text = "Присвоенное место"
    for c in hdr2:
        if c.paragraphs[0].runs:
            _style_run(c.paragraphs[0].runs[0], bold=True, size_pt=9.5)

    if not admitted_apps:
        r_empty2 = t2.add_row().cells
        for c in r_empty2:
            c.paragraphs[0].text = "—"
            _style_run(c.paragraphs[0].runs[0], size_pt=9.5)
    else:
        for idx, a in enumerate(admitted_apps, start=1):
            r = t2.add_row().cells
            r[0].paragraphs[0].text = str(a.get("application_number") or idx)

            supp_text = a.get("supplier_name") or ""
            if a.get("inn"):
                supp_text += f"\nИНН {a['inn']}"
            r[1].paragraphs[0].text = supp_text

            p_val = a.get("price_with_vat") or a.get("price_without_vat") or 0.0
            vat_lbl = a.get("vat_label") or "Без НДС"
            sub_dt = a.get("submitted_at") or ""
            dt_price_text = f"{sub_dt}\n{_fmt_money(p_val)} руб. ({vat_lbl})" if sub_dt else f"{_fmt_money(p_val)} руб. ({vat_lbl})"
            r[2].paragraphs[0].text = dt_price_text

            place_val = a.get("place") or idx
            r[3].paragraphs[0].text = f"{place_val} место"

            for c in r:
                if c.paragraphs[0].runs:
                    _style_run(c.paragraphs[0].runs[0], size_pt=9.5)

    _add_styled_p(doc, "", space_after=3)

    # ── 4. СОПОСТАВЛЕНИЕ И РАНЖИРОВАНИЕ ──
    _add_styled_p(doc, "4. Сопоставление и ранжирование по результатам оценки заявок", bold=True, space_after=4)
    _add_styled_p(doc, "4.1. Порядок оценки и сопоставления заявок участников закупки установлен в закупочной документации.", space_after=3)
    _add_styled_p(doc, "4.2. Комиссия не проводила сопоставления и ранжирования предложений в связи с отсутствием неценовых критериев.", space_after=6)

    # ── 5. РЕШЕНИЯ, ПРИНЯТЫЕ КОМИССИЕЙ ──
    _add_styled_p(doc, "5. Решения, принятые Комиссией", bold=True, space_after=4)

    winner_app = next((a for a in admitted_apps if a.get("place") == 1), (admitted_apps[0] if admitted_apps else None))
    winner_name = winner_app.get("supplier_name") if winner_app else "________________________"
    winner_price = (winner_app.get("price_with_vat") or winner_app.get("price_without_vat") or 0.0) if winner_app else 0.0
    winner_vat = winner_app.get("vat_label") if winner_app else "Без НДС"
    price_words = _rubles_to_words(winner_price)
    if price_words:
        price_words = price_words[:1].upper() + price_words[1:]
    winner_price_text = f"{_fmt_money(winner_price)} руб. ({price_words}) ({winner_vat})" if winner_price else "________________________"

    if admitted_count == 1:
        _add_styled_p(
            doc,
            "5.1. В соответствии с пп.1 п. 10.6.1 и абз. 2 п. 10.6.2 Положения о закупке товаров, работ, услуг Заказчика "
            "признать закупку несостоявшейся, по причине наличия только одной заявки, и заключить договор с единственным "
            "участником закупки, заявка которого признана соответствующей требованиям закупочной документации.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            f"5.2. Признать победителем закупки {winner_name} по цене {winner_price_text}.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            "5.3. Настоящий протокол подлежит хранению в течение трех лет от даты подведения итогов запроса.",
            space_after=6,
        )
    elif admitted_count >= 2:
        _add_styled_p(
            doc,
            f"5.1. Признать победителем закупки {winner_name} по цене {winner_price_text}.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            "5.2. Заказчик вправе заключить договор с победителем закупки.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            "5.3. Настоящий протокол подлежит хранению в течение трех лет от даты подведения итогов запроса.",
            space_after=6,
        )
    else:
        _add_styled_p(
            doc,
            "5.1. Признать закупку несостоявшейся по причине отсутствия заявок, соответствующих требованиям закупочной документации.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            "5.2. Заказчик вправе провести новую закупку, заключить договор с единственным поставщиком, отказаться от проведения закупки.",
            space_after=3,
        )
        _add_styled_p(
            doc,
            "5.3. Настоящий протокол подлежит хранению в течение трех лет от даты подведения итогов запроса.",
            space_after=6,
        )

    # ── 6. ПОДПИСИ ──
    _add_styled_p(doc, "6. Подписи", bold=True, space_after=6)

    chairman = next((m for m in members_to_show if "председатель" in (m.get("role") or "").lower()), members_to_show[0] if members_to_show else None)
    ordinary_members = [m for m in members_to_show if m != chairman]

    if chairman:
        ch_name = _fio_to_initials(chairman.get("full_name") or "")
        _add_styled_p(doc, f"Председатель Комиссии:\t\t\t\t__________________ {ch_name}", space_after=4)

    if ordinary_members:
        p_first = doc.add_paragraph()
        p_first.paragraph_format.space_after = Pt(4)
        m0_name = _fio_to_initials(ordinary_members[0].get("full_name") or "")
        p_first.add_run(f"Члены Комиссии:\t\t\t\t\t__________________ {m0_name}")
        _style_run(p_first.runs[0])

        for m in ordinary_members[1:]:
            p_sub = doc.add_paragraph()
            p_sub.paragraph_format.space_after = Pt(4)
            m_name = _fio_to_initials(m.get("full_name") or "")
            p_sub.add_run(f"\t\t\t\t\t\t__________________ {m_name}")
            _style_run(p_sub.runs[0])

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
