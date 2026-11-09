"""Утилиты для анализа альтернативных предложений (аналогов/эквивалентов), характеристик и дат.

ПРАВИЛО №5: компактный модуль (< 300 строк).
ПРАВИЛО №6: единый источник логики сопоставления аналогов и проверки характеристик.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def parse_ru_date(text: str) -> Optional[str]:
    """Разбирает русские даты в YYYY-MM-DD."""
    if not text:
        return None
    m_num = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m_num:
        return f"{m_num.group(3)}-{m_num.group(2)}-{m_num.group(1)}"
    m_text = re.search(r"[«\"']?\s*(\d{1,2})\s*[»\"']?\s*([а-яёА-ЯЁ]+)\s+(\d{4})", text)
    if m_text and m_text.group(2).lower() in RU_MONTHS:
        return f"{int(m_text.group(3)):04d}-{RU_MONTHS[m_text.group(2).lower()]:02d}-{int(m_text.group(1)):02d}"
    return None


def clean_str(val: Any) -> str:
    return "" if val is None else str(val).replace("\xa0", " ").strip()


def parse_num(val: Any) -> float:
    """Парсит число из строки или числа."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[-+]?\d*\.?\d+", clean_str(val).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    return float(m.group(0)) if m else 0.0


def detect_alternative(req_name: str, req_specs: str, off_name: str, off_specs: str) -> Tuple[bool, str]:
    """Определяет, является ли предложенный товар аналогом (эквивалентом)."""
    r_n, o_n, o_s = clean_str(req_name).lower(), clean_str(off_name).lower(), clean_str(off_specs).lower()
    if not o_n and not o_s:
        return False, ""
    for kw in ["аналог", "эквивалент", "замена", "вместо"]:
        if kw in o_n or kw in o_s:
            return True, "Указан аналог / эквивалент"
    if r_n and o_n:
        r_w, o_w = set(re.findall(r"[a-zа-яё0-9]{3,}", r_n)), set(re.findall(r"[a-zа-яё0-9]{3,}", o_n))
        if r_w and o_w and (len(r_w & o_w) / max(len(r_w), len(o_w)) < 0.35) and len(o_w - r_w) >= 1:
            return True, "Предложена иная модель / бренд"
    return False, ""


def build_rejection_reason_for_analogs(positions: List[Dict[str, Any]]) -> str:
    """Формирует текст причины отклонения заявки по отклонённым аналогам (п. 4, п. 6...)."""
    rejected = [p for p in positions if p.get("compliance_status") == "analog_rejected"]
    if not rejected:
        return ""
    pts, notes = [], []
    for p in rejected:
        p_num = p.get("item_num") or p.get("idx") or "?"
        pts.append(f"п. {p_num}")
        note = p.get("compliance_note", "").strip()
        if note:
            notes.append(f"п. {p_num}: {note}")
    base = f"Предложены аналоги, которые не соответствуют техническому заданию ({', '.join(pts)})"
    return f"{base}. Замечания: {'; '.join(notes)}" if notes else base


def canonicalize_characteristic_name(name: str) -> str:
    """Приводит синонимичные названия характеристик к единому каноническому виду."""
    n = clean_str(name).strip()
    if not n:
        return ""
    n_l = n.lower().replace("\xa0", " ")
    if any(k in n_l for k in ("масса", "вес")):
        return "Масса (вес)"
    if any(k in n_l for k in ("габарит", "размер", "дхшхв", "д×ш×в", "д*ш*в")):
        return "Габаритные размеры (Д×Ш×В)"
    if "мощность" in n_l:
        return "Мощность номинальная"
    if "напряжен" in n_l:
        return "Напряжение питания / выходное"
    if "шум" in n_l or "звук" in n_l:
        return "Уровень шума"
    if "бак" in n_l:
        return "Объем топливного бака"
    if "гарант" in n_l:
        return "Гарантийный срок"
    return n


def extract_default_exact_value(req_value: str) -> str:
    """Извлекает эталонное конкретное значение из формулировки ТЗ (без слов разброса)."""
    s = clean_str(req_value).replace("\xa0", " ").strip()
    if not s:
        return ""
    m_dims = re.search(r"\b\d+\s*[×x*хX]\s*\d+(?:\s*[×x*хX]\s*\d+)?\b", s)
    if m_dims:
        return m_dims.group(0).replace(" ", "")
    m_range = re.search(r"(?:от\s+)?([+-]?\d+(?:[.,]\d+)?)\s*(?:до|\.\.\.|…|[-—–])\s*([+-]?\d+(?:[.,]\d+)?)", s, re.IGNORECASE)
    if m_range and ("до" in s.lower() or "от" in s.lower() or "-" in s or "…" in s):
        return m_range.group(1).replace(",", ".")
    m_gte = re.search(r"(?:не\s+(?:менее|меньше|ниже)|>=|≥)\s*([+-]?\d+(?:[.,]\d+)?)", s, re.IGNORECASE)
    if m_gte:
        return m_gte.group(1).replace(",", ".")
    m_lte = re.search(r"(?:не\s+(?:более|больше|выше)|до|<=|≤)\s*([+-]?\d+(?:[.,]\d+)?)", s, re.IGNORECASE)
    if m_lte:
        return m_lte.group(1).replace(",", ".")
    cleaned = re.sub(r"^(?:не\s+(?:менее|более|меньше|больше|ниже|выше)|от|до|>=|<=|≥|≤)\s*", "", s, flags=re.IGNORECASE).strip()
    return cleaned


def extract_item_structured_chars(item: Any = None, tz_text: str = "") -> List[Dict[str, Any]]:
    """Извлекает структурированный список характеристик товара (ПРАВИЛО №6)."""
    from app.services.product_characteristics_parse import (
        clean_characteristic_name, normalize_characteristic_unit, _split_line, _KNOWN_UNITS_ALT,
    )
    chars: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(name: str, req_val: str, unit: str, ref_val: Optional[str] = None):
        n_c, v_c, u_c = canonicalize_characteristic_name(name or "").strip(), (req_val or "").strip(), (unit or "").strip()
        if n_c and v_c and n_c.lower() not in seen:
            seen.add(n_c.lower())
            ref_v = ref_val if (ref_val and not is_range_or_vague_value(ref_val)) else extract_default_exact_value(v_c)
            chars.append({"param_idx": len(chars) + 1, "name": n_c, "req_value": v_c, "unit": u_c, "ref_value": ref_v})

    raw_p = getattr(getattr(item, "product", None), "characteristics", None) or getattr(item, "characteristics", None)
    if raw_p:
        if isinstance(raw_p, str):
            try:
                import json
                raw_p = json.loads(raw_p)
            except Exception:
                raw_p = None
        if isinstance(raw_p, list):
            for c in raw_p:
                if isinstance(c, dict):
                    val_s = str(c.get("value") or "").strip()
                    _add(c.get("name") or "", val_s, c.get("unit") or "", val_s if not is_range_or_vague_value(val_s) else None)

    text = clean_str(tz_text)
    if text:
        for p in [p.strip() for p in re.split(r"[;\n\r]+", text) if p.strip()]:
            sp = _split_line(p)
            if sp:
                n_clean, u_name = clean_characteristic_name(sp[0])
                if n_clean:
                    m_u = re.search(rf"({_KNOWN_UNITS_ALT})\.?$", sp[1], re.IGNORECASE)
                    unit = (normalize_characteristic_unit(m_u.group(1)) if m_u else u_name) or ""
                    req_val = sp[1][:m_u.start()].strip().rstrip(".") if m_u else sp[1]
                    _add(n_clean, req_val, unit)
    return chars


def is_range_or_vague_value(val: str) -> bool:
    """Возвращает True, если значение содержит слова/символы разброса, неравенства или диапазона."""
    s = clean_str(val).replace("\xa0", " ").strip()
    if not s:
        return False
    s_l = s.lower()
    for kw in ("не менее", "не меньше", "не ниже", "не более", "не больше", "не выше", "не хуже", "или эквивалент", "или аналог", ">=", "<=", "≥", "≤", "±"):
        if kw in s_l:
            return True
    if any(sym in s for sym in (">", "<")):
        return True
    if re.search(r"(?:^|\s)от\s+[+-]?\d+(?:[.,]\d+)?\s*(?:до|[-–—…])\s*[+-]?\d+(?:[.,]\d+)?", s_l):
        return True
    if re.search(r"(?:^|\s)[+-]?\d+(?:[.,]\d+)?\s*до\s*[+-]?\d+(?:[.,]\d+)?", s_l):
        return True
    if re.search(r"\b\d+(?:[.,]\d+)?\s*[-–—…]\s*\d+(?:[.,]\d+)?\b", s):
        return True
    return False


def evaluate_characteristic_compliance(
    name: str,
    req_value: str,
    offered_value: str,
    unit: str = "",
    ref_value: str = "",
    is_exact_model_offer: bool = False,
) -> Dict[str, Any]:
    """Сравнивает предложенное значение характеристики с требованием ТЗ."""
    req_s, off_s = clean_str(req_value), clean_str(offered_value)
    ref_s = clean_str(ref_value) or extract_default_exact_value(req_s)
    u_sfx = f" {unit}".rstrip() if unit else ""

    # 1. Пустое предложенное значение недопустимо
    if not off_s:
        note = f"{name}: не указано конкретное значение (требуется {req_s}{u_sfx})".strip()
        return {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": "", "unit": unit, "compliant": False, "is_changed": True, "has_change": True, "note": note}

    # 2. Указание диапазона или размытого значения вместо конкретного параметра недопустимо
    if is_range_or_vague_value(off_s):
        note = f"{name}: указан диапазон/неопределённое значение «{off_s}» вместо конкретного параметра (требуется {req_s}{u_sfx})".strip()
        return {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": False, "is_changed": True, "has_change": True, "note": note}

    s_clean = req_s.replace("\xa0", " ").replace(",", ".").strip()
    m_range = re.search(r"(?:от\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:до|\.\.\.|…|[-—–])\s*([+-]?\d+(?:\.\d+)?)", s_clean, re.IGNORECASE)
    is_range = bool(m_range and ("до" in s_clean.lower() or "-" in s_clean or "…" in s_clean or ".." in s_clean))
    offered_num = parse_num(off_s)

    if is_range and m_range:
        v1, v2 = float(m_range.group(1)), float(m_range.group(2))
        min_v, max_v = min(v1, v2), max(v1, v2)
        ok = (min_v <= offered_num <= max_v)
        note = "" if ok else f"{name}: предложено {off_s}{u_sfx} (требуется {req_s}{u_sfx})".strip()
        res = {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": ok, "is_changed": True, "has_change": True, "note": note}
    elif (m_gte := re.search(r"(?:не\s+(?:менее|меньше|ниже)|от|>=|≥)\s*([+-]?\d+(?:\.\d+)?)", s_clean, re.IGNORECASE)):
        req_min = float(m_gte.group(1))
        ok = (offered_num >= req_min)
        note = "" if ok else f"{name}: предложено {off_s}{u_sfx} (требуется {req_s}{u_sfx})".strip()
        chg = (abs(offered_num - req_min) > 1e-6)
        res = {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": ok, "is_changed": chg, "has_change": chg, "note": note}
    elif (m_lte := re.search(r"(?:не\s+(?:более|больше|выше)|до|<=|≤)\s*([+-]?\d+(?:\.\d+)?)", s_clean, re.IGNORECASE)):
        req_max = float(m_lte.group(1))
        ok = (offered_num <= req_max)
        note = "" if ok else f"{name}: предложено {off_s}{u_sfx} (требуется {req_s}{u_sfx})".strip()
        chg = (abs(offered_num - req_max) > 1e-6)
        res = {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": ok, "is_changed": chg, "has_change": chg, "note": note}
    elif (m_exact := re.search(r"^[+-]?\d+(?:\.\d+)?$", s_clean)):
        ok = (abs(offered_num - float(m_exact.group(0))) <= 1e-6)
        note = "" if ok else f"{name}: предложено {off_s}{u_sfx} (требуется {req_s}{u_sfx})".strip()
        chg = not ok
        res = {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": ok, "is_changed": chg, "has_change": chg, "note": note}
    else:
        chg = (req_s.lower() != off_s.lower())
        res = {"name": name, "req_value": req_s, "ref_value": ref_s, "offered_value": off_s, "unit": unit, "compliant": True, "is_changed": chg, "has_change": chg, "note": ""}

    changed_from_ref = bool(ref_s and off_s.lower() != ref_s.lower())
    if is_exact_model_offer:
        if changed_from_ref or (not res["compliant"]):
            res["tz_corrected_by_supplier"] = True
            res["tz_correction_note"] = f"⚠️ Внимание (проверьте ТЗ): участник подтвердил поставку модели Заказчика, но скорректировал параметр «{name}»: указано «{off_s}»{u_sfx} (в ТЗ Заказчика: «{req_s}»{u_sfx}, эталон: «{ref_s or req_s}»{u_sfx})"
            if not res["compliant"]:
                res["needs_tz_review"] = True
    return res


def evaluate_position_characteristics(
    req_chars: List[Dict[str, Any]],
    offered_chars_or_map: Any,
    is_exact_model_offer: bool = False,
) -> Tuple[List[Dict[str, Any]], bool, bool, str, bool, List[str]]:
    """Сравнивает характеристики позиции и возвращает (evaluated, has_changes, all_compliant, notes_str, has_tz_correction, tz_correction_notes)."""
    off_map: Dict[str, str] = {}
    if isinstance(offered_chars_or_map, dict):
        for k, v in offered_chars_or_map.items():
            off_map[str(k).lower().strip()] = clean_str(v)
    elif isinstance(offered_chars_or_map, list):
        for idx, item in enumerate(offered_chars_or_map):
            if isinstance(item, dict):
                n, val = str(item.get("name") or "").lower().strip(), clean_str(item.get("offered_value") or item.get("value") or "")
                if n:
                    off_map[n] = val
                off_map[str(item.get("param_idx") or (idx + 1))] = val

    evaluated, has_changes, all_compliant, notes = [], False, True, []
    has_tz_correction = False
    tz_correction_notes: List[str] = []

    for idx, rc in enumerate(req_chars):
        p_idx = rc.get("param_idx") or (idx + 1)
        name = rc.get("name") or f"Параметр {p_idx}"
        req_val, unit = rc.get("req_value") or rc.get("value") or "", rc.get("unit") or ""
        ref_val = rc.get("ref_value") or extract_default_exact_value(req_val)
        off_val = off_map.get(name.lower().strip())
        if off_val is None:
            off_val = off_map.get(str(p_idx)) or rc.get("offered_value") or ""

        res = evaluate_characteristic_compliance(
            name, req_val, off_val, unit, ref_value=ref_val, is_exact_model_offer=is_exact_model_offer,
        )
        res["param_idx"] = p_idx
        evaluated.append(res)
        if res["is_changed"]:
            has_changes = True
        if res.get("tz_corrected_by_supplier"):
            has_tz_correction = True
            if res.get("tz_correction_note"):
                tz_correction_notes.append(res["tz_correction_note"])
        if not res["compliant"]:
            all_compliant = False
            if res.get("note"):
                notes.append(res["note"])

    return evaluated, has_changes, all_compliant, "; ".join(notes), has_tz_correction, tz_correction_notes
