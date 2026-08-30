"""
rules_order.py — правила замены для order_purchase (Приказ на закупку ВСКС).

Разметка задана владельцем дословно (не собственная эвристика) — см. промпт
сессии. Правила буквальные: конкретное значение образца → одна переменная,
остальной текст образца не переписывается.

Замены выполняются docxedit.replace_in_para() по смещениям внутри ранов
абзаца (как и rules_common.py), НЕ регулярками по склеенному тексту всего
документа — так исключается порча текста, соседствующего с ранами разной
разметки (например курсив/подчёркивание внутри одного предложения).
"""
import re

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W}}}"


def _make_rules():
    """
    Возвращает list[tuple[rule_id, pattern, replacement]] — применяются
    построчно к КАЖДОМУ абзацу (apply_order_rules), как apply_common_rules.
    """
    rules = []

    # ── Шапка (таблица реквизитов Заказчика) ───────────────────────────────
    # «(ВСКС)» — отдельная ячейка/абзац целиком
    rules.append((
        "O01_customer_short_name_cell",
        re.compile(r"^\(ВСКС\)$"),
        "({{ customer_short_name }})",
    ))

    # «Пр-т Вернадского, д. 78 стр. 8 Москва, 119454» — адрес целиком
    rules.append((
        "O02_customer_address",
        re.compile(r"^Пр-т Вернадского, д\. 78 стр\. 8 Москва, 119454$"),
        "{{ customer_address }}",
    ))

    # «Тел.: (495) 568-00-11         e-mail: info@vsks.ru» — заменяем только
    # телефон и email, префикс «Тел.: », разделитель и «e-mail: » остаются
    # дословно (как в образце).
    rules.append((
        "O03_customer_phone_header",
        re.compile(r"\(495\) 568-00-11"),
        "{{ customer_phone }}",
    ))
    rules.append((
        "O04_customer_email_header",
        re.compile(r"info@vsks\.ru"),
        "{{ customer_email }}",
    ))

    # ── Шапка (таблица номер/дата приказа) ──────────────────────────────────
    # «№___» (за underscore-блоком в этой ячейке следует w:tab — не трогаем)
    rules.append((
        "O05_procurement_order_number",
        re.compile(r"№___"),
        "№{{ procurement_order_number }}",
    ))

    # «23 марта 2026 г.» — дата приказа, абзац целиком
    rules.append((
        "O06_today",
        re.compile(r"^23 марта 2026 г\.$"),
        "{{ today }}",
    ))

    # ── Преамбула ────────────────────────────────────────────────────────
    # «Всероссийской общественной молодежной организации «Всероссийский
    # студенческий корпус спасателей» (ВСКС)» → {{ customer_full_name }}
    # целиком (одна переменная на весь оборот, включая «(ВСКС)» — так задано
    # разметкой владельца). Реквизиты «утвержденным приказом Президента ВСКС
    # от «02» апреля 2025 г. №13» (Положение о закупках) намеренно НЕ трогаем —
    # этих данных нет в базе (известный пробел, см. отчёт).
    rules.append((
        "O07_preamble_customer_full_name",
        re.compile(
            r"Всероссийской общественной молодежной организации\s+"
            r"«Всероссийский студенческий корпус спасателей»\s+\(ВСКС\)",
            re.DOTALL,
        ),
        "{{ customer_full_name }}",
    ))

    # ── Пункты приказа ──────────────────────────────────────────────────────
    # п.1: предмет закупки
    rules.append((
        "O08_subject",
        re.compile(r"на поставку роутера и жесткого диска"),
        "{{ subject }}",
    ))

    # п.2: способ закупки
    rules.append((
        "O09_purchase_method_label",
        re.compile(r"запрос цен"),
        "{{ purchase_method_label }}",
    ))

    # п.3: дата и время завершения приёма заявок
    rules.append((
        "O10_submission_deadline_datetime",
        re.compile(r"03\.04\.2026 г\. в 12:00"),
        "{{ submission_deadline_datetime }}",
    ))

    # п.5: место доставки
    rules.append((
        "O11_delivery_location",
        re.compile(r"г\. Москва"),
        "{{ delivery_location }}",
    ))

    # п.6: срок поставки
    rules.append((
        "O12_service_term",
        re.compile(r"7 календарных дней"),
        "{{ service_term }}",
    ))

    # п.8: НМЦД
    rules.append((
        "O13_total_nmck",
        re.compile(r"без НМЦД"),
        "{{ total_nmck }}",
    ))

    # п.9: источник финансирования — всё после «Источник финансирования: »
    # (фиксированный по ширине lookbehind — допустим в re, т.к. префикс
    # константной длины).
    rules.append((
        "O14_subsidy_agreement_text",
        re.compile(r"(?<=Источник финансирования: )Финансирование договора[\s\S]+$"),
        "{{ subsidy_agreement_text }}",
    ))

    # ── Подпись ──────────────────────────────────────────────────────────
    # «Президент ВСКС» (за текстом в этой ячейке следует w:tab — не трогаем)
    rules.append((
        "O15_customer_signatory_position",
        re.compile(r"^Президент ВСКС"),
        "{{ customer_signatory_position }}",
    ))

    # «Козеев Е.В.» после «______________ »
    rules.append((
        "O16_customer_signatory_name_initials",
        re.compile(r"Козеев Е\.В\."),
        "{{ customer_signatory_name_initials }}",
    ))

    return rules


RULES = _make_rules()

# Многоабзацная ячейка шапки: «Всероссийская общественная молодежная
# организация» / «ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ» — это ДВА
# соседних <w:p> внутри одной ячейки таблицы (перенос строки в исходнике —
# не \n внутри абзаца, а отдельный абзац). RULES построчно этого не поймает
# (regex работает в пределах одного абзаца) — отдельная обработка ниже.
_CUSTOMER_FULL_NAME_LINE1 = "Всероссийская общественная молодежная организация"
_CUSTOMER_FULL_NAME_LINE2 = "«ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ»"


def apply_order_rules(p, counts: dict) -> int:
    """
    Применяет RULES к абзацу p (как apply_common_rules в rules_common.py).
    Замены — через replace_in_para (смещения внутри ранов).
    """
    from backend.templates.build.docxedit import para_text, replace_in_para

    total = 0
    for rule_id, pattern, repl in RULES:
        text = para_text(p)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        for m in reversed(matches):
            if callable(repl):
                replacement = repl(m)
            else:
                replacement = m.expand(repl)
            replace_in_para(p, m.start(), m.end(), replacement)
            counts[rule_id] = counts.get(rule_id, 0) + 1
            total += 1
    return total


def apply_order_header_customer_name(root, counts: dict) -> None:
    """
    Шапка: cхлопывает пару абзацев «Всероссийская общественная молодежная
    организация» + «ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ» (два <w:p>
    в одной ячейке таблицы) в один тег {{ customer_full_name }}: первый
    абзац получает тег целиком, второй абзац (тот же родитель — та же
    ячейка) удаляется из документа. Ячейка таблицы не может остаться без
    абзацев — первый остаётся.
    """
    from backend.templates.build.docxedit import para_text, replace_in_para

    ns = {"w": W}
    paragraphs = root.findall(".//w:p", ns)
    for i, p in enumerate(paragraphs):
        if para_text(p).strip() != _CUSTOMER_FULL_NAME_LINE1:
            continue
        if i + 1 >= len(paragraphs):
            continue
        p2 = paragraphs[i + 1]
        if para_text(p2).strip() != _CUSTOMER_FULL_NAME_LINE2:
            continue
        if p.getparent() is None or p2.getparent() is not p.getparent():
            continue

        text = para_text(p)
        replace_in_para(p, 0, len(text), "{{ customer_full_name }}")
        p2.getparent().remove(p2)
        counts["O00_customer_full_name_header_cell"] = (
            counts.get("O00_customer_full_name_header_cell", 0) + 1
        )
        return
