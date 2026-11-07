"""Утилиты для анализа альтернативных предложений (аналогов/эквивалентов) и дат.

ПРАВИЛО №5: компактный модуль (< 200 строк).
ПРАВИЛО №6: единый источник логики сопоставления аналогов.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def parse_ru_date(text: str) -> Optional[str]:
    """Разбирает русские даты вида «12» мая 2026 г., 14 августа 2025, 05.08.2025 в YYYY-MM-DD."""
    if not text:
        return None
    m_num = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m_num:
        return f"{m_num.group(3)}-{m_num.group(2)}-{m_num.group(1)}"
    m_text = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})", text)
    if m_text:
        day = int(m_text.group(1))
        month = RU_MONTHS.get(m_text.group(2).lower())
        year = int(m_text.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).replace("\xa0", " ").strip()


def parse_num(val: Any) -> float:
    """Парсит число из строки или числа (убирая пробелы и запятые)."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = clean_str(val).replace(" ", "").replace("\u00a0", "").replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return 0.0
    return 0.0


def detect_alternative(req_name: str, req_specs: str, off_name: str, off_specs: str) -> Tuple[bool, str]:
    """Определяет, является ли предложенный товар аналогом (эквивалентом)."""
    r_n = clean_str(req_name).lower()
    o_n = clean_str(off_name).lower()
    o_s = clean_str(off_specs).lower()

    if not o_n and not o_s:
        return False, ""

    # Явные маркеры аналога в тексте
    for kw in ["аналог", "эквивалент", "замена", "вместо"]:
        if kw in o_n or kw in o_s:
            return True, "Указан аналог / эквивалент"

    # Если названия существенно отличаются
    if r_n and o_n:
        def tokenize(s: str) -> set:
            return set(re.findall(r"[a-zа-яё0-9]{3,}", s))

        r_words = tokenize(r_n)
        o_words = tokenize(o_n)
        if r_words and o_words:
            overlap = len(r_words & o_words) / max(len(r_words), len(o_words))
            if overlap < 0.35 and len(o_words - r_words) >= 1:
                return True, "Предложена иная модель / бренд"

    return False, ""


def build_rejection_reason_for_analogs(positions: List[Dict[str, Any]]) -> str:
    """Формирует текст причины отклонения заявки по отклонённым аналогам (п. 4, п. 6...)."""
    rejected = [p for p in positions if p.get("compliance_status") == "analog_rejected"]
    if not rejected:
        return ""
    pts: List[str] = []
    notes: List[str] = []
    for p in rejected:
        p_num = p.get("item_num") or p.get("idx") or "?"
        pts.append(f"п. {p_num}")
        note = p.get("compliance_note", "").strip()
        if note:
            notes.append(f"п. {p_num}: {note}")
    base = f"Предложены аналоги, которые не соответствуют техническому заданию ({', '.join(pts)})"
    if notes:
        base += f". Замечания: {'; '.join(notes)}"
    return base
