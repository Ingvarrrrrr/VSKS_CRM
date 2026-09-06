"""Форматирование дат/денег/ФИО и числа прописью для шаблонов документов.

Без зависимостей от остальных services/documents/* — только stdlib."""


import re
from datetime import date
from decimal import Decimal
from typing import Optional


def _fmt_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d
    return d.strftime("%d.%m.%Y")


def _clean_id(v) -> str:
    """Strip trailing .0 from INN/KPP imported as float strings."""
    if not v:
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def _fmt_money(v) -> str:
    if v is None:
        return ""
    return f"{float(v):,.2f}".replace(",", " ").replace(".", ",")


# Money without currency symbol, with space thousand separator, comma decimal —
# byte-identical to _fmt_money (Правило №6): kept as an alias, not a copy.
_fmt_money_plain = _fmt_money


def _merge_identical_items(items):
    """Склеивает позиции, у которых совпадает всё, кроме категории ФЭО.

    Возвращает список кортежей (representative_item, merged_quantity, merged_total_price)
    в порядке первого появления. Цена за единицу в группе одна и та же, поэтому
    суммы документа склейка не меняет.
    """
    groups: dict = {}
    order: list = []
    for item in items or []:
        # feo_category_id/feo_planned_item_id намеренно не входят в ключ — по ним и склеиваем
        key = (
            item.product_id,
            (item.item_name or "").strip().lower(),
            (item.item_type or ""),
            (item.unit or ""),
            str(item.unit_price) if item.unit_price is not None else "",
            (item.country_origin or ""),
            (getattr(item, "vat_rate", None) or ""),
        )
        if key not in groups:
            groups[key] = [item, None, None]  # [representative, quantity, total_price]
            order.append(key)
        g = groups[key]
        if item.quantity is not None:
            g[1] = (g[1] if g[1] is not None else Decimal("0")) + Decimal(str(item.quantity))
        if item.total_price is not None:
            g[2] = (g[2] if g[2] is not None else Decimal("0")) + Decimal(str(item.total_price))
    return [tuple(groups[key]) for key in order]


# Signatory position: extract from signatory field if "Директор ФИО" format
def _signatory_position(signatory: str) -> str:
    if not signatory:
        return ""
    parts = signatory.strip().split()
    if len(parts) > 1 and not parts[0][0].isupper():
        return parts[0]
    return "Директор"


# Phase 23: helpers for signatory formatting — used by both paths of _signatory_split

def _fio_to_genitive(name_full: str) -> str:
    """Rough genitive form of a full name: Козеев Евгений Викторович → Козеева Евгения Викторовича."""
    def _word(w: str) -> str:
        if w.endswith("ич"):  # Иванович → Ивановича
            return w + "а"
        if w.endswith("ий"):  # Евгений → Евгения
            return w[:-2] + "ия"
        if w.endswith("ья"):  # Илья → Ильи
            return w[:-2] + "ьи"
        if w.endswith("а") and len(w) > 2:
            return w[:-1] + "ы"
        # Last consonant cluster: add -а
        vowels = set("аеёиоуыьъэюяАЕЁИОУЫЭЮЯ")
        if w and w[-1] not in vowels and w[-1] not in "ьъ":
            return w + "а"
        return w  # fallback: as-is
    return " ".join(_word(w) for w in name_full.split()) if name_full else name_full


# B-dedup: формат ФИО → инициалы (используется для «Ответственного исполнителя»).
# "Иванова Ирина Владиславовна"   → "Иванова И.В."
# "Кулиев Гасан Валех оглы"        → "Кулиев Г.В." (4-я часть отбрасывается)
# "Иванова-Петрова Анна Сергеевна" → "Иванова-Петрова А.С." (дефис = одна фамилия)
# Phase (2026-09-01): вынесена из-под generate_document на уровень модуля —
# была локальным замыканием без обращений к внешним переменным, extraction
# не меняет поведение и даёт tests/test_responsible_person_persist.py
# прямой доступ к функции, не дублируя алгоритм в тесте.
def _format_initials(full: str) -> str:
    if not full:
        return ""
    parts = (full or "").strip().split()
    if not parts:
        return ""
    surname = parts[0]
    initials = []
    for p_word in parts[1:3]:  # только имя + отчество (3-я часть «оглы»/«кызы» отбрасывается)
        if p_word and p_word[0].isalpha():
            initials.append(p_word[0].upper() + ".")
    return f"{surname} {''.join(initials)}".strip()


_INITIALS_WORD_RE = re.compile(r'^([A-Za-zА-Яа-яЁё]\.){1,2}$')


def _format_initials_safe(full: str) -> str:
    """Сократить ФИО до «Фамилия И.О.», не ломая то, что сокращать не нужно.

    В отличие от `_format_initials`, эта обёртка ИДЕМПОТЕНТНА и не трогает
    строки, для которых сокращение не имеет смысла или уже выполнено.
    Нужна потому, что `_format_initials` слепо берёт первую букву 2-го и
    3-го «слова» — если на вход уже подать сокращённое имя, оно портится:

        _format_initials("Иванов И.В.")  → "Иванов И."   # ⚠ отчество потеряно!

    А ровно такой путь реален: для роли «Ответственный исполнитель»
    (см. resolved_responsible выше) в `full_name` подставляется значение,
    которое УЖЕ прошло через `_format_initials`. Повторное сокращение в
    approvers_list не должно откусывать инициал отчества.

    Правила:
    - пустая строка / только пробелы → "" (как и `_format_initials`);
    - строка без единой буквы (плейсхолдер вида «_________________»,
      «RESPONSIBLE_PLACEHOLDER») → возвращается как есть, без изменений;
    - уже сокращённая форма — все слова, кроме первого, выглядят как
      инициалы (1-2 буквы с точкой на конце, например «И.», «И.О.», «В.»)
      → возвращается как есть, повторно не сокращается;
    - иначе — обычное полное ФИО → применяется `_format_initials`.

    Примеры:
        _format_initials_safe("Маркодеева Анастасия Олеговна") → "Маркодеева А.О."
        _format_initials_safe("Борисов Александр Алексеевич")  → "Борисов А.А."
        _format_initials_safe("Иванов И.В.")                   → "Иванов И.В." (без изменений)
        _format_initials_safe("Иванов И.")                     → "Иванов И." (без изменений)
        _format_initials_safe("_________________")             → "_________________" (без изменений)
        _format_initials_safe("")                               → ""
        _format_initials_safe("Иванов")                         → "Иванов"
    """
    if not full:
        return ""
    stripped = full.strip()
    if not stripped:
        return ""
    if not any(ch.isalpha() for ch in stripped):
        # Плейсхолдер без единой буквы (подчёркивания и т.п.) — не трогаем.
        return full
    parts = stripped.split()
    if len(parts) > 1 and all(_INITIALS_WORD_RE.match(w) for w in parts[1:]):
        # Уже в сокращённой форме «Фамилия И.О.» — повторное сокращение
        # откусило бы инициал отчества, поэтому возвращаем как есть.
        return full
    return _format_initials(full)


def _resolve_responsible_person_update(current_value: Optional[str], responsible_name: Optional[str]) -> Optional[str]:
    """Куда писать пришедший ?responsible_name= в Purchase.responsible_person.

    Владелец: «из листа согласования договора почему-то самовольно исчез
    ответственный исполнитель, хотя был определён» — выбор в диалоге
    формирования документа раньше уходил только разовым query-параметром и
    нигде не сохранялся, поэтому при следующей генерации подставлялся
    другой человек. Теперь непустой параметр запоминается.

    Возвращает новое значение для записи в БД, либо None если писать не
    нужно: параметр пуст (пустой параметр НЕ должен затирать уже сохранённое
    имя) или совпадает с уже сохранённым (не гонять лишний commit).
    Чистая функция — вынесена отдельно ради юнит-теста без живой сессии
    (см. tests/test_responsible_person_persist.py).
    """
    if not responsible_name or not responsible_name.strip():
        return None
    new_value = responsible_name.strip()
    if new_value == (current_value or ""):
        return None
    return new_value


def _fio_to_initials(name_full: str) -> str:
    """Return "Фамилия И.О." form; falls back to name_full when < 2 words."""
    words = name_full.split() if name_full else []
    if len(words) >= 3:
        return f"{words[0]} {words[1][0]}.{words[2][0]}."
    if len(words) == 2:
        return f"{words[0]} {words[1][0]}."
    return name_full


def _fio_to_initials_prefix(name_full: str) -> str:
    """Return "И.О. Фамилия" form (инициалы впереди — для строки подписи).
    Falls back to name_full when < 2 words."""
    words = name_full.split() if name_full else []
    if len(words) >= 3:
        return f"{words[1][0]}.{words[2][0]}. {words[0]}"
    if len(words) == 2:
        return f"{words[1][0]}. {words[0]}"
    return name_full


_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят",
         "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_ONES_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
           "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
           "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]


def _chunk_to_words(n: int, feminine: bool = False) -> str:
    parts = []
    h = n // 100
    r = n % 100
    t = r // 10
    o = r % 10
    if h:
        parts.append(_HUNDREDS[h])
    if r < 20:
        w = (_ONES_F[r] if feminine else _ONES[r])
        if w:
            parts.append(w)
    else:
        if t:
            parts.append(_TENS[t])
        w = (_ONES_F[o] if feminine else _ONES[o])
        if w:
            parts.append(w)
    return " ".join(parts)


def _rubles_to_words(amount) -> str:
    """Convert numeric amount to Russian words (рублей XX копеек)."""
    if amount is None:
        return ""
    try:
        val = round(float(amount), 2)
    except (TypeError, ValueError):
        return ""
    rubles = int(val)
    kopecks = round((val - rubles) * 100)
    billions = rubles // 1_000_000_000
    millions = (rubles % 1_000_000_000) // 1_000_000
    thousands = (rubles % 1_000_000) // 1_000
    rest = rubles % 1_000

    parts = []
    if billions:
        w = _chunk_to_words(billions)
        if w:
            parts.append(w)
        if billions % 10 == 1 and billions % 100 != 11:
            parts.append("миллиард")
        elif 2 <= billions % 10 <= 4 and not (11 <= billions % 100 <= 14):
            parts.append("миллиарда")
        else:
            parts.append("миллиардов")
    if millions:
        w = _chunk_to_words(millions)
        if w:
            parts.append(w)
        if millions % 10 == 1 and millions % 100 != 11:
            parts.append("миллион")
        elif 2 <= millions % 10 <= 4 and not (11 <= millions % 100 <= 14):
            parts.append("миллиона")
        else:
            parts.append("миллионов")
    if thousands:
        w = _chunk_to_words(thousands, feminine=True)
        if w:
            parts.append(w)
        if thousands % 10 == 1 and thousands % 100 != 11:
            parts.append("тысяча")
        elif 2 <= thousands % 10 <= 4 and not (11 <= thousands % 100 <= 14):
            parts.append("тысячи")
        else:
            parts.append("тысяч")
    if rest or not parts:
        w = _chunk_to_words(rest, feminine=True)
        if w:
            parts.append(w)
    if rubles == 0:
        parts = ["ноль"]

    # Ruble ending
    r10 = rubles % 10
    r100 = rubles % 100
    if r10 == 1 and r100 != 11:
        rub_word = "рубль"
    elif 2 <= r10 <= 4 and not (11 <= r100 <= 14):
        rub_word = "рубля"
    else:
        rub_word = "рублей"

    parts.append(rub_word)
    parts.append(f"{kopecks:02d}")
    k10 = kopecks % 10
    k100 = kopecks % 100
    if k10 == 1 and k100 != 11:
        parts.append("копейка")
    elif 2 <= k10 <= 4 and not (11 <= k100 <= 14):
        parts.append("копейки")
    else:
        parts.append("копеек")

    return " ".join(parts)
