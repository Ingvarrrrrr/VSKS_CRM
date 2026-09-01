"""
vehicle_org_matching — сопоставление организации-собственника/эксплуатанта
транспорта из текста реестра (Excel) с организациями в БД.

Контекст (жалоба владельца, 2026-08-31): реестр Голичкова содержит колонки
«Собственник» / «ИНН собственника» / «У кого в эксплуатации» / «ИНН
эксплуатант». Раньше ИНН-колонки не читались вовсе, а сопоставление
владельца по названию не выполнялось на этапе preview — организация
подставлялась только если совпадало ровно (регистронезависимо) полное имя,
а любое расхождение тихо приводило к ошибке/пропуску строки на commit.

Приоритет сопоставления (см. задание): 1) точный ИНН после нормализации,
2) точное совпадение нормализованного названия. Всё, что не сопоставилось —
возвращается вызывающей стороне для ручного выбора (как уже сделано для
unmapped_regions) — НИКОГДА не подставляется тихая организация по умолчанию.

Единственный источник этой логики — не дублировать в other модулях. Роутер
app/routers/vehicles_import.py импортирует функции отсюда и для owner_text,
и для assigned_text (симметрично).
"""
import re
from typing import Any, Dict, Iterable, Optional, Tuple

# ── ИНН ────────────────────────────────────────────────────────────────────


def normalize_inn(raw: Any) -> Optional[str]:
    """Нормализует значение ИНН в канонический вид (10 или 12 цифр).

    Обрабатывает:
      - пробелы/дефисы внутри строки ("930 402 2845" → "9304022845");
      - число с плавающей точкой из openpyxl ("9304022845.0" → "9304022845");
      - потерю ведущего нуля при чтении Excel как числа (9-значный остаток
        от 10-значного ИНН → zfill(10); 11-значный остаток от 12-значного —
        zfill(12)).

    Возвращает None, если после очистки получилось не 10 и не 12 цифр
    (мусор/не-ИНН значение) — вызывающая сторона не должна пытаться матчить
    по такому значению.
    """
    if raw is None:
        return None
    if isinstance(raw, float):
        if raw != raw:  # NaN
            return None
        if raw.is_integer():
            raw = int(raw)
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"[^0-9]", "", s)
    if not s:
        return None
    if len(s) == 9:
        s = s.zfill(10)
    elif len(s) == 11:
        s = s.zfill(12)
    if len(s) not in (10, 12):
        return None
    return s


# ── Название организации ────────────────────────────────────────────────────

# Организационно-правовые формы — снимаются как отдельные токены (не частичные
# подстроки), чтобы не портить содержательные слова ("Донецкое РЕГИОНАЛЬНОЕ
# ОТДЕЛЕНИЕ" — не трогаем, это не ОПФ, а часть официального названия).
_LEGAL_FORM_TOKENS = {
    "ооо", "оао", "зао", "пао", "ао", "нко", "ано", "фгуп", "гуп", "муп", "чуп",
    "фгбу", "гбу", "мбу", "гку", "мку", "нп", "снт", "тсж", "ип", "пк", "кфх",
    "ooo", "oao", "zao", "pao",
}

_RE_WS = re.compile(r"\s+")
_RE_QUOTES = re.compile(r"[«»\"'`“”„]")
_RE_PUNCT_EDGE = re.compile(r"^[\s.,;:\-]+|[\s.,;:\-]+$")


def normalize_org_name(raw: Any) -> str:
    """lower + убрать кавычки/лишние пробелы + убрать токены ОПФ.

    Не делает нечёткого/частичного сопоставления (см. lesson
    feedback_dedup_exact_only) — только точная нормализация перед точным
    сравнением строк.
    """
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = _RE_QUOTES.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split(" ") if t and t not in _LEGAL_FORM_TOKENS]
    return " ".join(tokens).strip()


# ── Индексы организаций ─────────────────────────────────────────────────────

OrgRow = Tuple[int, Optional[str], Optional[str]]  # (id, name, inn)


def build_inn_index(orgs: Iterable[OrgRow]) -> Dict[str, int]:
    """{нормализованный ИНН → org_id}. Первое вхождение побеждает при дублях."""
    idx: Dict[str, int] = {}
    for oid, _name, inn in orgs:
        n = normalize_inn(inn)
        if n and n not in idx:
            idx[n] = oid
    return idx


def build_name_index(orgs: Iterable[OrgRow]) -> Dict[str, int]:
    """{нормализованное название → org_id}. Первое вхождение побеждает при дублях."""
    idx: Dict[str, int] = {}
    for oid, name, _inn in orgs:
        n = normalize_org_name(name)
        if n and n not in idx:
            idx[n] = oid
    return idx


# ── Точка входа для сопоставления одной строки ─────────────────────────────

def resolve_org_for_text(
    text_val: Optional[str],
    inn_val: Any,
    inn_index: Dict[str, int],
    name_index: Dict[str, int],
) -> Tuple[Optional[int], Optional[str]]:
    """Возвращает (org_id, method), method in {"inn", "name", None}.

    ИНН — приоритетный ключ (точнее названия, не страдает от сокращений).
    Если ИНН не задан/не нашёлся — пробуем нормализованное название.
    Если ничего не подошло — (None, None): вызывающая сторона обязана
    отправить эту строку в список для ручного сопоставления, а НЕ подставлять
    организацию по умолчанию молча.
    """
    inn = normalize_inn(inn_val)
    if inn and inn in inn_index:
        return inn_index[inn], "inn"

    name = normalize_org_name(text_val)
    if name and name in name_index:
        return name_index[name], "name"

    return None, None
