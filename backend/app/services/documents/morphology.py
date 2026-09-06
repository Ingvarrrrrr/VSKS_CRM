"""Падежные склонения ФИО и должностей для шаблонов документов.

Phase 26-V: pymorphy3 — общие слова (должности), petrovich — ФИО.
Вынесено из app/routers/documents.py (рефакторинг без изменения
поведения) — единственное место с этой логикой."""


# Phase 26-V: падежные склонения для шаблонов СЗ.
# pymorphy3 — для общих слов (должность), petrovich — для ФИО.
_morph = None
_petro = None

def _get_morph():
    global _morph
    if _morph is None:
        try:
            from pymorphy3 import MorphAnalyzer
            _morph = MorphAnalyzer()
        except Exception:
            _morph = False
    return _morph or None

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

def _to_gen_word_heuristic(word: str) -> str:
    """Эвристическое склонение слова в родительный падеж без pymorphy3.

    Покрывает 80-90% русских должностей (мужской род, второе склонение).
    Phase 26-SS: fallback после удаления pymorphy3 (OOM на проде, e2dee47).
    """
    if not word or len(word) < 2:
        return word
    lower = word.lower()
    # Сохраняем регистр первой буквы
    cap = word[0].isupper()
    # Окончания:
    # Слова УЖЕ в родительном падеже (атрибуты): «отдела», «управления»,
    # «фирмы» → не трогаем. Эвристика: -а/-я/-ы/-и/-ов/-ей часто = gen.sg/pl.
    if lower.endswith(('ия', 'ой', 'ого', 'его', 'ев', 'ов', 'ей')) and len(lower) > 3:
        result = lower
    elif lower.endswith('ый'):     # «главный» → «главного»
        result = lower[:-2] + 'ого'
    elif lower.endswith('ий'):     # «ведущий» → «ведущего» (после ж/ч/ш/щ → -его),
                                    # «генеральный» → «генерального» (после др. → -ого)
        prev = lower[-3] if len(lower) >= 3 else ''
        result = lower[:-2] + ('его' if prev in ('ж', 'ч', 'ш', 'щ') else 'ого')
    elif lower.endswith('ая'):     # «заведующая» → «заведующей»
        result = lower[:-2] + 'ей'
    elif lower.endswith('я'):      # «дядя» → «дяди»
        result = lower[:-1] + 'и'
    elif lower.endswith('а'):      # «бухгалтера» — уже gen.sg → не трогаем
        result = lower
    elif lower.endswith('ь'):      # «руководитель» → «руководителя»
        result = lower[:-1] + 'я'
    elif lower.endswith('й'):      # «специалистей» — редко
        result = lower[:-1] + 'я'
    elif lower.endswith(('о', 'е', 'у', 'ы', 'э', 'ю')):
        # Несклоняемые: фамилии типа «Лопатко», иностранные «такси»
        result = lower
    else:                          # consonant
        # «специалист» → «специалиста», «директор» → «директора»
        result = lower + 'а'

    if cap:
        result = result[0].upper() + result[1:]
    return result


def _to_gen_word(word: str) -> str:
    """Склонить одно слово в родительный падеж: pymorphy3 → эвристика."""
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
    # Phase 26-SS: fallback на эвристику если pymorphy3 нет (e2dee47 OOM revert)
    return _to_gen_word_heuristic(word)

def _to_gen_phrase(phrase: str) -> str:
    """Склонить фразу (должность) в родительный падеж — каждое слово отдельно."""
    if not phrase:
        return phrase
    import re as _re
    parts = _re.split(r'(\s+|-)', phrase)
    return ''.join(_to_gen_word(p) if p.strip() and p != '-' else p for p in parts)

def _inflect_phrase_genitive(phrase: str) -> str:
    """
    Склоняет фразу в родительный падеж пословно (для subject/service_name).
    Примеры:
      «Канцелярские принадлежности» → «канцелярских принадлежностей»
      «Оказание полиграфических услуг» → «оказания полиграфических услуг»
    Результат ВСЕГДА в нижнем регистре (для вставки внутри фразы:
    «Прошу осуществить закупку канцелярских принадлежностей.»).
    Аббревиатуры (ООО), числа, латиница — пропускаются как есть.
    Fallback на per-word эвристику если pymorphy3 недоступен.
    """
    if not phrase or not phrase.strip():
        return ""
    morph = _get_morph()
    import re as _re2
    # Токенизация: русские слова (с дефисом) / прочие токены / пробелы
    tokens = _re2.findall(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*|\S+|\s+", phrase)
    out = []
    for tok in tokens:
        if _re2.fullmatch(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*", tok):
            # Аббревиатуры (все буквы заглавные, ≥2 символа): не склонять
            if len(tok) >= 2 and tok.isupper():
                out.append(tok)
                continue
            inflected = None
            if morph:
                try:
                    parses = morph.parse(tok.lower())
                    # Pymorphy3 возвращает все возможные разборы по убыванию вероятности.
                    # Для омонимов («принадлежности» = nomn.plur ИЛИ gent.sg) выбираем
                    # разбор в именительном падеже — иначе inflect({'gent'}) у уже-gent
                    # вернёт то же слово (баг «принадлежности» → «принадлежности»).
                    parsed = None
                    for p in parses:
                        if 'nomn' in p.tag:
                            parsed = p
                            break
                    if not parsed and parses:
                        parsed = parses[0]
                    if parsed:
                        infl = parsed.inflect({'gent'})
                        if infl:
                            inflected = infl.word
                except Exception:
                    pass
            # Fallback: per-word эвристика (если pymorphy3 не сработал)
            if not inflected:
                inflected = _to_gen_word_heuristic(tok.lower())
            out.append(inflected.lower())
        else:
            out.append(tok)
    return "".join(out)


def _to_gen_fio(full_name: str) -> str:
    """Склонить ФИО (Фамилия Имя Отчество) в родительный падеж через petrovich."""
    petro_pack = _get_petro()
    if not petro_pack or not full_name:
        return full_name
    petro, Case, Gender = petro_pack
    parts = full_name.strip().split()
    if not parts:
        return full_name
    try:
        gender = Gender.MALE
        if len(parts) >= 3 and parts[2].endswith(('вна', 'чна')):
            gender = Gender.FEMALE
        elif len(parts) >= 3 and parts[2].endswith('вич'):
            gender = Gender.MALE
        result = []
        if len(parts) >= 1:
            result.append(petro.lastname(parts[0], Case.GENITIVE, gender))
        if len(parts) >= 2:
            result.append(petro.firstname(parts[1], Case.GENITIVE, gender))
        if len(parts) >= 3:
            result.append(petro.middlename(parts[2], Case.GENITIVE, gender))
        return ' '.join(result)
    except Exception:
        return _to_gen_phrase(full_name)
