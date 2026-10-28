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

# ── Константы линий ──────────────────────────────────────────────────────
BLANK_DATE = "__.__.____"                   # полная дата
BLANK_NUMBER = "_____________________"      # номер/реестровый номер (21 "_")
BLANK_DAY = "__"                             # contract_date_day
BLANK_MONTH = "__________"                   # contract_date_month (месяц словом)
BLANK_YEAR = "____"                          # contract_date_year

# Три части разбитой даты договора печатаются по отдельности в шаблоне
# («{{ contract_date_day }}» {{ contract_date_month }} {{ contract_date_year }} г.) —
# у каждой части своя длина линии, общее правило "_date" их не покрывает.
_DATE_PART_BLANKS: dict[str, str] = {
    "contract_date_day": BLANK_DAY,
    "contract_date_month": BLANK_MONTH,
    "contract_date_year": BLANK_YEAR,
}

# Поля, которые по имени похожи на дату/номер, но не ими являются (служебные
# технические поля или составной формат, который линией "__.__.____"/
# "______" испортить легко) — не гасим.
_NEVER_BLANK: frozenset[str] = frozenset({
    "today", "today_iso",
})

# "_num" встречается и у денежных полей (contract_price_num, doc_amount_num,
# vat_amount_num) — это суммы цифрами, не номера документа; денежные поля
# правилом №6 этого модуля не трогаем.
_NUMBER_EXCLUDE_SUBSTRINGS: tuple[str, ...] = ("price", "amount")


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


def _is_date_key(key: str) -> bool:
    if key in _DATE_PART_BLANKS or key in _NEVER_BLANK:
        return False
    if key.endswith("_iso"):
        return False
    return key.endswith("_date") or "_date_" in key or key.startswith("date")


def _is_number_key(key: str) -> bool:
    if key == "num" or key in _NEVER_BLANK:
        return False
    if any(token in key for token in _NUMBER_EXCLUDE_SUBSTRINGS):
        return False
    return key.endswith("_number") or key.endswith("_num") or key.endswith("_no")


def _apply_to_flat_dict(data: dict) -> dict:
    """Возвращает НОВЫЙ dict — одноуровневая обработка полей."""
    out = dict(data)
    for key, value in list(out.items()):
        if key in _DATE_PART_BLANKS:
            if _is_empty(value):
                out[key] = Blank(_DATE_PART_BLANKS[key])
            continue
        if not _is_empty(value):
            continue
        if _is_date_key(key):
            out[key] = Blank(BLANK_DATE)
        elif _is_number_key(key):
            out[key] = Blank(BLANK_NUMBER)
    return out


# Ключи верхнего уровня, под которыми в context лежит список позиций — их
# элементы (dict) тоже проверяются на пустые даты/номера.
_LIST_KEYS: tuple[str, ...] = ("items", "items_list")


def apply_blank_placeholders(context: dict) -> dict:
    """Возвращает НОВЫЙ context: пустые даты/номера — объектами Blank().

    Исходный context не мутируется. Обрабатываются ключи верхнего уровня и,
    отдельно, элементы списков items/items_list (если это словари).
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


def render_docx(tpl, context: dict) -> None:
    """Единая точка рендера .docx — tpl.render(...) с применением гашения
    пустых дат/номеров. Все places рендера документов обязаны звать эту
    функцию, а не tpl.render(context) напрямую (ПРАВИЛО №6)."""
    tpl.render(apply_blank_placeholders(context))
