"""
Генератор шаблона «Договор оказания услуг» (contract_services.docx).

Запуск (один раз):
    py backend/templates/make_contract_services.py

Создаёт backend/templates/contract_services.docx — шаблон docxtpl с Jinja2
placeholder'ами для всех переменных из documents.py (Phase 23).
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

TEMPLATES_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(TEMPLATES_DIR, "contract_services.docx")


def page_margins(doc):
    for sec in doc.sections:
        sec.top_margin = Cm(2)
        sec.bottom_margin = Cm(2)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(1.5)


def set_cell_bg(cell, hex_color: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def para(doc, text="", bold=False, size=12, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         space_before=0, space_after=6, italic=False):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = Pt(13.8)  # ~1.15 × 12pt
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        r.font.name = "Times New Roman"
        r.font.size = Pt(size)
    return p


def add_run(paragraph, text, bold=False, size=12, italic=False):
    r = paragraph.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.name = "Times New Roman"
    r.font.size = Pt(size)
    return r


def section_title(doc, text, num=""):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    full = f"{num}. {text}" if num else text
    r = p.add_run(full)
    r.bold = True
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    return p


def clause(doc, num, text, space_before=2):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = Pt(13.8)
    p.paragraph_format.first_line_indent = Cm(1)
    r = p.add_run(f"{num}. ")
    r.bold = True
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    r2 = p.add_run(text)
    r2.font.name = "Times New Roman"
    r2.font.size = Pt(12)
    return p


# ─────────────────────────────────────────────────────────────────────────────

doc = Document()
page_margins(doc)

# Установить шрифт по умолчанию
style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(12)

# ── ЗАГОЛОВОК ────────────────────────────────────────────────────────────────
p_title = doc.add_paragraph()
p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_title.paragraph_format.space_after = Pt(4)
add_run(p_title, "ДОГОВОР № {{contract_number}}", bold=True, size=14)

p_sub = doc.add_paragraph()
p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_sub.paragraph_format.space_after = Pt(10)
add_run(p_sub, "на оказание услуг", bold=True, size=12)

# Город и дата — строка с табуляцией
p_city = doc.add_paragraph()
p_city.alignment = WD_ALIGN_PARAGRAPH.LEFT
p_city.paragraph_format.space_after = Pt(10)
add_run(p_city, "г. {{contract_city}}", size=12)
add_run(p_city, "                                    «{{contract_date_day}}» {{contract_date_month}} {{contract_date_year}} г.", size=12)

# ── ПРЕАМБУЛА ────────────────────────────────────────────────────────────────
p_pre = doc.add_paragraph()
p_pre.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_pre.paragraph_format.space_after = Pt(6)
p_pre.paragraph_format.line_spacing = Pt(13.8)
add_run(p_pre, "{{customer_full_name}} ({{customer_short_name}}), именуемое в дальнейшем «Заказчик», "
               "в лице {{customer_signatory_position}} {{customer_signatory_name_genitive}}, "
               "действующего на основании {{customer_signatory_basis}}, с одной стороны, и")

# Условный блок — ИП или ООО
p_cond = doc.add_paragraph()
p_cond.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_cond.paragraph_format.space_after = Pt(6)
p_cond.paragraph_format.line_spacing = Pt(13.8)
add_run(p_cond,
        "{%- if contractor_org_type == 'ИП' %}"
        "Индивидуальный предприниматель {{contractor_signatory_name}} "
        "(ИП {{contractor_short_name}}), ИНН {{contractor_inn}}, "
        "ОГРНИП {{contractor_ogrnip}}"
        "{%- else %}"
        "{{contractor_full_name}} ({{contractor_short_name}}), "
        "в лице {{contractor_signatory_position}} {{contractor_signatory_name_genitive}}, "
        "действующего на основании {{contractor_signatory_basis}}"
        "{%- endif %}, "
        "именуемое в дальнейшем «Исполнитель», с другой стороны, "
        "совместно именуемые «Стороны», заключили настоящий Договор о нижеследующем:")

# ── 1. ПРЕДМЕТ ДОГОВОРА ──────────────────────────────────────────────────────
section_title(doc, "ПРЕДМЕТ ДОГОВОРА", "1")

clause(doc, "1.1",
       "Исполнитель обязуется оказать услуги по {{service_subject}} (далее — Услуги), "
       "а Заказчик — принять и оплатить их. Содержание, объём и требования к Услугам "
       "определяются Техническим заданием (Приложение №1), являющимся неотъемлемой "
       "частью настоящего Договора.")

clause(doc, "1.2",
       "Срок оказания Услуг: {{service_term}}.")

clause(doc, "1.3",
       "Договор заключён в рамках реализации {{subsidy_agreement_text}}.")

p_13 = doc.add_paragraph()
p_13.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_13.paragraph_format.first_line_indent = Cm(1)
p_13.paragraph_format.space_after = Pt(3)
p_13.paragraph_format.line_spacing = Pt(13.8)
add_run(p_13, "1.4. ", bold=True)
add_run(p_13, "Услуги оказываются Исполнителем ")
add_run(p_13, "{% if third_party_involved %}с привлечением третьих лиц{% else %}своими силами, без привлечения третьих лиц{% endif %}.")

# ── 2. ПРАВА И ОБЯЗАННОСТИ СТОРОН ───────────────────────────────────────────
section_title(doc, "ПРАВА И ОБЯЗАННОСТИ СТОРОН", "2")

clause(doc, "2.1",
       "Исполнитель обязан: оказать Услуги надлежащего качества в установленные сроки; "
       "соблюдать требования действующего законодательства РФ; предоставлять Заказчику "
       "по его требованию информацию о ходе оказания Услуг.")

clause(doc, "2.2",
       "Исполнитель вправе запрашивать у Заказчика документы и сведения, необходимые "
       "для надлежащего оказания Услуг.")

clause(doc, "2.3",
       "Заказчик обязан: своевременно передавать Исполнителю материалы и информацию, "
       "необходимые для оказания Услуг; принять результаты оказанных Услуг и оплатить "
       "их в соответствии с разделом 4 настоящего Договора.")

clause(doc, "2.4",
       "Заказчик вправе осуществлять контроль за ходом и качеством оказания Услуг, "
       "не вмешиваясь в оперативно-хозяйственную деятельность Исполнителя.")

# ── 3. ПОРЯДОК ПРИЁМКИ УСЛУГ ─────────────────────────────────────────────────
section_title(doc, "ПОРЯДОК ПРИЁМКИ УСЛУГ", "3")

clause(doc, "3.1",
       "По окончании оказания Услуг Исполнитель представляет Заказчику Акт сдачи-приёмки "
       "оказанных услуг (далее — Акт).")

clause(doc, "3.2",
       "Заказчик рассматривает Акт в течение 5 (пяти) рабочих дней с момента его получения. "
       "В случае обнаружения недостатков Заказчик направляет Исполнителю мотивированный "
       "отказ с перечнем замечаний.")

clause(doc, "3.3",
       "Исполнитель устраняет выявленные недостатки в согласованные Сторонами сроки "
       "и представляет Акт повторно.")

clause(doc, "3.4",
       "Датой приёмки Услуг считается дата подписания Акта уполномоченными представителями "
       "обеих Сторон.")

# ── 4. ЦЕНА ДОГОВОРА И ПОРЯДОК РАСЧЁТОВ ─────────────────────────────────────
section_title(doc, "ЦЕНА ДОГОВОРА И ПОРЯДОК РАСЧЁТОВ", "4")

p_41 = doc.add_paragraph()
p_41.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_41.paragraph_format.first_line_indent = Cm(1)
p_41.paragraph_format.space_after = Pt(3)
p_41.paragraph_format.line_spacing = Pt(13.8)
add_run(p_41, "4.1. ", bold=True)
add_run(p_41, "Цена Договора составляет {{contract_price_num}} ({{contract_price_words}}) рублей. "
              "{% if vat_applicable %}"
              "В том числе НДС {{vat_rate}}%: {{vat_amount_num}} ({{vat_amount_words}}) рублей."
              "{% else %}"
              "НДС не облагается на основании {{vat_exemption_article}}."
              "{% endif %}")

clause(doc, "4.2",
       "Оплата производится в безналичной форме путём перечисления денежных средств "
       "на расчётный счёт Исполнителя, указанный в разделе 5 настоящего Договора, "
       "в течение 30 (тридцати) календарных дней с даты подписания Акта.")

clause(doc, "4.3",
       "Цена Договора является фиксированной и изменению не подлежит, за исключением "
       "случаев, предусмотренных действующим законодательством Российской Федерации.")

# ── 5. ОТВЕТСТВЕННОСТЬ СТОРОН ────────────────────────────────────────────────
section_title(doc, "ОТВЕТСТВЕННОСТЬ СТОРОН", "5")

clause(doc, "5.1",
       "За нарушение сроков оказания Услуг Исполнитель уплачивает Заказчику неустойку "
       "в размере 0,1% от цены Договора за каждый день просрочки.")

clause(doc, "5.2",
       "За нарушение сроков оплаты Заказчик уплачивает Исполнителю пени "
       "в размере 1/300 ставки рефинансирования Банка России за каждый день просрочки.")

clause(doc, "5.3",
       "Стороны освобождаются от ответственности за частичное или полное неисполнение "
       "обязательств, если оно явилось следствием обстоятельств непреодолимой силы "
       "(форс-мажор), возникших после заключения настоящего Договора.")

# ── 6. СРОК ДЕЙСТВИЯ И ПОРЯДОК РАСТОРЖЕНИЯ ──────────────────────────────────
section_title(doc, "СРОК ДЕЙСТВИЯ И ПОРЯДОК РАСТОРЖЕНИЯ ДОГОВОРА", "6")

clause(doc, "6.1",
       "Договор вступает в силу с момента подписания Сторонами и действует до полного "
       "исполнения Сторонами принятых на себя обязательств.")

clause(doc, "6.2",
       "Договор может быть расторгнут по соглашению Сторон, а также в одностороннем "
       "порядке по основаниям, предусмотренным действующим законодательством РФ.")

# ── 7. РАЗРЕШЕНИЕ СПОРОВ ─────────────────────────────────────────────────────
section_title(doc, "РАЗРЕШЕНИЕ СПОРОВ", "7")

clause(doc, "7.1",
       "Все споры и разногласия, возникающие в связи с исполнением настоящего Договора, "
       "разрешаются путём переговоров. При недостижении согласия — в Арбитражном суде "
       "г. Москвы в соответствии с действующим законодательством РФ.")

# ── 8. ПРОЧИЕ УСЛОВИЯ ────────────────────────────────────────────────────────
section_title(doc, "ПРОЧИЕ УСЛОВИЯ", "8")

clause(doc, "8.1",
       "Договор составлен в двух экземплярах, имеющих равную юридическую силу, "
       "по одному для каждой из Сторон.")

clause(doc, "8.2",
       "Любые изменения и дополнения к Договору действительны только в случае их "
       "составления в письменной форме и подписания уполномоченными представителями "
       "обеих Сторон.")

clause(doc, "8.3",
       "Приложение №1 (Техническое задание) является неотъемлемой частью Договора.")

# ── 9. АДРЕСА И РЕКВИЗИТЫ СТОРОН ────────────────────────────────────────────
section_title(doc, "АДРЕСА И РЕКВИЗИТЫ СТОРОН", "9")

# Двухколоночная таблица реквизитов
tbl = doc.add_table(rows=1, cols=2)
tbl.style = "Table Grid"

# Настройка ширины колонок
from docx.oxml import OxmlElement as _OE
from docx.oxml.ns import qn as _qn

def set_col_width(cell, cm):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcW = _OE("w:tcW")
    tcW.set(_qn("w:w"), str(int(cm * 567)))
    tcW.set(_qn("w:type"), "dxa")
    tcPr.append(tcW)

LEFT = tbl.rows[0].cells[0]
RIGHT = tbl.rows[0].cells[1]
set_col_width(LEFT, 8.5)
set_col_width(RIGHT, 8.5)


def req_block(cell, lines):
    """Добавляет строки реквизитов в ячейку таблицы."""
    # Очищаем дефолтный параграф
    for i, line in enumerate(lines):
        if i == 0:
            p = cell.paragraphs[0]
        else:
            p = cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(0)
        r = p.add_run(line)
        r.font.name = "Times New Roman"
        r.font.size = Pt(10)
        if i == 0:
            r.bold = True


# ЗАКАЗЧИК
req_block(LEFT, [
    "ЗАКАЗЧИК:",
    "{{customer_full_name}}",
    "Адрес: {{customer_address}}",
    "Почтовый адрес: {{customer_postal_address}}",
    "ИНН: {{customer_inn}} / КПП: {{customer_kpp}}",
    "ОГРН: {{customer_ogrn}}",
    "Банк: {{customer_bank_name}}",
    "БИК: {{customer_bik}}",
    "р/с: {{customer_settlement_account}}",
    "к/с: {{customer_correspondent_account}}",
    "Тел.: {{customer_phone}}",
    "E-mail: {{customer_email}}",
    "",
    "{{customer_signatory_position}}",
    "________________ / {{customer_signatory_initials}}",
    "М.П.",
])

# ИСПОЛНИТЕЛЬ
req_block(RIGHT, [
    "ИСПОЛНИТЕЛЬ:",
    "{%- if contractor_org_type == 'ИП' %}",
    "ИП {{contractor_short_name}}",
    "ИНН: {{contractor_inn}}",
    "ОГРНИП: {{contractor_ogrnip}}",
    "{%- else %}",
    "{{contractor_full_name}}",
    "ИНН: {{contractor_inn}} / КПП: {{contractor_kpp}}",
    "ОГРН: {{contractor_ogrn}}",
    "{%- endif %}",
    "Адрес: {{contractor_address}}",
    "Банк: {{contractor_bank_name}}",
    "БИК: {{contractor_bik}}",
    "р/с: {{contractor_settlement_account}}",
    "к/с: {{contractor_correspondent_account}}",
    "Тел.: {{contractor_phone}}",
    "E-mail: {{contractor_email}}",
    "",
    "{{contractor_signatory_position}}",
    "________________ / {{contractor_signatory_initials}}",
    "М.П.",
])

# Приложение
doc.add_paragraph()
p_app = para(doc, "Приложение №1: Техническое задание (на __ л.).", size=12, space_before=6)

# ── СОХРАНЕНИЕ ───────────────────────────────────────────────────────────────
doc.save(OUTPUT)
print(f"OK: {OUTPUT}")
