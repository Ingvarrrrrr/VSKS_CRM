"""
rules_subsidy_clauses.py — вставляет в 7 собираемых форм договора
(contract_goods_single, contract_services, contract_services_food,
contract_gph_individual, contract_gph_individual_rid,
contract_repair_framework, contract_repair_vehicle) условные пункты из
переменных карточки субсидии. История решений владельца:

21.10.2026 (исходное решение) — два места:
  1. Последним пунктом раздела 1 «Предмет договора» — ссылка на соглашение
     о предоставлении субсидии: «N.k. Договор заключён в рамках реализации
     {{subsidy_agreement_text}}.», обёрнутая в {%p if subsidy_agreement_text %}.
  2. Два доп. пункта {{subsidy_extra_clause_1}}/{{subsidy_extra_clause_2}}.

21.10.2026 вечер (ревью №1) — дедуп: contract_services/contract_services_food
уже содержат эквивалентный пункт 1.3 «Настоящий Договор заключен в рамках
реализации {{ customer_short_name }} Соглашения...» — для них НЕ
добавляется новый пункт 1-го места, вместо этого существующий 1.3 делается
условным (apply_subsidy_agreement_clause, ветка _DEDUP_AGREEMENT_DOC_TYPES).

22.10.2026 (ревью №2) — новое место для доп. пунктов: НЕ последний раздел
перед реквизитами, а КОНЕЦ раздела 4 (цена/порядок расчётов и финансирование
за счёт субсидии), сразу после последних пунктов про субсидию, которые там
уже есть. Для форм с текстовой нумерацией — конец раздела определяется явным
заголовком СЛЕДУЮЩЕГО раздела (_PRICE_SECTION_NEXT_HEADING). Для ГПХ
(автонумерация, раздел 4 там продолжается другими, не связанными с
субсидией пунктами про приёмку услуг) — сразу после абзаца «Финансирование
договора осуществляется в рамках соглашения о предоставлении ... субсидии»
(без ожидания конца всего раздела). contract.docx (вне SOURCES) — пункта
о субсидии в разделе 4 нет, доп. пункты остаются там же, где были (6.3/6.4
раздела 6, см. patch_offbuild.py).

Шрифт/отступы нового абзаца — как у абзаца-образца (клонируется целиком,
см. docxedit.clone_para_with_text). Для форм с автонумерацией Word
(gph_individual/gph_individual_rid, w:numPr) номер в тексте не пишем —
нумерация продолжается сама.
"""
import re

from backend.templates.build import docxedit

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ns = {"w": W}

# Доки, где пункт про соглашение субсидии уже есть в разделе 1 под другим
# текстом/номером — для них НЕ добавляем новый пункт, а делаем
# существующий условным (см. apply_subsidy_agreement_clause).
_DEDUP_AGREEMENT_DOC_TYPES = frozenset({"contract_services", "contract_services_food"})

_DUP_AGREEMENT_RE = re.compile(
    r"^(\d+\.\d+)\.\s*(Настоящий Договор заключен в рамках реализации"
    r"\s*\{\{\s*customer_short_name\s*\}\}.*)$",
    re.S,
)

# doc_type -> (следующий заголовок после раздела "Предмет договора",
#              номер пункта про subsidy_agreement_text | None для автонумерации)
_CONFIG = {
    "contract_goods_single": (
        re.compile(r"Комплект,\s*комплектность и документы на товар", re.I),
        "1.5",
    ),
    "contract_services": (
        re.compile(r"Права и обязанности Сторон", re.I),
        "1.5",
    ),
    "contract_services_food": (
        re.compile(r"Права и обязанности Сторон", re.I),
        "1.5",
    ),
    "contract_repair_framework": (
        re.compile(r"ПОРЯДОК ВЫПОЛНЕНИЯ РАБОТ", re.I),
        "1.4",
    ),
    "contract_repair_vehicle": (
        re.compile(r"ПОРЯДОК ВЫПОЛНЕНИЯ РАБОТ", re.I),
        "1.4",
    ),
    "contract_gph_individual": (
        re.compile(r"Срок оказания услуг и срок действия Договора", re.I),
        None,
    ),
    "contract_gph_individual_rid": (
        re.compile(r"Срок оказания услуг и срок действия Договора", re.I),
        None,
    ),
}

_GPH_DOC_TYPES = frozenset({"contract_gph_individual", "contract_gph_individual_rid"})

# Заголовок раздела, идущего СРАЗУ ПОСЛЕ раздела 4 (цена/расчёты/
# финансирование) — конец этого раздела и есть точка вставки доп. пунктов
# (для форм с текстовой нумерацией; ГПХ обрабатывается отдельно).
_PRICE_SECTION_NEXT_HEADING = {
    "contract_goods_single": re.compile(r"Сроки и условия поставки", re.I),
    "contract_services": re.compile(r"Ответственность Сторон", re.I),
    "contract_services_food": re.compile(r"Ответственность Сторон", re.I),
    "contract_repair_framework": re.compile(r"ГАРАНТИИ", re.I),
    "contract_repair_vehicle": re.compile(r"ГАРАНТИИ", re.I),
}

# Номера доп. пунктов (n1, n2) — фактический следующий номер после
# последнего пункта раздела 4 в каждой форме (см. докстринг выше).
_EXTRA_CLAUSE_NUMBERS = {
    "contract_goods_single": ("4.8", "4.9"),
    "contract_services": ("4.7", "4.8"),
    "contract_services_food": ("4.7", "4.8"),
    "contract_repair_framework": ("4.10", "4.11"),
    "contract_repair_vehicle": ("4.10", "4.11"),
}

# Абзац «Финансирование договора осуществляется в рамках соглашения о
# предоставлении ... субсидии» — используется ТОЛЬКО для ГПХ (см. докстринг).
_FINANCING_RE = re.compile(r"Финансирование.*?субсид", re.I | re.S)


def _find_heading(paragraphs, phrase_re: "re.Pattern") -> "object | None":
    for p in paragraphs:
        text = docxedit.para_text(p).strip()
        if len(text) < 90 and phrase_re.search(text):
            return p
    return None


def _insert_clause_before(anchor_p, template_p, clause_text: str, cond_var: str, counts: dict, rule_id: str) -> None:
    """
    Вставляет новый абзац с текстом clause_text прямо ПЕРЕД anchor_p,
    оформлением (pPr/рана) — как у template_p (клон), обёрнутый в
    {%p if {cond_var} %} / {%p endif %}.
    """
    new_p = docxedit.clone_para_with_text(template_p, clause_text)
    parent = anchor_p.getparent()
    idx = list(parent).index(anchor_p)
    parent.insert(idx, new_p)
    docxedit.insert_para_before(new_p, f"{{%p if {cond_var} %}}")
    docxedit.insert_para_after(new_p, "{%p endif %}")
    counts[rule_id] = counts.get(rule_id, 0) + 1


def _para_before(anchor_p, paragraphs):
    """Абзац, непосредственно предшествующий anchor_p в документе."""
    parent = anchor_p.getparent()
    idx = list(parent).index(anchor_p)
    siblings = list(parent)
    for i in range(idx - 1, -1, -1):
        if siblings[i].tag == f"{{{W}}}p":
            return siblings[i]
    return None


def _para_after(anchor_p, paragraphs):
    """Абзац, непосредственно следующий за anchor_p в документе."""
    parent = anchor_p.getparent()
    idx = list(parent).index(anchor_p)
    siblings = list(parent)
    for i in range(idx + 1, len(siblings)):
        if siblings[i].tag == f"{{{W}}}p":
            return siblings[i]
    return None


def apply_subsidy_agreement_clause(doc_type: str, paragraphs: list, counts: dict) -> None:
    """Печатает ссылку на соглашение о субсидии последним пунктом раздела
    «Предмет договора» (только для 7 собираемых форм, см. _CONFIG).

    Для contract_services/contract_services_food — не новый пункт, а
    существующий 1.3 делается условным (см. _DEDUP_AGREEMENT_DOC_TYPES).
    """
    cfg = _CONFIG.get(doc_type)
    if cfg is None:
        return
    subject_re, number = cfg

    if doc_type in _DEDUP_AGREEMENT_DOC_TYPES:
        for p in paragraphs:
            full_text = docxedit.para_text(p)
            m = _DUP_AGREEMENT_RE.match(full_text.strip())
            if m is None:
                continue
            num, rest = m.group(1), m.group(2)
            new_text = (
                f"{num}. {{% if subsidy_agreement_text %}}"
                f"Настоящий Договор заключен в рамках реализации "
                f"{{{{subsidy_agreement_text}}}}."
                f"{{% else %}}{rest}{{% endif %}}"
            )
            docxedit.replace_in_para(p, 0, len(full_text), new_text)
            counts["SUB_01_agreement_text_clause"] = counts.get("SUB_01_agreement_text_clause", 0) + 1
            return
        raise RuntimeError(
            f"{doc_type}: ожидаемый дублирующий пункт «заключен в рамках "
            f"реализации {{ customer_short_name }} Соглашения» не найден "
            f"— дедуп subsidy_agreement_text остановлен."
        )

    heading_p = _find_heading(paragraphs, subject_re)
    if heading_p is None:
        raise RuntimeError(
            f"{doc_type}: заголовок раздела после «Предмет договора» "
            f"не найден (regex {subject_re.pattern!r}) — вставка "
            f"subsidy_agreement_text остановлена."
        )
    template_p = _para_before(heading_p, paragraphs)
    if template_p is None:
        raise RuntimeError(f"{doc_type}: не найден абзац-образец перед {subject_re.pattern!r}")

    if number is not None:
        text = f"{number}. Договор заключён в рамках реализации {{{{subsidy_agreement_text}}}}."
    else:
        text = "Договор заключён в рамках реализации {{subsidy_agreement_text}}."

    _insert_clause_before(
        heading_p, template_p, text, "subsidy_agreement_text",
        counts, "SUB_01_agreement_text_clause",
    )


def apply_subsidy_extra_clauses(doc_type: str, paragraphs: list, counts: dict) -> None:
    """Вставляет два дополнительных пункта ({{subsidy_extra_clause_1}} /
    {{subsidy_extra_clause_2}}) в конец раздела 4 (цена/расчёты/
    финансирование за счёт субсидии) — сразу после последних пунктов про
    субсидию, которые там уже есть (только для 7 собираемых форм)."""
    cfg = _CONFIG.get(doc_type)
    if cfg is None:
        return

    if doc_type in _GPH_DOC_TYPES:
        financing_p = None
        for p in paragraphs:
            if _FINANCING_RE.search(docxedit.para_text(p)):
                financing_p = p
                break
        if financing_p is None:
            raise RuntimeError(
                f"{doc_type}: абзац «Финансирование договора осуществляется "
                f"в рамках соглашения о предоставлении ... субсидии» не "
                f"найден — вставка subsidy_extra_clause_1/2 остановлена."
            )
        anchor_p = _para_after(financing_p, paragraphs)
        if anchor_p is None:
            raise RuntimeError(f"{doc_type}: не найден абзац сразу после пункта о финансировании")
        template_p = financing_p
        text1 = "{{subsidy_extra_clause_1}}"
        text2 = "{{subsidy_extra_clause_2}}"
    else:
        heading_re = _PRICE_SECTION_NEXT_HEADING[doc_type]
        heading_p = _find_heading(paragraphs, heading_re)
        if heading_p is None:
            raise RuntimeError(
                f"{doc_type}: заголовок раздела после раздела 4 не найден "
                f"(regex {heading_re.pattern!r}) — вставка "
                f"subsidy_extra_clause_1/2 остановлена."
            )
        anchor_p = heading_p
        template_p = _para_before(anchor_p, paragraphs)
        if template_p is None:
            raise RuntimeError(f"{doc_type}: не найден абзац-образец перед {heading_re.pattern!r}")

        n1, n2 = _EXTRA_CLAUSE_NUMBERS[doc_type]
        text1 = f"{n1}. {{{{subsidy_extra_clause_1}}}}"
        text2 = (
            "{% if subsidy_extra_clause_1 %}" + n2 + "{% else %}" + n1 + "{% endif %}."
            " {{subsidy_extra_clause_2}}"
        )

    # Каждая вставка кладёт блок НЕПОСРЕДСТВЕННО перед anchor_p (оттесняя
    # anchor_p дальше) — поэтому первый пункт вставляем ПЕРВЫМ (он окажется
    # сразу за существующим текстом раздела), а второй — ВТОРЫМ (попадёт
    # между первым пунктом и anchor_p), итоговый порядок: clause_1,
    # clause_2, anchor_p.
    _insert_clause_before(
        anchor_p, template_p, text1, "subsidy_extra_clause_1",
        counts, "SUB_02_extra_clause_1",
    )
    _insert_clause_before(
        anchor_p, template_p, text2, "subsidy_extra_clause_2",
        counts, "SUB_03_extra_clause_2",
    )
