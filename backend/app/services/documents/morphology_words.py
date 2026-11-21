"""Склонение отдельных слов и должностей (головная группа).

Вынесено из morphology.py для соблюдения Правила №5 (< 500 строк).
"""
from __future__ import annotations

import re
from typing import Optional

_morph = None


def _get_morph():
    global _morph
    if _morph is None:
        try:
            from pymorphy3 import MorphAnalyzer
            _morph = MorphAnalyzer()
        except Exception:
            _morph = False
    return _morph or None


def _to_gen_word_heuristic(word: str) -> str:
    """Эвристическое склонение слова в родительный падеж без pymorphy3."""
    if not word or len(word) < 2:
        return word
    lower = word.lower()
    cap = word[0].isupper()
    if lower.endswith(('ия', 'ой', 'ого', 'его', 'ев', 'ов', 'ей')) and len(lower) > 3:
        result = lower
    elif lower.endswith('ый'):
        result = lower[:-2] + 'ого'
    elif lower.endswith('ий'):
        prev = lower[-3] if len(lower) >= 3 else ''
        result = lower[:-2] + ('его' if prev in ('ж', 'ч', 'ш', 'щ') else 'ого')
    elif lower.endswith('ое'):
        result = lower[:-2] + 'ого'
    elif lower.endswith('ее'):
        result = lower[:-2] + 'его'
    elif lower.endswith('ие'):
        result = lower[:-2] + 'ия'
    elif lower.endswith('ая'):
        result = lower[:-2] + 'ей'
    elif lower.endswith('я'):
        result = lower[:-1] + 'и'
    elif lower.endswith('а'):
        result = lower
    elif lower.endswith('ь'):
        result = lower[:-1] + 'я'
    elif lower.endswith('й'):
        result = lower[:-1] + 'я'
    elif lower.endswith(('о', 'е', 'у', 'ы', 'э', 'ю')):
        result = lower
    else:
        result = lower + 'а'

    if cap:
        result = result[0].upper() + result[1:]
    return result


def _to_gen_word(word: str) -> str:
    if not word:
        return word
    morph = _get_morph()
    if morph:
        try:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({'gent'})
            if inflected:
                out = inflected.word
                if word[0].isupper():
                    out = out[0].upper() + out[1:]
                return out
        except Exception:
            pass
    return _to_gen_word_heuristic(word)


def _to_dat_word_heuristic(word: str) -> str:
    if not word or len(word) < 2:
        return word
    lower = word.lower()
    cap = word[0].isupper()
    if lower.endswith(('ый', 'ой')):
        result = lower[:-2] + 'ому'
    elif lower.endswith('ий'):
        prev = lower[-3] if len(lower) >= 3 else ''
        result = lower[:-2] + ('ему' if prev in ('ж', 'ч', 'ш', 'щ') else 'ому')
    elif lower.endswith('ое'):
        result = lower[:-2] + 'ому'
    elif lower.endswith('ее'):
        result = lower[:-2] + 'ему'
    elif lower.endswith('ие'):
        result = lower[:-2] + 'ию'
    elif lower.endswith('ая'):
        result = lower[:-2] + 'ой'
    elif lower.endswith('ь'):
        result = lower[:-1] + 'ю'
    elif lower.endswith('й'):
        result = lower[:-1] + 'ю'
    elif lower.endswith('а'):
        result = lower[:-1] + 'е'
    elif lower.endswith('я'):
        result = lower[:-1] + 'е'
    elif lower.endswith(('о', 'е', 'у', 'ы', 'э', 'ю')):
        result = lower
    else:
        result = lower + 'у'

    if cap:
        result = result[0].upper() + result[1:]
    return result


def _to_dat_word(word: str) -> str:
    if not word:
        return word
    morph = _get_morph()
    if morph:
        try:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({'datv'})
            if inflected:
                out = inflected.word
                if word[0].isupper():
                    out = out[0].upper() + out[1:]
                return out
        except Exception:
            pass
    return _to_dat_word_heuristic(word)


def _to_case_word(word: str, pymorphy_case: str) -> str:
    if not word:
        return word
    morph = _get_morph()
    if morph:
        try:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({pymorphy_case})
            if inflected:
                out = inflected.word
                if word[0].isupper():
                    out = out[0].upper() + out[1:]
                return out
        except Exception:
            pass
    # fallback
    from app.services.fio_inflect import inflect_position
    return inflect_position(word, pymorphy_case)


def _to_ablt_word(word: str) -> str:
    return _to_case_word(word, 'ablt')


def _to_accs_word(word: str) -> str:
    return _to_case_word(word, 'accs')


def _to_loct_word(word: str) -> str:
    return _to_case_word(word, 'loct')


def _to_case_position(phrase: str, case: str) -> str:
    """Склонить ДОЛЖНОСТЬ в падеж case ('gent'/'datv'/'ablt'/'accs'/'loct')."""
    if not phrase or not phrase.strip():
        return phrase or ""

    morph = _get_morph()
    if not morph:
        from app.services.fio_inflect import inflect_position
        return inflect_position(phrase, case)

    tokens = re.split(r'(\s+|-)', phrase)

    def _is_word(tok: str) -> bool:
        return tok.strip() != '' and tok != '-'

    word_indices = [i for i, t in enumerate(tokens) if _is_word(t)]
    if not word_indices:
        return phrase

    decline_word = {
        'gent': _to_gen_word, 'datv': _to_dat_word, 'ablt': _to_ablt_word,
        'accs': _to_accs_word, 'loct': _to_loct_word,
    }.get(case, _to_dat_word)

    out = list(tokens)
    stop = False
    for i in word_indices:
        if stop:
            break
        word = tokens[i]
        letters = [ch for ch in word if ch.isalpha()]
        if letters and len(letters) >= 2 and all(ch.isupper() for ch in letters):
            continue

        is_adj_or_prtf = False
        is_noun = False
        is_prtf = False
        try:
            parses = morph.parse(word.lower())
            tag = next((pr.tag for pr in parses if 'nomn' in pr.tag), parses[0].tag)
            is_prtf = 'PRTF' in tag
            is_adj_or_prtf = ('ADJF' in tag or is_prtf) and 'nomn' in tag
            is_noun = 'NOUN' in tag and 'nomn' in tag
        except Exception:
            pass

        if is_adj_or_prtf:
            out[i] = decline_word(word)
            if is_prtf:
                stop = True
            continue
        if is_noun:
            out[i] = decline_word(word)
            stop = True
            continue
        stop = True

    return ''.join(out)


def _to_gen_phrase(phrase: str) -> str:
    return _to_case_position(phrase, 'gent')


def _to_dat_position(phrase: str) -> str:
    return _to_case_position(phrase, 'datv')


def _to_ablt_position(phrase: str) -> str:
    return _to_case_position(phrase, 'ablt')


def _to_accs_position(phrase: str) -> str:
    return _to_case_position(phrase, 'accs')


def _to_loct_position(phrase: str) -> str:
    return _to_case_position(phrase, 'loct')


def _inflect_phrase_genitive(phrase: str) -> str:
    if not phrase or not phrase.strip():
        return ""
    morph = _get_morph()
    tokens = re.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*|\S+|\s+", phrase)
    out = []
    for tok in tokens:
        if re.fullmatch(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*", tok):
            if len(tok) >= 2 and tok.isupper():
                out.append(tok)
                continue
            inflected = None
            if morph:
                try:
                    parses = morph.parse(tok.lower())
                    parsed = next((p for p in parses if 'nomn' in p.tag), parses[0] if parses else None)
                    if parsed:
                        infl = parsed.inflect({'gent'})
                        if infl:
                            inflected = infl.word
                except Exception:
                    pass
            if not inflected:
                inflected = _to_gen_word_heuristic(tok.lower())
            out.append(inflected.lower())
        else:
            out.append(tok)
    return "".join(out)
