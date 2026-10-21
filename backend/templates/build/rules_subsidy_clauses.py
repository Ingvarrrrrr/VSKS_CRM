"""
rules_subsidy_clauses.py — вставляет в 7 собираемых форм договора
(contract_goods_single, contract_services, contract_services_food,
contract_gph_individual, contract_gph_individual_rid,
contract_repair_framework, contract_repair_vehicle) условные пункты из
переменных карточки субсидии (решение владельца 21.10.2026, правки по
ревью 21.10.2026 вечер):

1. Последним пунктом раздела 1 «Предмет договора» — ссылка на соглашение о
   предоставлении субсидии: «N.k. Договор заключён в рамках реализации
   {{subsidy_agreement_text}}.», обёрнутая в {%p if subsidy_agreement_text %}.
   ИСКЛЮЧЕНИЕ (дедуп, ревью): contract_services/contract_services_food уже
   содержат эквивалентный пункт 1.3 «Настоящий Договор заключен в рамках
   реализации {{ customer_short_name }} Соглашения, заключенного с ...» —
   для них НЕ добавляется новый пункт, а существующий 1.3 делается условным
   (if subsidy_agreement_text — печатает короткую форму с переменной,
   иначе — исходный текст без изменений), см. apply_subsidy_agreement_clause.
   (У contract.docx — вне SOURCES — такой же пункт уже есть, 1.4; его
   только оборачивают в условие, см. patch_offbuild.py CONTRACT_RULES.)

2-3. {{subsidy_extra_clause_1}} и {{subsidy_extra_clause_2}}, каждый в своём
   {%p if %}/{%p endif %}, чтобы пустое поле карточки субсидии = пункта нет
   (без пустого абзаца на его месте). Точка вставки — ПЕРЕД пунктом
   «Приложение(-я):» раздела (и его подпунктами-строками списка), если такой
   пункт есть в разделе; если нет — в конец раздела (перед заголовком
   следующего раздела), как раньше. При текстовой нумерации, если пункт
   «Приложения» найден, оба новых пункта получают его номер (первый — сам
   номер «Приложения», второй — +1 либо тот же, если первый пуст), а сам
   пункт «Приложения» становится `N.{{ M + (1 if subsidy_extra_clause_1
   else 0) + (1 if subsidy_extra_clause_2 else 0) }}.` — число сдвигается
   автоматически на то, сколько пунктов реально напечаталось.

Точка вставки — НЕ фиксированный индекс абзаца (хрупко к порядку правил
R1-R6/T4 в build.py), а «абзац прямо ПЕРЕД следующим заголовком раздела»
(или пунктом «Приложения» внутри него): устойчиво независимо от того,
применены ли уже другие правила-обёртки (apply_r2_third_party_wrap и т.п.)
к предыдущим абзацам того же раздела.

Нумерация: для форм с текстовой нумерацией (goods_single/services/
services_food/repair_framework/repair_vehicle) номер пишем явно. Для форм с
автонумерацией Word (gph_individual/gph_individual_rid, w:numPr) —
клонируем соседний пронумерованный абзац без текста номера, нумерация
продолжится сама.

Шрифт/отступы нового абзаца — как у абзаца-образца (клонируется целиком,
см. docxedit.clone_para_with_text).
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

# Абзац-«пункт приложений»: «Приложение:»/«Приложения:» (заголовок списка,
# обычно с номером) или сами строки списка («- Приложение № 1 – ...» /
# «Приложение № 1 – ...» при автонумерации). «Все Приложения Договора
# являются неотъемлемой частью...» НЕ матчится — после снятия номерного
# префикса текст начинается не со слова «Приложени», а со слова «Все».
_APPENDIX_ITEM_RE = re.compile(r"^Приложени[ея]\b", re.I)
_NUM_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s*")
# Заголовок списка приложений с текстовым номером целиком: «11.9. Приложение:»
_APPENDIX_HEADER_RE = re.compile(r"^(\d+)\.(\d+)\.\s*(Приложени[ея]:?)\s*$", re.I)


def _is_appendix_para(text: str) -> bool:
    t = text.strip()
    if t.startswith("-"):
        t = t[1:].strip()
    t = _NUM_PREFIX_RE.sub("", t)
    return bool(_APPENDIX_ITEM_RE.match(t))


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


# doc_type -> (следующий заголовок после раздела "Предмет договора",
#              следующий заголовок после финального раздела перед реквизитами,
#              текстовая_нумерация: str | None  — если None, автонумерация w:numPr,
#              запасные номера (n1, n2), если пункт «Приложения» не найден)
_CONFIG = {
    "contract_goods_single": (
        re.compile(r"Комплект,\s*комплектность и документы на товар", re.I),
        re.compile(r"Адреса и реквизиты сторон", re.I),
        "1.5", ("11.10", "11.11"),
    ),
    "contract_services": (
        re.compile(r"Права и обязанности Сторон", re.I),
        re.compile(r"Адреса и реквизиты Сторон", re.I),
        "1.5", ("10.13", "10.14"),
    ),
    "contract_services_food": (
        re.compile(r"Права и обязанности Сторон", re.I),
        re.compile(r"Адреса и реквизиты Сторон", re.I),
        "1.5", ("10.13", "10.14"),
    ),
    "contract_repair_framework": (
        re.compile(r"ПОРЯДОК ВЫПОЛНЕНИЯ РАБОТ", re.I),
        re.compile(r"ЮРИДИЧЕСКИЕ АДРЕСА И БАНКОВСКИЕ РЕКВИЗИТЫ СТОРОН", re.I),
        "1.4", ("10.16", "10.17"),
    ),
    "contract_repair_vehicle": (
        re.compile(r"ПОРЯДОК ВЫПОЛНЕНИЯ РАБОТ", re.I),
        re.compile(r"ЮРИДИЧЕСКИЕ АДРЕСА И БАНКОВСКИЕ РЕКВИЗИТЫ СТОРОН", re.I),
        "1.4", ("10.16", "10.17"),
    ),
    # Автонумерация (w:numPr) — номер text=None, клон соседнего пункта.
    "contract_gph_individual": (
        re.compile(r"Срок оказания услуг и срок действия Договора", re.I),
        re.compile(r"Адреса и реквизиты Сторон", re.I),
        None, None,
    ),
    "contract_gph_individual_rid": (
        re.compile(r"Срок оказания услуг и срок действия Договора", re.I),
        re.compile(r"Адреса и реквизиты Сторон", re.I),
        None, None,
    ),
}


def _para_before(anchor_p, paragraphs):
    """Абзац, непосредственно предшествующий anchor_p в документе
    (последний абзац раздела, из него клонируется форматирование)."""
    parent = anchor_p.getparent()
    idx = list(parent).index(anchor_p)
    siblings = list(parent)
    for i in range(idx - 1, -1, -1):
        if siblings[i].tag == f"{{{W}}}p":
            return siblings[i]
    return None


def _find_appendix_block_start(heading_p):
    """
    Идёт от heading_p назад по телу документа, пропуская пустые абзацы, и
    собирает КОНТИГУОЗНЫЙ блок «абзацев про приложения» (см.
    _is_appendix_para), примыкающий вплотную к heading_p. Возвращает самый
    РАННИЙ (верхний) абзац этого блока — туда нужно вставлять новые пункты.
    Если блока нет (последний пункт раздела — не про приложения), None.
    """
    parent = heading_p.getparent()
    siblings = list(parent)
    idx = siblings.index(heading_p)

    first_idx = None
    i = idx - 1
    while i >= 0:
        node = siblings[i]
        if node.tag != f"{{{W}}}p":
            i -= 1
            continue
        text = docxedit.para_text(node).strip()
        if text == "":
            i -= 1
            continue
        if _is_appendix_para(text):
            first_idx = i
            i -= 1
            continue
        break

    if first_idx is None:
        return None
    return siblings[first_idx]


def apply_subsidy_agreement_clause(doc_type: str, paragraphs: list, counts: dict) -> None:
    """Печатает ссылку на соглашение о субсидии последним пунктом раздела
    «Предмет договора» (только для 7 собираемых форм, см. _CONFIG).

    Для contract_services/contract_services_food — не новый пункт, а
    существующий 1.3 делается условным (см. _DEDUP_AGREEMENT_DOC_TYPES).
    """
    cfg = _CONFIG.get(doc_type)
    if cfg is None:
        return
    subject_re, _final_re, number, _final_numbers = cfg

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
    {{subsidy_extra_clause_2}}) ПЕРЕД пунктом «Приложение(-я):» финального
    раздела (если он есть — вместе с перенумерацией этого пункта), иначе —
    последними пунктами раздела перед реквизитами/подписями сторон (только
    для 7 собираемых форм)."""
    cfg = _CONFIG.get(doc_type)
    if cfg is None:
        return
    _subject_re, final_re, number, final_numbers = cfg

    heading_p = _find_heading(paragraphs, final_re)
    if heading_p is None:
        raise RuntimeError(
            f"{doc_type}: заголовок «Адреса и реквизиты сторон» (или аналог) "
            f"не найден (regex {final_re.pattern!r}) — вставка "
            f"subsidy_extra_clause_1/2 остановлена."
        )

    appendix_p = _find_appendix_block_start(heading_p)
    anchor_p = appendix_p if appendix_p is not None else heading_p

    template_p = _para_before(anchor_p, paragraphs)
    if template_p is None:
        raise RuntimeError(f"{doc_type}: не найден абзац-образец перед {anchor_p!r}")

    # Без добавленной точки после переменной: subsidy_extra_clause_1/2 —
    # готовые законченные предложения из карточки субсидии (в отличие от
    # subsidy_agreement_text, которая — часть одной фразы в точке 1).
    if number is not None:
        n1, n2 = final_numbers
        renumbered_appendix = False

        if appendix_p is not None:
            header_text = docxedit.para_text(appendix_p).strip()
            hm = _APPENDIX_HEADER_RE.match(header_text)
            if hm is not None:
                section, base_str, label = hm.group(1), hm.group(2), hm.group(3)
                base = int(base_str)
                n1 = f"{section}.{base}"
                n2 = f"{section}.{base + 1}"
                new_header_text = (
                    f"{section}.{{{{ {base} "
                    f"+ (1 if subsidy_extra_clause_1 else 0) "
                    f"+ (1 if subsidy_extra_clause_2 else 0) }}}}. {label}"
                )
                full_header_text = docxedit.para_text(appendix_p)
                docxedit.replace_in_para(appendix_p, 0, len(full_header_text), new_header_text)
                renumbered_appendix = True

        text1 = f"{n1}. {{{{subsidy_extra_clause_1}}}}"
        text2 = (
            "{% if subsidy_extra_clause_1 %}" + n2 + "{% else %}" + n1 + "{% endif %}."
            " {{subsidy_extra_clause_2}}"
        )
        if renumbered_appendix:
            counts["SUB_04_appendix_header_renumbered"] = counts.get("SUB_04_appendix_header_renumbered", 0) + 1
    else:
        text1 = "{{subsidy_extra_clause_1}}"
        text2 = "{{subsidy_extra_clause_2}}"

    # Каждая вставка кладёт блок НЕПОСРЕДСТВЕННО перед anchor_p (оттесняя
    # anchor_p дальше) — поэтому первый пункт вставляем ПЕРВЫМ (он окажется
    # сразу за существующим текстом раздела), а второй — ВТОРЫМ (попадёт
    # между первым пунктом и anchor_p), итоговый порядок: clause_1,
    # clause_2, anchor_p (пункт «Приложения» или заголовок раздела).
    _insert_clause_before(
        anchor_p, template_p, text1, "subsidy_extra_clause_1",
        counts, "SUB_02_extra_clause_1",
    )
    _insert_clause_before(
        anchor_p, template_p, text2, "subsidy_extra_clause_2",
        counts, "SUB_03_extra_clause_2",
    )
