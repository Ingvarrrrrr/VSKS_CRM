"""
rules_methodology.py — нейтрализует упоминания ВСКС в методических
рекомендациях (methodology_large/small).

Методичка НЕ рендерится docxtpl — она приклеивается к готовому договору
«как есть» через docxcompose.Composer (app/services/documents/
stages_methodology.py::attach_methodology), без прохода через Jinja2.
Поэтому замена здесь — на ОБЫЧНЫЙ текст «Заказчик» (не {{ customer_* }} —
тег так и остался бы тегом в документе, который отправляется контрагенту).

Ревью 2026-10-05: «методички приклеиваются как есть — нейтрально: для
Заказчика / в адрес Заказчика / проверяются Заказчиком; адрес — по адресу
Заказчика, указанному в Договоре». Отдельный файл по ПРАВИЛУ №5.
"""
import re

S = re.DOTALL


def _make_rules():
    rules = []

    rules.append((
        "METH_01_title",
        re.compile(r"ОКАЗАННЫХ УСЛУГ ДЛЯ ВСКС", S),
        "ОКАЗАННЫХ УСЛУГ ДЛЯ ЗАКАЗЧИКА",
    ))

    rules.append((
        "METH_02_predjavlyaut",
        re.compile(r"предъявляют к этим отчетам ВСКС\.", S),
        "предъявляет к этим отчетам Заказчик.",
    ))
    rules.append((
        "METH_03_dogovor_s_vsks",
        re.compile(r"договор оказания услуг с ВСКС,", S),
        "договор оказания услуг с Заказчиком,",
    ))
    rules.append((
        "METH_04_dlya_vsks_dalee",
        re.compile(r"для ВСКС \(далее", S),
        "для Заказчика (далее",
    ))
    rules.append((
        "METH_05_term_definition",
        re.compile(
            r"Заказчик, ВСКС\s*[–-]\s*Всероссийская общественная молодежная "
            r"организация\s*«Всероссийский студенческий корпус спасателей»\.\s*",
            S,
        ),
        "Заказчик – организация, заключившая с Исполнителем Договор оказания услуг. ",
    ))
    rules.append((
        "METH_06_v_adres_vsks",
        re.compile(r"в адрес ВСКС в сроки", S),
        "в адрес Заказчика в сроки",
    ))
    rules.append((
        "METH_07_address_line",
        re.compile(
            r"^Адрес получателя:\s*119454,\s*г\.\s*Москва,\s*пр-т Вернадского,\s*д\.78,\s*стр\.8\.$",
            S,
        ),
        "Адрес получателя: по адресу Заказчика, указанному в Договоре.",
    ))
    rules.append((
        "METH_08_poluchatel",
        re.compile(r"представитель ВСКС\.", S),
        "представитель Заказчика.",
    ))
    rules.append((
        "METH_09_predostavlyautsya",
        re.compile(r"предоставляются в ВСКС на материальном носителе", S),
        "предоставляются Заказчику на материальном носителе",
    ))
    rules.append((
        "METH_10_proveryautsya",
        re.compile(r"проверяются в ВСКС в срок", S),
        "проверяются Заказчиком в срок",
    ))
    rules.append((
        "METH_11_napravlenii",
        re.compile(r"отчетных документов в ВСКС срок проверки", S),
        "отчетных документов Заказчику срок проверки",
    ))
    rules.append((
        "METH_12_utverzhdenie",
        re.compile(r"утверждения ВСКС отчетной документации", S),
        "утверждения Заказчиком отчетной документации",
    ))
    rules.append((
        "METH_13_napravlyaet_akt",
        re.compile(r"направляет в ВСКС актуальный Акт", S),
        "направляет Заказчику актуальный Акт",
    ))
    rules.append((
        "METH_14_vzaimootnosheniya",
        re.compile(r"взаимоотношения между ВСКС и Исполнителем", S),
        "взаимоотношения между Заказчиком и Исполнителем",
    ))
    rules.append((
        "METH_15_ne_podlezhat",
        re.compile(r"не подлежат оплате со стороны ВСКС\.", S),
        "не подлежат оплате со стороны Заказчика.",
    ))
    rules.append((
        "METH_16_signature_block",
        re.compile(r"^ВСКС «_____»$", S),
        "Заказчик «_____»",
    ))

    return rules


RULES = _make_rules()


def apply_methodology_rules(root, counts: dict) -> None:
    """Проходит по абзацам УЖЕ ОТРЕЗАННОЙ методички (после заголовка
    «МЕТОДИЧЕСКИЕ РЕКОМЕНДАЦИИ») и нейтрализует упоминания ВСКС."""
    from backend.templates.build.docxedit import para_text, replace_in_para

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": W}
    for p in root.findall(".//w:p", ns):
        for rule_id, pattern, repl in RULES:
            text = para_text(p)
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            for m in reversed(matches):
                replacement = repl(m) if callable(repl) else m.expand(repl)
                replace_in_para(p, m.start(), m.end(), replacement)
                counts[rule_id] = counts.get(rule_id, 0) + 1
