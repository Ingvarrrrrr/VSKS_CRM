"""Приведение полного наименования организации (из ЕГРЮЛ, обычно КАПСОМ) к
обычному написанию для подстановки в документы — владелец, 27.10.2026.

НЕ путать с `app/services/vehicle_org_matching.py::normalize_org_name` — та
функция нормализует название для СРАВНЕНИЯ (поиск дублей), эта — для
ОТОБРАЖЕНИЯ в документе. Разные задачи, разные правила, имя дано другое
специально, чтобы не путать вызывающих (ПРАВИЛО №6: не второй источник того
же показателя — это другой показатель).

Правила (см. задачу владельца, 27.10.2026):
1. Регистр меняется ТОЛЬКО если во всей строке нет ни одной строчной буквы
   (целиком капс). Если есть хоть одна строчная — регистр не трогаем
   (кавычки всё равно конвертируются).
2. Прямые кавычки "…" парами → «…»; уже расставленные «» не трогаем.
3. Всё приводится к нижнему регистру; заглавная буква — у первого слова всей
   строки и у первого слова после каждой открывающей «.
4. Исключения (список слов/фраз в нужном написании — из карточки
   организации, `org_name_exceptions()`, плюс встроенные) ищутся без учёта
   регистра по границам слова (без `\\b` — он не всегда корректен на
   кириллице в питоновском `re`, используем `(?<!\\w)`/`(?!\\w)`),
   длинные фразы заменяются раньше коротких, заменяются на написание из
   списка — оно побеждает независимо от позиции в строке.
5. Встроенные исключения всегда в силе: РФ, ИНН, ОГРН. Слова с цифрами и
   римские цифры (I, II, III, IV…) регистр не меняют (остаются как в
   исходной строке).
"""
import re
from typing import List, Optional, Sequence

BUILTIN_EXCEPTIONS: List[str] = ["РФ", "ИНН", "ОГРН"]

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_ROMAN_TOKEN_RE = re.compile(r"^[IVXLCDMivxlcdm]+$")


def org_name_exceptions(org) -> List[str]:
    """Исключения из карточки организации (`organizations.doc_name_exceptions`)
    — по одной строке на слово/фразу, пустые строки и пробелы отбрасываются.
    `org=None` (нет организации / не привязана) → пустой список, встроенные
    исключения (РФ/ИНН/ОГРН) всё равно применяются внутри `doc_case_org_name`.
    """
    if org is None:
        return []
    raw = getattr(org, "doc_name_exceptions", None)
    if not raw:
        return []
    return [line.strip() for line in raw.split("\n") if line.strip()]


def _convert_quotes(text: str) -> str:
    """Прямые кавычки "…" парами → «…» (ёлочки). Уже стоящие « » не трогаем
    — мы заменяем только символ `"`, парами по порядку встречи."""
    if '"' not in text:
        return text
    parts = text.split('"')
    out = parts[0]
    for i in range(1, len(parts)):
        mark = "«" if i % 2 == 1 else "»"
        out += mark + parts[i]
    return out


def _has_lowercase(text: str) -> bool:
    return any(ch.islower() for ch in text)


def _lowercase_protecting_tokens(text: str) -> str:
    """Нижний регистр для всей строки, КРОМЕ слов с цифрами и римских цифр
    (I, II, III, IV…) — те остаются как в исходной (капс) строке."""

    def _repl(m: "re.Match[str]") -> str:
        tok = m.group(0)
        if any(ch.isdigit() for ch in tok):
            return tok
        if _ROMAN_TOKEN_RE.match(tok):
            return tok
        return tok.lower()

    return _WORD_RE.sub(_repl, text)


def _capitalize_letter_from(chars: List[str], start: int) -> None:
    """Заглавная буква у первого буквенного символа начиная с `start`,
    пропуская пробелы/кавычки перед ним (мутирует `chars` на месте)."""
    for i in range(start, len(chars)):
        ch = chars[i]
        if ch.isalpha():
            chars[i] = ch.upper()
            return
        if ch.isspace() or ch in ("«", "»", '"', "“", "‘"):
            continue
        return


def _capitalize_sentence_starts(text: str) -> str:
    chars = list(text)
    _capitalize_letter_from(chars, 0)
    for i, ch in enumerate(text):
        if ch == "«":
            _capitalize_letter_from(chars, i + 1)
    return "".join(chars)


def _apply_exceptions(text: str, exceptions: Sequence[str]) -> str:
    cleaned = sorted({e.strip() for e in exceptions if e and e.strip()}, key=len, reverse=True)
    for exc in cleaned:
        pattern = re.compile(r"(?<!\w)" + re.escape(exc) + r"(?!\w)", re.IGNORECASE | re.UNICODE)
        text = pattern.sub(lambda m, _exc=exc: _exc, text)
    return text


def doc_case_org_name(name: Optional[str], exceptions: Optional[Sequence[str]] = None) -> str:
    """Привести полное/краткое наименование организации к обычному
    написанию для документа — см. правила 1-5 в докстринге модуля."""
    if not name:
        return name or ""
    text = _convert_quotes(name)
    if _has_lowercase(text):
        # Правило 1: регистр не трогаем, но кавычки уже сконвертированы выше.
        return text
    all_exceptions = list(BUILTIN_EXCEPTIONS) + list(exceptions or [])
    lowered = _lowercase_protecting_tokens(text)
    capitalized = _capitalize_sentence_starts(lowered)
    return _apply_exceptions(capitalized, all_exceptions)


def doc_quotes_only(name: Optional[str]) -> str:
    """Только конвертация кавычек, регистр не меняется — для краткого
    наименования (customer_short_name/contractor_short_name и их падежей),
    которое в карточке и так пишется нормальным регистром."""
    if not name:
        return name or ""
    return _convert_quotes(name)


_CASE_FUNC_NAMES = {"gent": "_to_gen_org_name", "datv": "_to_dat_org_name", "ablt": "_to_ablt_org_name"}


def doc_case_org_name_case(
    name: Optional[str], exceptions: Optional[Sequence[str]], case: str
) -> str:
    """`doc_case_org_name` + склонение в падеж *case* ('gent'/'datv'/'ablt')
    через существующие `_to_gen_org_name`/`_to_dat_org_name`/`_to_ablt_org_name`
    (contexts_org_people.py, ПРАВИЛО №6 — второй алгоритм склонения не
    заводим). Порядок: нормализовать регистр → склонить → снова применить
    исключения (склонение головной группы теоретически может задеть
    исключение, если оно и есть голова фразы) → заглавная первая буква."""
    if not name:
        return name or ""
    if case not in _CASE_FUNC_NAMES:
        raise ValueError(f"Неизвестный падеж: {case!r} (ожидается 'gent'/'datv'/'ablt')")
    # Локальный импорт — contexts_org_people.py не импортирует org_name_case.py,
    # но избегаем цикла на случай будущей правки порядка импортов в пакете documents.
    from app.services.documents.contexts_org_people import (
        _to_gen_org_name, _to_dat_org_name, _to_ablt_org_name,
    )
    case_fn = {"gent": _to_gen_org_name, "datv": _to_dat_org_name, "ablt": _to_ablt_org_name}[case]

    normalized = doc_case_org_name(name, exceptions)
    declined = case_fn(normalized)
    all_exceptions = list(BUILTIN_EXCEPTIONS) + list(exceptions or [])
    result = _apply_exceptions(declined, all_exceptions)
    chars = list(result)
    _capitalize_letter_from(chars, 0)
    return "".join(chars)
