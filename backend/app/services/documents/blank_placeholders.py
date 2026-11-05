"""Единая подстановка «пустографок» для дат и номеров при рендере .docx.

Владелец (28.10.2026): «если дата поставки или какая-то дата не указана —
ставить __.__.____, чтобы вписать от руки после распечатки. Так же для
номеров: если по разметке шаблона номер/дата должны быть, но не заполнены —
ставить _____________________».

ПРАВИЛО №6: это ЕДИНСТВЕННОЕ место, где решается, какое пустое поле
контекста печатается линией подчёркивания вместо "". fabrikant_contract_blank.py
(гашение полей ПРОЕКТА договора — поставщик/цена/номер договора, которых
на этом этапе физически не существует) переиспользует отсюда BLANK_DATE —
свой список полей он определяет сам (другая причина гашения, другая длина
линий для некоторых полей), но общую "__.__.____" берёт здесь, а не считает
второй раз.

Как подключить новую точку рендера: заменить `tpl.render(context)` на
`render_docx(tpl, context)` из этого модуля — больше ничего не нужно.
"""

from __future__ import annotations

import copy
import re
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# ── Тексты-маркеры для незаполненных переменных (владелец, 05.11.2026) ────
MISSING_CONTRACTOR_TEXT = "Не хватает данных, заполните карточку контрагента"
MISSING_PURCHASE_TEXT = "Заполните карточку закупки"

# ── Legacy-константы (сохранены для обратной совместимости импортов,
#    например fabrikant_contract_blank.py для проекта договора до торгов) ──
BLANK_DATE = "__.__.____"                   # полная дата
BLANK_NUMBER = "_____________________"      # номер/реестровый номер (21 "_")
BLANK_DAY = "__"                             # contract_date_day
BLANK_MONTH = "__________"                   # contract_date_month (месяц словом)
BLANK_YEAR = "____"                          # contract_date_year

# Поля, которые НЕ должны превращаться в видимый маркер при пустом значении:
# технические/служебные поля, перечисления управления ветвлением и опциональные
# подписи позиций ТЗ, которые по дизайну пусты у обычных строк.
_NEVER_BLANK: frozenset[str] = frozenset({
    "today",
    "today_iso",
    "doc_kind",
    "subject_kind",
    "status",
    "period_type",
    "service_term_mode",
    "service_term_type",
    "contractor_org_type",
    "num",
    "photo",
    "_product",
    "menu_lines",
    "form_summary",
    "description",
})

_MARKERS: tuple[str, ...] = (MISSING_CONTRACTOR_TEXT, MISSING_PURCHASE_TEXT)
_MARKER_SPLIT_RE = re.compile(
    "(" + "|".join(re.escape(m) for m in _MARKERS) + ")"
)


class Blank:
    """Значение для пустого поля даты/номера: при печати в docx — линия
    подчёркивания, но во всех проверках Python/Jinja — ложно, как и было
    с исходной "" (чтобы `{% if contract_end_date %}...{% else %}до полного
    исполнения{% endif %}` и подобные ветки шаблонов продолжали работать).
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text = text

    def __str__(self) -> str:
        return self._text

    def __repr__(self) -> str:
        return f"Blank({self._text!r})"

    # MarkupSafe (jinja2 autoescape) спрашивает __html__ раньше str(), чтобы
    # не экранировать уже готовый текст — у нас в линии нет HTML-спецсимволов,
    # но определяем явно, чтобы поведение не зависело от версии jinja2/markupsafe.
    def __html__(self) -> str:
        return self._text

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        if other is None:
            return True
        if isinstance(other, str):
            return other == ""
        if isinstance(other, Blank):
            return True
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash("")


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _is_contractor_key(key: str) -> bool:
    if key in _NEVER_BLANK:
        return False
    return key.startswith("contractor_")


def _apply_to_flat_dict(data: dict) -> dict:
    """Возвращает НОВЫЙ dict — одноуровневая обработка пустых полей."""
    out = dict(data)
    for key, value in list(out.items()):
        if key in _NEVER_BLANK:
            continue
        if not _is_empty(value):
            continue
        if _is_contractor_key(key):
            out[key] = Blank(MISSING_CONTRACTOR_TEXT)
        else:
            out[key] = Blank(MISSING_PURCHASE_TEXT)
    return out


# Ключи верхнего уровня, под которыми в context лежит список позиций — их
# элементы (dict) тоже проверяются на пустые значения.
_LIST_KEYS: tuple[str, ...] = ("items", "items_list", "contract_items")


def apply_blank_placeholders(context: dict) -> dict:
    """Возвращает НОВЫЙ context: пустые поля contractor_* — Blank(MISSING_CONTRACTOR_TEXT),
    остальные пустые переменные — Blank(MISSING_PURCHASE_TEXT).

    Исходный context не мутируется. Обрабатываются ключи верхнего уровня и,
    отдельно, элементы списков items/items_list/contract_items (если это словари).
    """
    out = _apply_to_flat_dict(context)
    for list_key in _LIST_KEYS:
        items = out.get(list_key)
        if isinstance(items, list):
            out[list_key] = [
                _apply_to_flat_dict(item) if isinstance(item, dict) else item
                for item in items
            ]
    return out


def _add_yellow_highlight(r_el) -> None:
    """Добавляет <w:highlight w:val="yellow"/> в <w:rPr> элемента <w:r>."""
    rPr = r_el.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        r_el.insert(0, rPr)
    existing = rPr.find(qn("w:highlight"))
    if existing is not None:
        existing.set(qn("w:val"), "yellow")
    else:
        hl = OxmlElement("w:highlight")
        hl.set(qn("w:val"), "yellow")
        rPr.append(hl)


def _collapse_adjacent_markers_in_paragraph(p_el) -> None:
    """Схлопывает подряд идущие одинаковые маркеры внутри одного абзаца
    (например, когда разбитая дата «{{ contract_date_day }}» {{ contract_date_month }}
    {{ contract_date_year }} или должность + ФИО подписанта оба пусты)."""
    t_elements = p_el.findall(".//" + qn("w:t"))
    if not t_elements:
        return

    # 1. Внутри одного <w:t>
    for t_el in t_elements:
        txt = t_el.text or ""
        if not txt:
            continue
        changed = False
        for m in _MARKERS:
            esc = re.escape(m)
            # «Заполните...» Заполните... Заполните...
            new_txt = re.sub(rf"«{esc}»(?:\s+{esc})+", m, txt)
            new_txt = re.sub(rf"{esc}(?:\s+{esc})+", m, new_txt)
            if new_txt != txt:
                txt = new_txt
                changed = True
        if changed:
            t_el.text = txt
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    # 2. Между соседними <w:t> в том же абзаце
    for m in _MARKERS:
        prev_had_marker = False
        for idx, t_el in enumerate(t_elements):
            txt = t_el.text or ""
            if not txt:
                continue
            if prev_had_marker:
                stripped = txt.strip()
                if stripped in ("", "»", "«"):
                    if stripped in ("»", "«") and idx + 1 < len(t_elements) and m in (t_elements[idx + 1].text or ""):
                        t_el.text = txt.replace("»", "").replace("«", "")
                    continue
                if stripped == m or stripped == f"» {m}" or stripped == f"{m} г.":
                    t_el.text = txt.replace("»", "", 1).replace(m, "", 1).lstrip()
                    t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    continue
                prev_had_marker = m in txt
            else:
                if m in txt:
                    prev_had_marker = True
                    # Если перед маркером в предыдущем ране осталась одиночная «
                    if idx > 0 and (t_elements[idx - 1].text or "").endswith("«"):
                        # проверим, есть ли в следующих ранах ещё один такой же маркер
                        has_next_same = any(m in (n_el.text or "") for n_el in t_elements[idx + 1:idx + 4])
                        if has_next_same:
                            t_elements[idx - 1].text = (t_elements[idx - 1].text or "")[:-1]


def _highlight_markers_in_paragraph(p_el) -> None:
    """Разбивает <w:r>, содержащие маркеры незаполненных полей, и выделяет
    сами маркеры жёлтым фоном (<w:highlight w:val="yellow"/>)."""
    _collapse_adjacent_markers_in_paragraph(p_el)

    for r_el in list(p_el.findall(qn("w:r"))):
        t_els = r_el.findall(qn("w:t"))
        if len(t_els) != 1:
            # На случай если в одном ране несколько <w:t>
            full_r_text = "".join((t.text or "") for t in t_els)
            if any(m in full_r_text for m in _MARKERS):
                _add_yellow_highlight(r_el)
            continue

        t_el = t_els[0]
        txt = t_el.text or ""
        if not any(m in txt for m in _MARKERS):
            continue

        parts = _MARKER_SPLIT_RE.split(txt)
        if len(parts) == 1:
            continue

        # Если весь ран целиком состоит из маркера — просто подсвечиваем его
        if len(parts) == 3 and parts[0] == "" and parts[2] == "":
            _add_yellow_highlight(r_el)
            continue

        parent = r_el.getparent()
        insert_idx = parent.index(r_el)
        orig_rPr = r_el.find(qn("w:rPr"))

        for part in parts:
            if not part:
                continue
            new_r = OxmlElement("w:r")
            if orig_rPr is not None:
                new_r.append(copy.deepcopy(orig_rPr))
            new_t = OxmlElement("w:t")
            new_t.text = part
            new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            new_r.append(new_t)
            if part in _MARKERS:
                _add_yellow_highlight(new_r)
            parent.insert(insert_idx, new_r)
            insert_idx += 1

        parent.remove(r_el)


def highlight_missing_placeholders_in_doc(doc) -> None:
    """Обходит все параграфы документа (тело, таблицы, колонтитулы) и
    выделяет маркеры незаполненных переменных жёлтым цветом."""
    if doc is None:
        return
    roots = []
    if getattr(doc, "_element", None) is not None:
        roots.append(doc._element)
    for section in getattr(doc, "sections", ()):
        for hf_attr in ("header", "first_page_header", "even_page_header",
                        "footer", "first_page_footer", "even_page_footer"):
            hf = getattr(section, hf_attr, None)
            if hf is not None and getattr(hf, "_element", None) is not None:
                roots.append(hf._element)
    seen = set()
    for root in roots:
        for p_el in root.findall(".//" + qn("w:p")):
            pid = id(p_el)
            if pid not in seen:
                seen.add(pid)
                _highlight_markers_in_paragraph(p_el)


def render_docx(tpl, context: dict) -> None:
    """Единая точка рендера .docx — tpl.render(...) с подстановкой маркеров
    незаполненных полей и выделением их жёлтым цветом. Все места рендера
    документов обязаны звать эту функцию, а не tpl.render(context) напрямую
    (ПРАВИЛО №6)."""
    tpl.render(apply_blank_placeholders(context))
    highlight_missing_placeholders_in_doc(getattr(tpl, "docx", None))
