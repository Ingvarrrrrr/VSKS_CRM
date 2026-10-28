"""Единый источник сборки/разбора адреса по частям (ПРАВИЛО №6).

Используется карточкой организации/контрагента (юр. адрес, хранится одной
строкой в `contractors.address`, но редактируется по частям — почтовый
индекс/регион/район-городской округ/населённый пункт/улица/дом/корпус/офис).

Бага владельца (28.10.2026): разбор строки адреса из ЕГРЮЛ/DaData для
Запорожской области вместо «г.о. Бердянск» давал огрызок «о.Бердянск» —
регэксп, ищущий префикс города «г.», не умел отличать его от сокращения
«г.о.» (городской округ) и срезал «г.», оставляя «о.Бердянск»/«о. Бердянск».

`extract_settlement_name()` ниже — ЕДИНСТВЕННОЕ место, которое отличает
«г.» (город) от «г.о.» (городской округ): и разбор адреса на части (`parse_address`
в этом модуле), и {{customer_city}}/{{contractor_city}} в документах
(app/services/documents/formatting.py::_extract_city_from_address — делегирует
сюда) используют ровно эту функцию. Не писать новый регэксп на «г./г.о.» ещё
где-то — звать эту функцию.
"""
import re

from app.services.region_from_text import find_region_in_text

__all__ = [
    "ADDRESS_PART_KEYS",
    "compose_address",
    "parse_address",
    "extract_settlement_name",
]

# Порядок частей — как в compose_address() и как в parse_address().
ADDRESS_PART_KEYS = (
    "postal_code",
    "region",
    "district",
    "settlement_type",
    "settlement",
    "street",
    "house",
    "building",
    "office",
)

# --- Распознавание населённого пункта -------------------------------------
# «г.» / «г » + имя до запятой, НО не «г.о.» (городской округ) — именно тот
# фрагмент, который раньше и давал «о.Бердянск» вместо «Бердянск».
_G_PREFIX_RE = re.compile(r'(?:^|,)\s*г(?:\.\s*|\s+)(?!о\.)([^,]+?)\s*(?:,|$)', re.IGNORECASE)
_CITY_WORD_RE = re.compile(r'(?:^|,)\s*город\s+([^,]+?)\s*(?:,|$)', re.IGNORECASE)
_FEDERAL_CITIES = ("Москва", "Санкт-Петербург", "Севастополь")

# Городской/муниципальный округ — «г.о. X», «г. о. X», «городской округ X»,
# «муниципальный округ X». Используется и как фолбэк для населённого пункта
# (когда в адресе нет отдельной строки «г. X» — сам округ назван по городу,
# как «г.о. Бердянск»), и как источник для поля district в parse_address().
_OKRUG_RE = re.compile(
    r'(?:^|,)\s*г\.?\s*о\.?\s*([^,]+?)\s*(?:,|$)'
    r'|(?:^|,)\s*городск\w*\s+округ\w*\s+([^,]+?)\s*(?:,|$)'
    r'|(?:^|,)\s*муниципальн\w*\s+округ\w*\s+([^,]+?)\s*(?:,|$)',
    re.IGNORECASE,
)
_RAION_RE = re.compile(r'(?:^|,)\s*([^,]*?\bрайон[^,]*?)\s*(?:,|$)', re.IGNORECASE)

_STREET_RE = re.compile(
    r'(?:^|,)\s*((?:ул\.|улица|пр-т|проспект|пер\.|переулок|ш\.|шоссе|б-р|бульвар|наб\.|набережная|пл\.|площадь)\s*[^,]*?)\s*(?:,|$)',
    re.IGNORECASE,
)
_HOUSE_RE = re.compile(r'(?:^|,)\s*(?:д\.|дом)\s*([^,]+?)\s*(?:,|$)', re.IGNORECASE)
_BUILDING_RE = re.compile(r'(?:^|,)\s*(?:корп\.?|корпус|стр\.?|строение)\s*([^,]+?)\s*(?:,|$)', re.IGNORECASE)
_OFFICE_RE = re.compile(r'(?:^|,)\s*(?:оф\.?|офис|кв\.?|квартира|пом\.?|помещение)\s*([^,]+?)\s*(?:,|$)', re.IGNORECASE)
_POSTAL_RE = re.compile(r'(?<!\d)(\d{6})(?!\d)')


def extract_settlement_name(address: str | None) -> str:
    """Населённый пункт из строки адреса. «» если не нашли.

    Примеры:
        "г. Донецк, ул. Артёма, д. 1"                     → "Донецк"
        "г.Донецк, ул. Артёма, д. 1"                       → "Донецк"
        "город Москва, Тверская ул., д. 1"                 → "Москва"
        "Санкт-Петербург, Невский пр-т, д. 1"               → "Санкт-Петербург"
        "обл. Запорожская, г.о. Бердянск, пер. Металлистов" → "Бердянск" (НЕ "о.Бердянск")
        "Запорожская обл., г.о. Бердянск, г. Бердянск, ул." → "Бердянск"
        "ул. Ленина, д. 5"                                  → ""
    """
    if not address or not address.strip():
        return ""
    m = _G_PREFIX_RE.search(address)
    if m:
        return m.group(1).strip()
    m = _CITY_WORD_RE.search(address)
    if m:
        return m.group(1).strip()
    for fed in _FEDERAL_CITIES:
        if re.search(r'(?:^|[,\s])' + re.escape(fed) + r'(?:[,\s]|$)', address):
            return fed
    # Фолбэк: нет отдельной строки «г. X» — сам городской округ назван по
    # населённому пункту (реальный случай на проде: "г.о. Бердянск" без
    # отдельного "г. Бердянск").
    m = _OKRUG_RE.search(address)
    if m:
        name = next((g for g in m.groups() if g), "")
        return name.strip()
    return ""


def _extract_district_name(address: str, *, settlement: str) -> str:
    """Район/городской (муниципальный) округ — ТОЛЬКО если это отдельный
    показатель от населённого пункта (иначе район дублировал бы то же имя,
    что уже попало в settlement через фолбэк _OKRUG_RE внутри
    extract_settlement_name — см. там)."""
    if not address:
        return ""
    m = _RAION_RE.search(address)
    if m:
        name = m.group(1).strip()
        if name and name.lower() != (settlement or "").lower():
            return name
    m = _OKRUG_RE.search(address)
    if m:
        name = next((g for g in m.groups() if g), "").strip()
        # Явная "г." строка нашлась отдельно => округ — самостоятельный
        # показатель (не совпадает с settlement, взятым из _G_PREFIX_RE/
        # _CITY_WORD_RE/федерального города).
        if name and _G_PREFIX_RE.search(address) and name.lower() != (settlement or "").lower():
            return name
    return ""


def _settlement_type_for(address: str, settlement: str) -> str:
    """Тип населённого пункта (г./г.о.) — по тому, какой маркер фактически
    его дал в extract_settlement_name (тот же приоритет: явная "г." строка
    важнее фолбэка на городской округ)."""
    if not settlement:
        return ""
    if _G_PREFIX_RE.search(address):
        return "г."
    if _CITY_WORD_RE.search(address):
        return "г."
    if settlement in _FEDERAL_CITIES:
        return ""  # федеральный город обычно пишется без префикса "г."
    if _OKRUG_RE.search(address):
        return "г.о."
    return ""


def _extract_segment(address: str, pattern: re.Pattern) -> str:
    if not address:
        return ""
    m = pattern.search(address)
    if not m:
        return ""
    return m.group(1).strip()


def parse_address(address: str | None) -> dict:
    """Строка адреса → словарь частей (см. ADDRESS_PART_KEYS). Best-effort —
    часть, которую не удалось распознать, остаётся "". Не бросает исключений.

    Идемпотентность: `compose_address(parse_address(compose_address(parts)))
    == compose_address(parts)` для канонического набора частей (см.
    backend/tests/test_address_compose.py)."""
    result = {k: "" for k in ADDRESS_PART_KEYS}
    if not address or not address.strip():
        return result
    text = address.strip()

    m = _POSTAL_RE.search(text)
    if m:
        result["postal_code"] = m.group(1)

    region = find_region_in_text(text)
    if region:
        result["region"] = region

    settlement = extract_settlement_name(text)
    if settlement:
        result["settlement"] = settlement
        result["settlement_type"] = _settlement_type_for(text, settlement)

    district = _extract_district_name(text, settlement=settlement)
    if district:
        result["district"] = district

    result["street"] = _extract_segment(text, _STREET_RE)
    result["house"] = _extract_segment(text, _HOUSE_RE)
    result["building"] = _extract_segment(text, _BUILDING_RE)
    result["office"] = _extract_segment(text, _OFFICE_RE)
    return result


def compose_address(parts: dict | None, *, building_prefix: str = "корп.") -> str:
    """Словарь частей (см. ADDRESS_PART_KEYS) → собранная строка адреса.
    Пустые части пропускаются. Порядок — канонический почтовый порядок
    (индекс, регион, район/округ, населённый пункт, улица, дом, корпус,
    офис).

    `building_prefix` — подпись перед корпусом/строением. По умолчанию
    «корп.» (юр. адрес контрагента, ContractorEditDialog). Адрес ДОСТАВКИ
    закупки (publications_payload.py::_build_delivery_address) уходит во
    внешний API Фабриканта, где исторически используется короткая подпись
    «к.» — формат внешнего потребителя менять нельзя, поэтому вызывающая
    сторона передаёт свой префикс вместо того, чтобы заводить вторую
    функцию сборки (ПРАВИЛО №6)."""
    p = {k: (parts or {}).get(k) or "" for k in ADDRESS_PART_KEYS}
    p = {k: v.strip() if isinstance(v, str) else v for k, v in p.items()}

    segments: list[str] = []
    if p["postal_code"]:
        segments.append(p["postal_code"])
    if p["region"]:
        segments.append(p["region"])
    if p["district"]:
        segments.append(p["district"])
    if p["settlement"]:
        stype = p["settlement_type"]
        segments.append(f"{stype} {p['settlement']}".strip() if stype else p["settlement"])
    if p["street"]:
        segments.append(p["street"])
    if p["house"]:
        segments.append(f"д. {p['house']}")
    if p["building"]:
        segments.append(f"{building_prefix} {p['building']}".strip())
    if p["office"]:
        segments.append(f"оф. {p['office']}")
    return ", ".join(s for s in segments if s)
