"""Разбор текста, вставленного пользователем из карточки товара на сайте
поставщика, в список характеристик [{"name","value","unit"}] (владелец,
задача «заполнить характеристики копированием с сайта», 26.10.2026).

Доп. формат «Метка - значение» (дефис/тире, 27.10.2026, задача «нет данных —
заполняются из описания», товар 3002 с прода): добавлен ТОЛЬКО этот модуль
(ПРАВИЛО №6) — fallback из description в генераторе ТЗ 44-ФЗ
(app/services/product_tz_44fz_multiline.py) переиспользует _split_line
ОТСЮДА построчно, второго места с таким же разбором нет.

ЕДИНСТВЕННОЕ место этого разбора (ПРАВИЛО №6) — вызывается из
app/routers/products_characteristics.py (POST /characteristics/parse),
второй такой парсер не писать.

Переиспользование app/services/product_tz_44fz_multiline.py: там есть
похожая по смыслу функция `_parse_description_fallback` (и её внутренности
`_parse_pairs`/`_is_valid_label`/`_FALLBACK_LINE_RE`), но ВСЕ они с
ведущим подчёркиванием — приватные символы модуля, предназначенные только
для внутреннего использования app/services/product_tz_44fz.py (единственный
импортёр, см. grep). Этот модуль сейчас активно правит соседняя сессия
(файл в списке «не трогать» в задании) — тянуть оттуда приватные имена
означало бы: (а) нарушить соглашение о приватности формальным импортом
"_private_name" из чужого модуля, (б) создать скрытую связь с файлом, который
прямо сейчас меняется параллельно. Их алгоритм к тому же настроен на другую
задачу — очистку ТЗ 44-ФЗ от брендов/допусков с эвристикой "похоже на
заголовок группы", а не на разбор ЧЕТЫРЁХ явных форматов вставки (двоеточие/
таб/точки-разделитель/чередование), которые нужны здесь. Поэтому формат
разбора реализован самостоятельно, независимым и более простым набором
регулярок (см. ниже) — дублирования алгоритма тз-44фз здесь нет.
"""
import re
from typing import Optional

MAX_TEXT_LENGTH = 50_000

_TAB_LINE_RE = re.compile(r"^(.+?)\t+(.+)$")
_COLON_LINE_RE = re.compile(r"^([^:\n]{1,200}):\s*(.+)$")
# "Метка - значение" / "Метка — значение" / "Метка – значение" — дефис/тире,
# ОКРУЖЁННЫЙ пробелами с обеих сторон (иначе это дефис внутри слова
# "литий-ионный" или диапазон "108-112" без пробелов — не разделитель).
# Метка короткая (<=60) и с заглавной буквы — защита от абзацев текста, где
# " - " может встретиться случайно как часть обычного предложения.
_DASH_LINE_RE = re.compile(r"^(.{1,60}?)\s+[-—–]\s+(\S.*)$")
# "Метка ..... значение" / "Метка    значение" — метка и значение разделены
# либо повтором точек (2+), либо пробегом из 2+ пробелов.
_DOTS_OR_SPACES_LINE_RE = re.compile(r"^(.{1,200}?)(?:\.{2,}|\s{2,})\s*(\S.*)$")


def _is_dash_label(label: str) -> bool:
    """Метка формата "Метка - значение" — короткая строка с заглавной
    буквы (не длинный абзац, где " - " случайное совпадение)."""
    s = (label or "").strip()
    return bool(s) and len(s) <= 60 and s[0].isupper()

# "2786 г" / "1.5 л" / "220 В" — число (точка/запятая как разделитель
# дробной части) + единица измерения через пробел.
_NUMBER_UNIT_RE = re.compile(
    r"^(-?\d+(?:[.,]\d+)?)\s+([^\d\s][^\n]*)$"
)


def _split_line(line: str) -> Optional[tuple]:
    """Пробует разбить ОДНУ строку на (метка, значение) одним из ЧЕТЫРЁХ
    форматов «в строке», в порядке однозначности: таб → двоеточие → дефис/
    тире (короткая метка с заглавной) → точки/пробелы-разделитель. Дефис
    проверяется ДО общего разделителя "2+ пробела", иначе "Метка  - значение"
    (два пробела перед дефисом) перехватывается менее точным правилом и
    отрезает дефис в значение. Возвращает None, если ни один не подошёл."""
    m = _TAB_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value:
            return label, value
    m = _COLON_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value:
            return label, value
    m = _DASH_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value and _is_dash_label(label):
            return label, value
    m = _DOTS_OR_SPACES_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip().rstrip(".").strip(), m.group(2).strip()
        if label and value:
            return label, value
    return None


def _separate_unit(value: str) -> tuple:
    """"2786 г" → ("2786", "г"); если значение не «число + единица» —
    возвращает (value, None) без изменений."""
    m = _NUMBER_UNIT_RE.match(value.strip())
    if not m:
        return value, None
    number, rest = m.group(1).strip(), m.group(2).strip()
    # "x"/"×" внутри остатка — это составное значение вроде "31.5 x 11.5 x 11 см"
    # (габариты), не "число + единица"; не разделяем такие.
    if re.search(r"[x×]", rest, re.IGNORECASE):
        return value, None
    # Единица — короткое слово/аббревиатура без пробелов внутри (иначе это,
    # скорее всего, не единица, а продолжение текстового значения).
    if " " in rest or len(rest) > 20:
        return value, None
    return number, rest


def parse_pasted_characteristics(text: str) -> list:
    """Разбирает вставленный текст в список характеристик. Пустой/пробельный
    текст → []. Поддерживает «Метка: значение», «Метка\\tзначение», «Метка -
    значение» (дефис/тире), «Метка ..... значение» (построчно) и, если
    построчный разбор не дал результата хотя бы на половине строк,
    чередующиеся строки метка/значение."""
    if not text or not text.strip():
        return []

    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not raw_lines:
        return []

    pairs: list = []
    unresolved = 0
    for line in raw_lines:
        parsed = _split_line(line)
        if parsed:
            pairs.append(parsed)
        else:
            unresolved += 1

    # Построчный разбор не справился (меньше половины строк дали пару) —
    # пробуем чередующиеся строки метка/значение (нечётные/чётные).
    if not pairs or unresolved > len(raw_lines) / 2:
        if len(raw_lines) >= 2 and len(raw_lines) % 2 == 0:
            alt_pairs = []
            ok = True
            for i in range(0, len(raw_lines), 2):
                label, value = raw_lines[i].strip(), raw_lines[i + 1].strip()
                if not label or not value:
                    ok = False
                    break
                alt_pairs.append((label, value))
            if ok and alt_pairs:
                pairs = alt_pairs

    items = []
    seen = set()
    for label, value in pairs:
        label = label.strip()
        value = value.strip()
        if not label or not value:
            continue
        key = (label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        value_part, unit_part = _separate_unit(value)
        items.append({"name": label, "value": value_part, "unit": unit_part})
    return items
