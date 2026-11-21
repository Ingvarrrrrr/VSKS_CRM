"""Падежные склонения ФИО и должностей для шаблонов документов.

Phase 26-V: pymorphy3 / fio_inflect — общие слова (должности), petrovich / fio_inflect — ФИО.
Вынесено из app/routers/documents.py (рефакторинг без изменения поведения).
"""
from __future__ import annotations

import re
from typing import Optional

# Реэкспорт функций склонения слов и должностей из morphology_words
from app.services.documents.morphology_words import (
    _morph,
    _get_morph,
    _to_gen_word_heuristic,
    _to_gen_word,
    _to_dat_word_heuristic,
    _to_dat_word,
    _to_case_word,
    _to_ablt_word,
    _to_accs_word,
    _to_loct_word,
    _to_case_position,
    _to_gen_phrase,
    _to_dat_position,
    _to_ablt_position,
    _to_accs_position,
    _to_loct_position,
    _inflect_phrase_genitive,
)
from app.services.fio_inflect import inflect_fio, inflect_position, inflect_signatory_full

_petro = None


def _get_petro():
    global _petro
    if _petro is None:
        try:
            from petrovich.main import Petrovich
            from petrovich.enums import Case, Gender
            _petro = (Petrovich(), Case, Gender)
        except Exception:
            _petro = False
    return _petro or None


_SIBILANT_VELAR_ENDINGS = ('га', 'ка', 'ха', 'жа', 'ша', 'ча', 'ща')
_SIBILANT_VELAR_CASE_SUFFIX = {'GENITIVE': 'и', 'DATIVE': 'е'}
_PLAIN_A_CASE_SUFFIX = {'GENITIVE': 'ы', 'DATIVE': 'е'}


def _apply_sibilant_velar_a_fix(word: str, case_name: str) -> str | None:
    suffix = _SIBILANT_VELAR_CASE_SUFFIX.get(case_name)
    if not suffix or not word:
        return None
    if not word.lower().endswith(_SIBILANT_VELAR_ENDINGS):
        return None
    stem = word[:-1]
    return stem + (suffix.upper() if word.isupper() else suffix)


def _apply_plain_a_male_fix(word: str, case_name: str) -> str | None:
    suffix = _PLAIN_A_CASE_SUFFIX.get(case_name)
    if not suffix or not word:
        return None
    lower = word.lower()
    if not lower.endswith('а') or lower.endswith(_SIBILANT_VELAR_ENDINGS):
        return None
    stem = word[:-1]
    return stem + (suffix.upper() if word.isupper() else suffix)


def _decline_name_part(petro, method: str, word: str, case, case_name: str, gender) -> str:
    patched = _apply_sibilant_velar_a_fix(word, case_name)
    if patched is None and gender == 'male':
        patched = _apply_plain_a_male_fix(word, case_name)
    if patched is not None:
        return patched
    return getattr(petro, method)(word, case, gender)


def _is_patronymic(word: str) -> bool:
    lower = word.lower().rstrip(',')
    return lower.endswith(('вич', 'вна', 'чна', 'ична'))


_INITIALS_TOKEN_RE = re.compile(r'^[А-ЯA-ZЁ]\.(?:[А-ЯA-ZЁ]\.)?$')


def _looks_like_initials_token(word: str) -> bool:
    return bool(_INITIALS_TOKEN_RE.match(word))


_FEMALE_SURNAME_ENDINGS = ('ова', 'ева', 'ина', 'ына', 'ская', 'цкая', 'ая')

_CASE_MAP_SHORT = {
    'GENITIVE': 'gent',
    'DATIVE': 'datv',
    'ACCUSATIVE': 'accs',
    'INSTRUMENTAL': 'ablt',
    'PREPOSITIONAL': 'loct',
}


def _to_case_fio(full_name: str, case_name: str) -> str:
    """Склонить ФИО в заданный падеж (petrovich с fallback на fio_inflect)."""
    if not full_name or not full_name.strip():
        return full_name
    parts = full_name.strip().split()
    normalized = ' '.join(parts)
    short_case = _CASE_MAP_SHORT.get(case_name, 'gent')

    petro_pack = _get_petro()
    if not petro_pack:
        # Fallback на собственный детерминированный чистый парсер fio_inflect
        return inflect_fio(normalized, short_case)

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name, None)
    if not case:
        return inflect_fio(normalized, short_case)

    ogly_kyzy = {'оглы', 'кызы'}
    if len(parts) == 3 and _is_patronymic(parts[2]):
        fio_parts, suffix = parts, None
    elif len(parts) == 4 and parts[3].lower() in ogly_kyzy:
        fio_parts, suffix = parts[:3], parts[3]
    else:
        return inflect_fio(normalized, short_case)

    try:
        gender = Gender.FEMALE if fio_parts[2].lower().endswith(('вна', 'чна', 'ична')) else Gender.MALE
        result = [
            _decline_name_part(petro, 'lastname', fio_parts[0], case, case_name, gender),
            _decline_name_part(petro, 'firstname', fio_parts[1], case, case_name, gender),
            _decline_name_part(petro, 'middlename', fio_parts[2], case, case_name, gender),
        ]
        if suffix:
            result.append(suffix)
        res = ' '.join(result)
        # Если petrovich не изменил ФИО (например, не нашел правило), сверяем с fio_inflect
        if res == normalized and short_case in ('gent', 'datv', 'ablt'):
            return inflect_fio(normalized, short_case)
        return res
    except Exception:
        return inflect_fio(normalized, short_case)


def _to_gen_fio(full_name: str) -> str:
    return _to_case_fio(full_name, 'GENITIVE')


def _to_dat_fio(full_name: str) -> str:
    return _to_case_fio(full_name, 'DATIVE')


def _to_case_fio_initials(full_name: str, case_name: str) -> str:
    """«Фамилия И.О.» в падеже case_name."""
    if not full_name or not full_name.strip():
        return full_name
    from .formatting import _fio_to_initials
    nominative_initials = _fio_to_initials(full_name)

    parts = full_name.strip().split()
    short_case = _CASE_MAP_SHORT.get(case_name, 'gent')

    if len(parts) == 2 and _looks_like_initials_token(parts[1]):
        return _decline_bare_surname_initials(parts[0], parts[1], case_name)

    petro_pack = _get_petro()
    if not petro_pack:
        return inflect_fio(nominative_initials, short_case)

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name, None)
    if not case:
        return inflect_fio(nominative_initials, short_case)

    ogly_kyzy = {'оглы', 'кызы'}
    is_classic = (len(parts) == 3 and _is_patronymic(parts[2])) or (
        len(parts) == 4 and parts[3].lower() in ogly_kyzy
    )
    if not is_classic:
        return inflect_fio(nominative_initials, short_case)

    try:
        gender = Gender.FEMALE if parts[2].lower().endswith(('вна', 'чна', 'ична')) else Gender.MALE
        last_declined = _decline_name_part(petro, 'lastname', parts[0], case, case_name, gender)
    except Exception:
        return inflect_fio(nominative_initials, short_case)

    nom_words = nominative_initials.split(maxsplit=1)
    if len(nom_words) == 2:
        out = f"{last_declined} {nom_words[1]}"
    else:
        out = last_declined
    if parts[0][0].isupper():
        out = out[0].upper() + out[1:]
    return out


def _decline_bare_surname_initials(surname: str, initials_token: str, case_name: str) -> str:
    short_case = _CASE_MAP_SHORT.get(case_name, 'gent')
    petro_pack = _get_petro()
    if not petro_pack:
        return inflect_fio(f"{surname} {initials_token}", short_case)

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name, None)
    if not case:
        return inflect_fio(f"{surname} {initials_token}", short_case)

    gender = Gender.FEMALE if surname.lower().endswith(_FEMALE_SURNAME_ENDINGS) else Gender.MALE
    try:
        declined = _decline_name_part(petro, 'lastname', surname, case, case_name, gender)
        if surname[0].isupper():
            declined = declined[0].upper() + declined[1:]
        return f"{declined} {initials_token}"
    except Exception:
        return inflect_fio(f"{surname} {initials_token}", short_case)


def _decline_surname_initials_prefix(initials_token: str, surname: str, case_name: str) -> str:
    short_case = _CASE_MAP_SHORT.get(case_name, 'gent')
    petro_pack = _get_petro()
    if not petro_pack:
        return inflect_fio(f"{initials_token} {surname}", short_case)

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name, None)
    if not case:
        return inflect_fio(f"{initials_token} {surname}", short_case)

    gender = Gender.FEMALE if surname.lower().endswith(_FEMALE_SURNAME_ENDINGS) else Gender.MALE
    try:
        declined = _decline_name_part(petro, 'lastname', surname, case, case_name, gender)
        if surname[0].isupper():
            declined = declined[0].upper() + declined[1:]
        return f"{initials_token} {declined}"
    except Exception:
        return inflect_fio(f"{initials_token} {surname}", short_case)


def _to_case_initials_prefix(value: str, case_name: str) -> str:
    if not value or not value.strip():
        return value
    parts = value.strip().split()
    if len(parts) == 2 and _looks_like_initials_token(parts[0]):
        return _decline_surname_initials_prefix(parts[0], parts[1], case_name)
    short_case = _CASE_MAP_SHORT.get(case_name, 'gent')
    return inflect_fio(value, short_case)


def _to_gen_fio_initials(full_name: str) -> str:
    return _to_case_fio_initials(full_name, 'GENITIVE')


def _to_dat_fio_initials(full_name: str) -> str:
    return _to_case_fio_initials(full_name, 'DATIVE')
