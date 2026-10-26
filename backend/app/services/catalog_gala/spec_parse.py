"""Разбор ключа характеристики поставщика на (имя, единица) — ОБЩАЯ функция
для ВСЕХ конвертеров catalog_gala/, у которых исходник отдаёт характеристики
как specifications-словарь с единицей в самом ключе (ПРАВИЛО №6). Раньше
жила только внутри from_electro_mpo.py; baucenter_construction_all.json
(владелец, 26.10) принёс тот же формат "<Имя> (<ед>)" (например
"Диаметр (мм)", "Расход в один слой до (м2/л)") — используется та же
функция, не вторая копия разбора.

Два распознаваемых формата ключа:
  - "<Имя> в <ед>" (electro_mpo: "Высота в м", "Объём  в м3" — повторные
    пробелы схлопываются перед разбором).
  - "<Имя> (<ед>)" (electro_mpo кабели, baucenter: "Диаметр (мм)").
Единица признаётся единицей, только если похожа на единицу (короткий код
до 3 символов ИЛИ содержит цифру — _looks_like_unit) — иначе это бытовое
слово ("в упаковке" и т.п.), ключ остаётся как есть, без разбора.
normalize_unit (units_normalize.py) применяется к найденной единице.
"""
import re

from app.services.catalog_gala.units_normalize import normalize_unit

_UNIT_SUFFIX_RE = re.compile(r"^(.*?)\s+в\s+(\S+)$", re.IGNORECASE)
# Короткий код типа "м"/"кг"/"м3" — не бытовое слово (см. docstring).
_UNIT_TOKEN_RE = re.compile(r"^[a-zA-Zа-яА-ЯёЁ0-9/]{1,3}$")
_UNIT_PAREN_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)$")


def clean_key(key: str) -> str:
    return re.sub(r"\s+", " ", key).strip()


def looks_like_unit(token: str) -> bool:
    return bool(_UNIT_TOKEN_RE.match(token)) or any(ch.isdigit() for ch in token)


def split_key_unit(raw_key: str) -> tuple:
    """Возвращает (имя, единица|None); единица уже нормализована
    (normalize_unit)."""
    key = clean_key(raw_key)

    m = _UNIT_SUFFIX_RE.match(key)
    if m and looks_like_unit(m.group(2).strip()):
        return m.group(1).strip(), normalize_unit(m.group(2).strip())

    m = _UNIT_PAREN_RE.match(key)
    if m and looks_like_unit(m.group(2).strip()):
        return m.group(1).strip(), normalize_unit(m.group(2).strip())

    return key, None
