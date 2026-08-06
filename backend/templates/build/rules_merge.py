"""
rules_merge.py — обобщённое слияние двух вариантов одного документа
(базовый + вариант с доп. условиями) в единый шаблон с абзацными
условными тегами docxtpl ({%p if %}/{%p else %}/{%p endif %}).

Используется, когда два образца .docx отличаются друг от друга набором
вставленных/заменённых абзацев (напр. ГПХ без РИД / ГПХ +РИД, малая/большая
отчётность услуг). Выравнивание последовательностей абзацев делается через
difflib.SequenceMatcher на СПИСКАХ абзацев (не посимвольно), различия
оборачиваются в условные абзацные теги.
"""
import copy
import difflib
import re

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W}}}"
_NS = {"w": W}

_LEADING_NUM_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.\s*")
_WS_RE = re.compile(r"\s+")
_EDGE_PUNCT_RE = re.compile(r'^[\s.,;:!?…"\'«»()\[\]\-]+|[\s.,;:!?…"\'«»()\[\]\-]+$')


def _normalize_text(text: str) -> str:
    """Убирает ведущую нумерацию (напр. «4.1.2.»), схлопывает пробелы,
    приводит к нижнему регистру — для сравнения абзацев между документами."""
    text = _LEADING_NUM_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip().lower()
    return text


def _strict_key(text: str) -> str:
    """Более строгая нормализация поверх _normalize_text — дополнительно
    убирает знаки препинания на краях строки и вообще все пробелы.
    Нужна, чтобы «...: {{ x }}» и «...: {{ x }}.» (различие в одну точку)
    считались фактически одинаковым абзацем при сравнении replace-пар."""
    text = _normalize_text(text)
    # края могут содержать несколько символов пунктуации подряд («…»,
    # «.»/«»» и т.п.) — применяем, пока строка не перестанет меняться.
    prev = None
    while prev != text:
        prev = text
        text = _EDGE_PUNCT_RE.sub("", text)
    return _WS_RE.sub("", text)


def _is_blank(text: str) -> bool:
    """True, если абзац не содержит ни одного непробельного символа."""
    return not text.strip()


def _body_paragraphs(root) -> list:
    """Прямые дети w:body с тегом w:p (без вложенных — таблицы/текстбоксы
    не считаются абзацами верхнего уровня документа)."""
    body = root.find("w:body", _NS)
    if body is None:
        return []
    return [el for el in body if el.tag == f"{_W}p"]


def _strip_style_refs(p) -> None:
    """Удаляет ссылки на styles.xml/numbering.xml чужого документа
    (w:pStyle, w:numPr в pPr; w:rStyle в rPr) у скопированного абзаца.
    Прямое форматирование (остальные элементы w:rPr/w:pPr) сохраняется."""
    for ppr in p.findall("w:pPr", _NS):
        for tag in ("w:pStyle", "w:numPr"):
            for el in ppr.findall(tag, _NS):
                ppr.remove(el)
    for rpr in p.iter(f"{_W}rPr"):
        for el in list(rpr):
            if el.tag == f"{_W}rStyle":
                rpr.remove(el)


def _clone_paragraph(p):
    new_p = copy.deepcopy(p)
    _strip_style_refs(new_p)
    return new_p


def _insert_before(anchor, elements: list) -> None:
    """Вставляет elements (в порядке списка) непосредственно перед anchor."""
    if not elements:
        return
    parent = anchor.getparent()
    idx = list(parent).index(anchor)
    for offset, el in enumerate(elements):
        parent.insert(idx + offset, el)


def _insert_after(anchor, elements: list) -> None:
    """Вставляет elements (в порядке списка) непосредственно после anchor."""
    if not elements:
        return
    parent = anchor.getparent()
    idx = list(parent).index(anchor)
    for offset, el in enumerate(elements):
        parent.insert(idx + 1 + offset, el)


def merge_variant(root, variant_root, flag: str, counts: dict,
                   rule_prefix: str, base_start: int = 0, var_start: int = 0,
                   handle_delete: bool = True) -> None:
    """
    Выравнивает абзацы body базового документа (root) и документа-варианта
    (variant_root), оборачивает различия в условные абзацные теги docxtpl
    по значению переменной flag.

    - insert (абзацы только в варианте): {%p if flag %} + копии абзацев
      варианта + {%p endif %}.
    - replace (разные абзацы на одном месте): {%p if not flag %} + базовые
      абзацы + {%p else %} + копии абзацев варианта + {%p endif %}.
    - delete (абзацы только в базе): если handle_delete — {%p if not flag %}
      + базовые абзацы + {%p endif %}; иначе оставляются как есть.
    - equal: без изменений.

    Различие, не несущее смысла, условным блоком НЕ оборачивается —
    иначе builder плодит {%p if %} вокруг форматирования, а не контента:
    - Если все затронутые абзацы (insert — со стороны варианта, delete —
      со стороны базы, replace — с обеих сторон) пустые (не содержат
      непробельного текста), операция пропускается целиком: ничего не
      оборачивается и не вставляется. Счётчик: f"{rule_prefix}_skipped_empty".
    - Для replace, если тексты фактически совпадают (после более строгой
      нормализации — см. _strict_key), абзац варианта отбрасывается,
      базовый абзац остаётся как есть, без обёртки. Счётчик:
      f"{rule_prefix}_skipped_same".

    counts пополняется ключами f"{rule_prefix}_insert" / "_replace" / "_delete"
    (число сработавших опкодов каждого типа) и f"{rule_prefix}_skipped_empty" /
    "_skipped_same" (число опкодов, признанных незначащими и пропущенных).
    """
    from backend.templates.build.docxedit import (
        para_text, insert_para_before, insert_para_after,
    )

    base_paras = _body_paragraphs(root)
    var_paras = _body_paragraphs(variant_root)

    base_norm = [_normalize_text(para_text(p)) for p in base_paras]
    var_norm = [_normalize_text(para_text(p)) for p in var_paras]

    sm = difflib.SequenceMatcher(
        None,
        base_norm[base_start:],
        var_norm[var_start:],
    )
    opcodes = sm.get_opcodes()

    # Идём по опкодам В ОБРАТНОМ ПОРЯДКЕ — иначе индексы более ранних
    # опкодов «поедут» после вставок, сделанных для более поздних.
    for tag, i1, i2, j1, j2 in reversed(opcodes):
        if tag == "equal":
            continue

        bi1, bi2 = base_start + i1, base_start + i2
        vj1, vj2 = var_start + j1, var_start + j2

        if tag == "insert":
            var_texts = [para_text(var_paras[k]) for k in range(vj1, vj2)]
            if not any(not _is_blank(t) for t in var_texts):
                # Все абзацы варианта на этой позиции пустые — различие
                # чисто форматирования (лишние отбивки), не контент.
                counts[f"{rule_prefix}_skipped_empty"] = (
                    counts.get(f"{rule_prefix}_skipped_empty", 0) + 1
                )
                continue

            var_slice = [_clone_paragraph(var_paras[k]) for k in range(vj1, vj2)]
            if not var_slice:
                continue

            if bi1 < len(base_paras):
                anchor = base_paras[bi1]
                insert_para_before(anchor, "{%p if " + flag + " %}")
                _insert_before(anchor, var_slice)
                insert_para_before(anchor, "{%p endif %}")
            else:
                # Вставка после последнего абзаца базового документа
                # (нет базового абзаца-«якоря» на этой позиции).
                if not base_paras:
                    continue
                tail_anchor = base_paras[-1]
                open_p = insert_para_after(tail_anchor, "{%p if " + flag + " %}")
                _insert_after(open_p, var_slice)
                insert_para_after(var_slice[-1], "{%p endif %}")

            counts[f"{rule_prefix}_insert"] = counts.get(f"{rule_prefix}_insert", 0) + 1

        elif tag == "replace":
            base_texts = [para_text(base_paras[k]) for k in range(bi1, bi2)]
            var_texts = [para_text(var_paras[k]) for k in range(vj1, vj2)]

            if not any(not _is_blank(t) for t in base_texts) and \
                    not any(not _is_blank(t) for t in var_texts):
                # Обе стороны пустые — форматирование, не контент.
                counts[f"{rule_prefix}_skipped_empty"] = (
                    counts.get(f"{rule_prefix}_skipped_empty", 0) + 1
                )
                continue

            if [_strict_key(t) for t in base_texts] == [_strict_key(t) for t in var_texts]:
                # Тексты фактически совпадают (различие только в пунктуации/
                # пробелах) — оставляем базовый абзац как есть, без условного
                # блока, вариант отбрасываем.
                counts[f"{rule_prefix}_skipped_same"] = (
                    counts.get(f"{rule_prefix}_skipped_same", 0) + 1
                )
                continue

            first_base = base_paras[bi1]
            last_base = base_paras[bi2 - 1]
            var_slice = [_clone_paragraph(var_paras[k]) for k in range(vj1, vj2)]

            insert_para_before(first_base, "{%p if not " + flag + " %}")
            else_p = insert_para_after(last_base, "{%p else %}")
            if var_slice:
                _insert_after(else_p, var_slice)
                insert_para_after(var_slice[-1], "{%p endif %}")
            else:
                insert_para_after(else_p, "{%p endif %}")

            counts[f"{rule_prefix}_replace"] = counts.get(f"{rule_prefix}_replace", 0) + 1

        elif tag == "delete":
            base_texts = [para_text(base_paras[k]) for k in range(bi1, bi2)]
            if not any(not _is_blank(t) for t in base_texts):
                # Все затронутые абзацы базы пустые — форматирование
                # (напр. отбивки перед «Приложение № 1»), не контент.
                counts[f"{rule_prefix}_skipped_empty"] = (
                    counts.get(f"{rule_prefix}_skipped_empty", 0) + 1
                )
                continue

            if handle_delete:
                first_base = base_paras[bi1]
                last_base = base_paras[bi2 - 1]
                insert_para_before(first_base, "{%p if not " + flag + " %}")
                insert_para_after(last_base, "{%p endif %}")
            counts[f"{rule_prefix}_delete"] = counts.get(f"{rule_prefix}_delete", 0) + 1
