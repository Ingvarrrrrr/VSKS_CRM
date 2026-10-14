"""Поиск субъекта РФ внутри произвольного текста (юр. адрес организации,
адрес доставки и т.п.) — НЕ нормализация уже известного имени региона (это
делает ru_regions.canonical_region_name): здесь на входе целая строка адреса,
«119454, Г.МОСКВА, ул. Лобачевского, д. 1», и нужно ВЫЧЛЕНИТЬ из неё субъект.

Один источник данных — app/services/ru_regions.py (RU_REGIONS + REGION_INDEX,
ПРАВИЛО №6): этот модуль не хранит собственного списка регионов/алиасов,
только дополнительно огрубляет пунктуацию для сравнения со свободным текстом.

Используется: services/org_region_from_address.py (регион организации из
юр. адреса), backfill в миграции (organizations.region, если ещё не заполнен).
"""
import re

from app.services.ru_regions import RU_REGIONS, REGION_INDEX


def _strip_punctuation(s: str) -> str:
    """casefold + ё→е + вся пунктуация (точки, запятые, дефисы, тире) → пробел,
    схлопнуть пробелы. Нужно отдельно от ru_regions._normalize (которая
    СОХРАНЯЕТ дефисы — там это часть официального имени типа «Ханты-Мансийский»),
    потому что свободный адрес пишет «Г.МОСКВА» без пробела после точки, а
    субъект может быть указан через запятую в любом месте строки."""
    s = s.casefold().replace("ё", "е")
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _build_search_index() -> list[tuple[str, str]]:
    """[(нормализованный_ключ_без_пунктуации, каноническое_имя), ...], длинные
    ключи первыми — чтобы «Москва» не перехватывал совпадение раньше более
    специфичного «Московская область» (на деле не пересекаются подстрокой, но
    порядок по длине — общая защита от похожих названий)."""
    seen: dict[str, str] = {}
    for normalized_or_name, canonical in REGION_INDEX.items():
        key = _strip_punctuation(normalized_or_name)
        if key and key not in seen:
            seen[key] = canonical
    for canonical in RU_REGIONS:
        key = _strip_punctuation(canonical)
        if key and key not in seen:
            seen[key] = canonical
    return sorted(seen.items(), key=lambda kv: len(kv[0]), reverse=True)


_SEARCH_INDEX = _build_search_index()


def find_region_in_text(text: str | None) -> str | None:
    """Текст адреса → каноническое имя субъекта РФ (из RU_REGIONS) или None,
    если ни один субъект/алиас не встретился в тексте."""
    if not text:
        return None
    haystack = f" {_strip_punctuation(text)} "
    for key, canonical in _SEARCH_INDEX:
        if f" {key} " in haystack:
            return canonical
    return None
