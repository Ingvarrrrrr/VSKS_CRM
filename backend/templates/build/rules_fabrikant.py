"""
rules_fabrikant.py — правила замены для 3 документов пакета Фабрикант,
восстановленных 1:1 из реальных заполненных образцов пользователя:

  - fabrikant_application_form  ← "Доработки/Настраиваем ФАБРИКАНТ/Прил2 Форма Заявки.docx"
  - fabrikant_documentation     ← "Доработки/Настраиваем ФАБРИКАНТ/Прил1 Документация (2).docx"
  - fabrikant_contract_project  ← "Доработки/Настраиваем ФАБРИКАНТ/ПРОЕКТ Договор поставка 2026.docx"

В отличие от rules_common.py (8 шаблонов договоров, собранных из "пустых"
типовых бланков с подчёркиваниями), здесь источники — ПОЛНОСТЬЮ ЗАПОЛНЕННЫЕ
реальные документы (Херсонское РО ВСКС, поставка автомобиля). Задача —
заменить ТОЛЬКО конкретные фактические значения (наименование заказчика,
адрес, суммы, даты, номера) на переменные Jinja, сохранив весь остальной
текст, форматирование, таблицы, нумерацию — характер побуквенной сборки
идентичен build.py, но правила и код полностью отдельные и не должны
затрагивать rules_common.py / build.py / 8 договорных шаблонов.

Каждое правило: (rule_id, compiled_re, replacement_str_or_callable) —
применяется той же логикой, что apply_common_rules в rules_common.py.
"""
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent.parent
_TEMPLATES_DIR = _HERE.parent

sys.path.insert(0, str(_REPO_ROOT))

from backend.templates.build import docxedit  # noqa: E402

W = docxedit.W
NS = {"w": W}

S = re.DOTALL
IC = re.IGNORECASE | re.DOTALL


SOURCES: dict[str, str] = {
    "fabrikant_application_form": (
        "Доработки/Настраиваем ФАБРИКАНТ/Прил2 Форма Заявки.docx"
    ),
    "fabrikant_documentation": (
        "Доработки/Настраиваем ФАБРИКАНТ/Прил1 Документация (2).docx"
    ),
    "fabrikant_contract_project": (
        "Доработки/Настраиваем ФАБРИКАНТ/ПРОЕКТ Договор поставка 2026.docx"
    ),
}


# ─────────────────────────────────────────────────────────────────────────
# Общий рантайм применения правил (аналог apply_common_rules)
# ─────────────────────────────────────────────────────────────────────────

def apply_fabrikant_rules(p, rules: list, counts: dict) -> int:
    """
    Применяет rules (list[(rule_id, pattern, repl)]) к абзацу p.
    Пополняет counts[rule_id]. Возвращает суммарное число замен.
    """
    from backend.templates.build.docxedit import para_text, replace_in_para

    total = 0
    for rule_id, pattern, repl in rules:
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
            total += 1
            counts[rule_id] = counts.get(rule_id, 0) + 1
    return total


# ─────────────────────────────────────────────────────────────────────────
# fabrikant_application_form — "ЗАЯВКА НА УЧАСТИЕ В ЗАКУПКЕ"
# ─────────────────────────────────────────────────────────────────────────

def _rules_application_form() -> list:
    rules = []

    rules.append((
        "AF01_notice_number",
        re.compile(r"№ извещения:\s*_+", S),
        "№ извещения: {{ notice_number }}",
    ))
    rules.append((
        "AF02_subject",
        re.compile(r"Предмет закупки:\s*_+", S),
        "Предмет закупки: {{ subject }}",
    ))

    return rules


def _apply_af_price_table(root, counts: dict) -> None:
    """
    Таблица «Расчёт предложенной цены» (2-я таблица документа):
    header | 1..7 (номера колонок) | статичные строки '1.','2.','3.','...' |
    'Итого, руб.'.
    Строки данных разворачиваются в {%tr for item in items %} цикл —
    заполняем номер/наименование/ед.изм./кол-во из технического задания
    закупки, цену/сумму/примечание оставляем пустыми (заполняет участник).
    """
    tables = root.findall(".//w:tbl", NS)
    if len(tables) < 2:
        return  # не тот документ — пропускаем

    table = tables[1]
    rows = table.findall("w:tr", NS)
    if len(rows) < 3:
        return

    data_row = rows[2]
    cells = data_row.findall("w:tc", NS)
    if len(cells) != 7:
        return

    from backend.templates.build.rules_common import _set_cell_text, _make_tag_row

    for_row = _make_tag_row(data_row, "{%tr for item in items %}")
    table.insert(list(table).index(data_row), for_row)

    _set_cell_text(cells[0], "{{ item.num }}.")
    _set_cell_text(cells[1], "{{ item.name }}")
    _set_cell_text(cells[2], "{{ item.unit }}")
    _set_cell_text(cells[3], "{{ item.quantity }}")
    _set_cell_text(cells[4], "")
    _set_cell_text(cells[5], "")
    _set_cell_text(cells[6], "")

    endfor_row = _make_tag_row(data_row, "{%tr endfor %}")
    table.insert(list(table).index(data_row) + 1, endfor_row)

    counts["AFT_price_table_row"] = 1

    # Убираем оставшиеся статичные строки-заглушки ('2.','3.','...'),
    # НЕ трогая последнюю строку «Итого, руб.».
    rows_after = table.findall("w:tr", NS)
    keep = {rows_after[0], rows_after[1], for_row, data_row, endfor_row, rows_after[-1]}
    to_remove = [r for r in rows_after if r not in keep]
    for r in to_remove:
        table.remove(r)
    counts["AFT_price_table_removed"] = len(to_remove)


# ─────────────────────────────────────────────────────────────────────────
# fabrikant_documentation — "ДОКУМЕНТАЦИЯ ЗАПРОСА ЦЕН"
# ─────────────────────────────────────────────────────────────────────────

def _rules_documentation() -> list:
    rules = []

    # Полное наименование заказчика — встречается в ALL CAPS (титул, п.3, п.4)
    # и в обычном регистре (информационная карта, строка 1) — IGNORECASE
    # покрывает оба варианта одним правилом.
    rules.append((
        "D01_customer_full_name",
        re.compile(
            r"ХЕРСОНСКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ "
            r"МОЛОДЕЖНОЙ ОРГАНИЗАЦИИ\s*«ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ»",
            IC,
        ),
        "{{ customer_full_name }}",
    ))

    # Предмет закупки — встречается в ALL CAPS (заголовок) и обычным
    # регистром (информационная карта, строка 3) — тоже одним правилом.
    rules.append((
        "D02_subject",
        re.compile(
            r"Поставка нового легкового автомобиля повышенной проходимости "
            r"для обеспечения деятельности Херсонского регионального отделения "
            r"Всероссийского студенческого корпуса спасателей",
            IC,
        ),
        "{{ subject }}",
    ))

    rules.append((
        "D03_city_year",
        re.compile(r"Геническ,\s*2026", S),
        "{{ contract_city }}, {{ contract_date_year }}",
    ))

    rules.append((
        "D04_customer_address",
        re.compile(
            r"Херсонская область,\s*М\.О\.\s*Генический,\s*п\.\s*Геническая горка,\s*"
            r"ул\.\s*50-лет Победы,\s*д\.\s*6",
            S,
        ),
        "{{ customer_address }}",
    ))

    rules.append((
        "D05_customer_phone",
        re.compile(r"Тел\.:\s*\+7-990-166-31-07", S),
        "Тел.: {{ customer_phone }}",
    ))

    rules.append((
        "D06_nmcd_not_set",
        re.compile(r"\bНе установлена\b", S),
        "{{ total_nmcd }}",
    ))

    rules.append((
        "D07_submission_deadline",
        re.compile(r"31\.07\.2026\s+в\s+12:00", S),
        "{{ submission_deadline_datetime }}",
    ))

    return rules


def _fix_documentation_delivery_location(root, counts: dict) -> None:
    """
    D04 заменяет адрес заказчика ОБА раза, где он встречается дословно
    (строка 1 «Наименование, местонахождение...» и строка 4 «Место
    доставки...» информационной карты содержат в образце один и тот же
    адрес). Текстовый regex не может различить эти два абзаца — они
    идентичны по содержимому и находятся в разных ячейках таблицы.
    Поэтому здесь точечно правим именно строку «Место доставки...»,
    заменяя уже вставленный {{ customer_address }} на {{ delivery_location }}
    (абзацы ячеек таблицы — обычные w:p, см. root.findall('.//w:p')).
    """
    tables = root.findall(".//w:tbl", NS)
    if not tables:
        return
    table = tables[0]
    for row in table.findall("w:tr", NS):
        cells = row.findall("w:tc", NS)
        row_text = " ".join(
            docxedit.para_text(p)
            for c in cells
            for p in c.findall(".//w:p", NS)
        )
        if "Место доставки поставляемых товаров" not in row_text:
            continue
        for c in cells:
            for p in c.findall(".//w:p", NS):
                text = docxedit.para_text(p)
                if text.strip() == "{{ customer_address }}":
                    docxedit.replace_in_para(p, 0, len(text), "{{ delivery_location }}")
                    counts["D04b_delivery_location_fix"] = (
                        counts.get("D04b_delivery_location_fix", 0) + 1
                    )


# ─────────────────────────────────────────────────────────────────────────
# fabrikant_contract_project — "Договор поставки № ___"
# ─────────────────────────────────────────────────────────────────────────

def _rules_contract_project() -> list:
    rules = []

    rules.append((
        "CP01_title_number",
        re.compile(r"Договор поставки №\s*$", S),
        "Договор поставки № {{ contract_number }}",
    ))

    # «г. _____» — только до первых табов, дальше в абзаце идут w:tab,
    # regex не должен их захватывать (replace_in_para падает на non-text span).
    rules.append((
        "CP02_city",
        re.compile(r"г\.\s*_+(?=\t)", S),
        "г. {{ contract_city }}",
    ))
    rules.append((
        "CP03_date",
        re.compile(r"«__»\s+_+\s+2026\s*г\.", S),
        "«{{ contract_date_day }}» {{ contract_date_month }} {{ contract_date_year }} г.",
    ))

    # Преамбула Покупателя (региональное отделение ВСКС + краткое имя)
    rules.append((
        "CP04a_customer_org_name",
        re.compile(
            r"_+\s*региональное отделение Всероссийской общественной "
            r"молодежной организации\s*«Всероссийский студенческий корпус "
            r"спасателей»\s*\(_+\s*ВСКС\)",
            IC,
        ),
        "{{ customer_full_name }} ({{ customer_short_name }})",
    ))
    rules.append((
        "CP04b_customer_signatory",
        re.compile(
            r"в лице Председателя Совета\s+_+,\s*действующего на основании Устава",
            S,
        ),
        "в лице {{ customer_signatory_position }} {{ customer_signatory_name }}, "
        "действующего на основании {{ customer_signatory_basis }}",
    ))

    # Преамбула Поставщика
    rules.append((
        "CP05_contractor_preamble",
        re.compile(
            r"_+,\s*именуемое в дальнейшем «Поставщик»,\s*в лице\s*_+,\s*"
            r"действующего на основании\s*_+",
            S,
        ),
        "{{ contractor_full_name }}, именуемое в дальнейшем «Поставщик», "
        "в лице {{ contractor_signatory_position }} {{ contractor_signatory_name }}, "
        "действующего на основании {{ contractor_signatory_basis }}",
    ))

    # Протокол закупки — известен только номер, дата протокола отдельной
    # переменной в контексте нет (оставляем «от___» как есть).
    rules.append((
        "CP06_protocol_number",
        re.compile(r"\(Протокол №_+\s*от_+\)", S),
        "(Протокол №{{ procurement_protocol_number }} от___)",
    ))

    # п.4.1 — цена и НДС. В образце (в отличие от 8 типовых договоров)
    # сумма НДС отдельно не выделяется, указывается только ставка —
    # сохраняем формулировку источника «в размере N%», а не берём
    # синтаксис вида «НДС N% — сумма (пропись)» из rules_common.
    #
    # ВАЖНО: тримминг-дефисы Jinja2 ({%- ... -%}) внутри ОДНОГО абзаца
    # ломают рендер docxtpl именно в контексте ПОЛНОГО документа (изолированный
    # мини-docx рендерится нормально, но в реальном документе конструкция
    # "{{ vat_rate }}%{%- else %}" приводит к тому, что docxtpl молча
    # выбрасывает весь абзац при рендере, хотя raw-Jinja на том же XML
    # отрабатывает корректно — воспроизведено и подтверждено эмпирически).
    # Решение: тот же if/else, но БЕЗ дефисов-тримминга; пробелы расставлены
    # вручную вокруг тегов, чтобы не терять/дублировать пробелы в тексте.
    rules.append((
        "CP07_price_vat",
        re.compile(
            r"составляет\s+_+,00\s*\(_+\)\s*рублей 00 копеек,\s*"
            r"в том числе НДС в размере\s*_+\.",
            S,
        ),
        "составляет {{ contract_price_num }} ({{ contract_price_words }}) рублей 00 копеек, "
        "{% if vat_applicable %}в том числе НДС в размере {{ vat_rate }}%"
        "{% else %}НДС не облагается на основании {{ vat_exemption_article }}{% endif %}.",
    ))

    # п.4.6 — финансирование за счёт субсидии
    rules.append((
        "CP08_subsidy_agreement",
        re.compile(
            r"Соглашения №_+\s*о предоставлении субсидии из бюджета\s+_+\s+от\s+"
            r"_+\s+2026\s+года,\s*заключенного между\s+_+\s+РЕГИОНАЛЬНЫМ "
            r"ОТДЕЛЕНИЕМ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ ОРГАНИЗАЦИИ\s*"
            r"«ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ»\s+и\s+"
            r"МИНИСТЕРСТВОМ МОЛОДЕЖНОЙ ПОЛИТИКИ\s+_+",
            IC,
        ),
        "Соглашения № {{ subsidy_agreement_number }} о предоставлении субсидии "
        "из бюджета {{ subsidy_grantor_name }} от {{ subsidy_agreement_date }} года, "
        "заключенного между {{ customer_full_name }} и {{ subsidy_ministry_name }}",
    ))
    rules.append((
        "CP09_subsidy_budget_repeat",
        re.compile(r"за счет средств из бюджета\s+_+,", S),
        "за счет средств из бюджета {{ subsidy_grantor_name }},",
    ))

    # п.5.1.2 — срок поставки
    rules.append((
        "CP10_delivery_deadline",
        re.compile(r"в срок до\s*«___»\s+_+\s+2026\s+г\.", S),
        "в срок до {{ delivery_date }}",
    ))
    # п.5.2.1 — адрес местонахождения Покупателя (адрес поставки)
    rules.append((
        "CP11_delivery_address",
        re.compile(r"находящегося по адресу_+\.", S),
        "находящегося по адресу {{ customer_address }}.",
    ))

    # п.11.1 — дата окончания действия договора
    rules.append((
        "CP12_contract_end_date",
        re.compile(r"«30»\s+декабря\s+2026\s+г\.", S),
        "{{ contract_end_date }}",
    ))

    # Приложение № 1 — шапка «№___________ от_________»
    rules.append((
        "CP13_appendix_header",
        re.compile(r"^№_+\s*от_+$", S),
        "№ {{ contract_number }} от {{ contract_date }}",
    ))

    # Таблицы подписей — должности сторон (сами подписи/М.П. не трогаем —
    # это физическое место для подписи, как и в 8 договорных шаблонах).
    rules.append((
        "CP14_customer_signatory_position",
        re.compile(r"^Председатель Совета$", S),
        "{{ customer_signatory_position }}",
    ))
    rules.append((
        "CP15_contractor_signatory_position",
        re.compile(r"^Генеральный директор$", S),
        "{{ contractor_signatory_position }}",
    ))

    return rules


# ─────────────────────────────────────────────────────────────────────────
# Сборка
# ─────────────────────────────────────────────────────────────────────────

_RULES_BY_DOC = {
    "fabrikant_application_form": _rules_application_form,
    "fabrikant_documentation": _rules_documentation,
    "fabrikant_contract_project": _rules_contract_project,
}


def build_one(doc_type: str, out_dir: pathlib.Path) -> pathlib.Path:
    rel_path = SOURCES[doc_type]
    src = _REPO_ROOT / rel_path
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {src}")

    zip_bytes, root = docxedit.load(str(src))
    docxedit.normalize(root)

    rules = _RULES_BY_DOC[doc_type]()
    counts: dict[str, int] = {}

    for p in root.findall(".//w:p", NS):
        apply_fabrikant_rules(p, rules, counts)

    if doc_type == "fabrikant_application_form":
        _apply_af_price_table(root, counts)

    if doc_type == "fabrikant_documentation":
        _fix_documentation_delivery_location(root, counts)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc_type}.docx"
    docxedit.save(zip_bytes, root, str(out_path))

    all_rule_ids = [r[0] for r in rules]
    print(f"  {doc_type}:")
    for rid in all_rule_ids:
        n = counts.get(rid, 0)
        marker = "" if n else "  <-- WARN 0 срабатываний"
        print(f"    {rid}: {n}{marker}")
    for extra_id in sorted(set(counts) - set(all_rule_ids)):
        print(f"    {extra_id}: {counts[extra_id]}")

    return out_path


def main() -> None:
    out_dir = _TEMPLATES_DIR
    for doc_type in SOURCES:
        build_one(doc_type, out_dir)


if __name__ == "__main__":
    main()
