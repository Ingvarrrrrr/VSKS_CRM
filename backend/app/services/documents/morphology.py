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


# ── Патч известного дефекта установленной версии petrovich (2.0.1) ──────────
#
# Жалоба владельца (28.10.2026): «Копылова Ольга Владимировна» → «Копыловой
# Ольгы Владимировны» вместо «Ольги». Причина — НЕ в этом файле и не в
# petrovich.rules.json (там нужное правило есть, gender='androgynous',
# окончание «-и» для имён/фамилий на -га/-ка/-ха/-ча/-ща/-жа), а в самом
# коде библиотеки: `Petrovich.__find_rules` (petrovich/main.py, установлена
# версия 2.0.1) сравнивает `rule['gender'] != gender` БУКВАЛЬНО, без учёта
# androgynous — поэтому androgynous-правила никогда не применяются, если
# вызывающий код передаёт явный gender ('male'/'female'), как делает
# `_to_case_fio` ниже. Следующая версия библиотеки (3.0.0) чинит это ровно
# так, как нужно (проверено), но требует Python 3.12+ (PEP 695 `type`
# statement в main.py) — контейнер backend на 3.11, апгрейд вне объёма этой
# задачи. Патчить файл самой библиотеки нельзя — site-packages перезатирается
# при любой переустановке зависимостей (не единственный источник истины).
# Поэтому: воспроизводим ИМЕННО то правило, что в данных petrovich уже есть,
# но код библиотеки его не достаёт — здесь, в единственном месте склонения
# ФИО (_to_case_fio/_to_case_fio_initials ниже), ДО вызова petrovich.
#
# Побочный эффект того же бага — мужские имена на безударное -а без
# отдельного мужского правила в таблице (Никита, Кузьма, Фока, Лука — есть
# только androgynous-правило «-а», тоже недоступное) не склонялись вовсе.
# Патч закрывает оба случая.
_SIBILANT_VELAR_ENDINGS = ('га', 'ка', 'ха', 'жа', 'ша', 'ча', 'ща')
# Орфографическое правило «жи-ши пиши с буквой и» для родительного/дательного
# падежа слов 1-го склонения на -а после шипящих/заднеязычных (г,к,х,ж,ш,ч,щ):
# «Ольга»→«Ольги»/«Ольге», никогда «Ольгы».
_SIBILANT_VELAR_CASE_SUFFIX = {'GENITIVE': 'и', 'DATIVE': 'е'}
# Общее правило для -а без шипящих/заднеязычных (андрогинное у petrovich,
# но недостижимое с явным gender) — то же окончание, что уже верно работает
# для женских имён через собственное женское правило («Марфа»→«Марфы»):
# достраиваем его и для мужских имён на -а (Никита→Никиты, Кузьма→Кузьмы).
_PLAIN_A_CASE_SUFFIX = {'GENITIVE': 'ы', 'DATIVE': 'е'}


def _apply_sibilant_velar_a_fix(word: str, case_name: str) -> str | None:
    """См. блок комментариев выше. None — патч не применим, использовать
    обычный petrovich."""
    suffix = _SIBILANT_VELAR_CASE_SUFFIX.get(case_name)
    if not suffix or not word:
        return None
    if not word.lower().endswith(_SIBILANT_VELAR_ENDINGS):
        return None
    stem = word[:-1]
    return stem + (suffix.upper() if word.isupper() else suffix)


def _apply_plain_a_male_fix(word: str, case_name: str) -> str | None:
    """Мужские имена на безударное -а (Никита, Кузьма...) — см. блок
    комментариев выше. Вызывать только для gender == Gender.MALE."""
    suffix = _PLAIN_A_CASE_SUFFIX.get(case_name)
    if not suffix or not word:
        return None
    lower = word.lower()
    if not lower.endswith('а') or lower.endswith(_SIBILANT_VELAR_ENDINGS):
        return None
    stem = word[:-1]
    return stem + (suffix.upper() if word.isupper() else suffix)


def _decline_name_part(petro, method: str, word: str, case, case_name: str, gender) -> str:
    """Склонить один компонент ФИО (фамилия/имя/отчество) — патч выше в
    приоритете перед обычным petrovich (ПРАВИЛО №6: единственная точка
    вызова petrovich для ФИО — здесь, в обёртке, а не напрямую в трёх
    местах _to_case_fio/_to_case_fio_initials)."""
    patched = _apply_sibilant_velar_a_fix(word, case_name)
    if patched is None and gender == 'male':
        patched = _apply_plain_a_male_fix(word, case_name)
    if patched is not None:
        return patched
    return getattr(petro, method)(word, case, gender)


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

def _to_dat_word_heuristic(word: str) -> str:
    """Эвристическое склонение слова в дательный падеж без pymorphy3.

    Та же идея, что `_to_gen_word_heuristic` (мужской род, 2-е склонение),
    зеркально для дательного падежа — fallback, когда pymorphy3 недоступен.
    """
    if not word or len(word) < 2:
        return word
    lower = word.lower()
    cap = word[0].isupper()
    if lower.endswith(('ый', 'ой')):      # «главный» → «главному»
        result = lower[:-2] + 'ому'
    elif lower.endswith('ий'):            # «ведущий» → «ведущему»,
                                            # «генеральный» → не сюда (окончание -ый)
        prev = lower[-3] if len(lower) >= 3 else ''
        result = lower[:-2] + ('ему' if prev in ('ж', 'ч', 'ш', 'щ') else 'ому')
    elif lower.endswith('ая'):            # «заведующая» → «заведующей»
        result = lower[:-2] + 'ой'
    elif lower.endswith('ь'):             # «руководитель» → «руководителю»
        result = lower[:-1] + 'ю'
    elif lower.endswith('й'):
        result = lower[:-1] + 'ю'
    elif lower.endswith('а'):             # «бухгалтера» (уже gen) → «бухгалтере» неверно,
                                            # но эвристика без pymorphy3 не различает — ближайшее -е
        result = lower[:-1] + 'е'
    elif lower.endswith('я'):
        result = lower[:-1] + 'е'
    elif lower.endswith(('о', 'е', 'у', 'ы', 'э', 'ю')):
        # Несклоняемые
        result = lower
    else:                                  # consonant: «директор» → «директору»
        result = lower + 'у'

    if cap:
        result = result[0].upper() + result[1:]
    return result


def _to_dat_word(word: str) -> str:
    """Склонить одно слово в дательный падеж: pymorphy3 → эвристика."""
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


def _to_ablt_word(word: str) -> str:
    """Склонить одно слово в творительный падеж: pymorphy3 → слово без
    изменений (без pymorphy3 эвристики для творительного не заводим — см.
    _to_gen_word/_to_dat_word, тот же паттерн, просто без heuristic-fallback)."""
    if not word:
        return word
    morph = _get_morph()
    if morph:
        try:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({'ablt'})
            if inflected:
                out = inflected.word
                if word[0].isupper():
                    out = out[0].upper() + out[1:]
                return out
        except Exception:
            pass
    return word


def _to_case_position(phrase: str, case: str) -> str:
    """Склонить ДОЛЖНОСТЬ в падеж *case* ('gent' родительный / 'datv'
    дательный / 'ablt' творительный) — только управляющую головную группу,
    НЕ пословно.

    ПРАВИЛО №6: единственный алгоритм разбора головной группы должности —
    используется и для родительного (_to_gen_phrase), и для дательного
    (_to_dat_position) падежей, обе — тонкие обёртки над этой функцией.

    Баг до объединения (15.10.2026, владелец): старый пословный
    `_to_gen_phrase` ломал хвост и аббревиатуры — «Председатель Совета
    Донецкого РО ВСКС» → «Председателя Совета Донецкого Ро Вскса»
    (склонял КАЖДОЕ слово, включая уже-родительный «Совета», «Донецкого» и
    аббревиатуры РО/ВСКС). Пословный алгоритм для дательного никогда не
    заводился отдельно — сразу делался головной (см. ниже), поэтому баг был
    только в родительном; теперь оба падежа идут через один безопасный
    разбор головы.

    Правило: с начала фразы склоняются идущие подряд прилагательные/причастия
    в им.падеже (ADJF/PRTF, nomn), затем первое существительное в им.падеже
    (NOUN, nomn) склоняется и ДАЛЬШЕ СКЛОНЕНИЕ ОСТАНАВЛИВАЕТСЯ — остаток
    фразы возвращается дословно (он управляется этим существительным,
    «Совета Донецкого РО ВСКС» уже не меняется). Причастие (PRTF, например
    «Исполняющий») само управляет дополнением — склоняется и сразу
    останавливает разбор («Исполняющего/Исполняющему обязанности директора»).
    Аббревиатуры (слово целиком заглавными буквами, ≥2 символа) не трогаются
    и не останавливают разбор (пропускаются как «не опорное слово»).
    Регистр первой буквы каждого слова сохраняется (см. `_to_gen_word`/
    `_to_dat_word`).

    Без pymorphy3 — простая эвристика: первые слова с типичными
    прилагательными окончаниями (-ый/-ой/-ий/-ая) считаются головной группой
    и склоняются, первое слово без такого окончания — существительное,
    склоняется, разбор останавливается.
    """
    if not phrase or not phrase.strip():
        return phrase or ""

    import re as _re3
    tokens = _re3.split(r'(\s+|-)', phrase)

    def _is_word(tok: str) -> bool:
        return tok.strip() != '' and tok != '-'

    word_indices = [i for i, t in enumerate(tokens) if _is_word(t)]
    if not word_indices:
        return phrase

    # Переиспользуем уже готовые пословные склонятели (pymorphy3 + эвристика
    # как fallback) — не второй расчёт падежного окончания, только второй
    # разбор ГОЛОВНОЙ ГРУППЫ сверху.
    decline_word = {'gent': _to_gen_word, 'datv': _to_dat_word, 'ablt': _to_ablt_word}.get(case, _to_dat_word)

    morph = _get_morph()
    out = list(tokens)
    stop = False
    for i in word_indices:
        if stop:
            break
        word = tokens[i]
        letters = [ch for ch in word if ch.isalpha()]
        if letters and len(letters) >= 2 and all(ch.isupper() for ch in letters):
            # Аббревиатура — не склоняем, не останавливаемся (не опорное слово)
            continue

        is_adj_or_prtf = False
        is_noun = False
        is_prtf = False
        if morph:
            try:
                # Средний род / неодуш. слова («отделение», «Региональное») —
                # им. и вин. падеж пишутся одинаково, и pymorphy3 нередко
                # ранжирует вин. выше (видел на практике: «отделение» →
                # top-parse accs 0.6 против nomn 0.4). Смотрим все разборы
                # слова, а не только первый по score — тот же приём, что уже
                # применяется в `_inflect_phrase_genitive` ниже (ПРАВИЛО №6,
                # не второй алгоритм, та же идея "искать разбор с nomn").
                # Склоняем через `decline_word` всё равно по топ-разбору —
                # pymorphy инфлектит из любого падежа в целевой правильно
                # (лексема одна), это лишь переопределяет ДЕТЕКЦИЮ "можно
                # склонять".
                parses = morph.parse(word.lower())
                tag = next((pr.tag for pr in parses if 'nomn' in pr.tag), parses[0].tag)
                is_prtf = 'PRTF' in tag
                is_adj_or_prtf = ('ADJF' in tag or is_prtf) and 'nomn' in tag
                is_noun = 'NOUN' in tag and 'nomn' in tag
            except Exception:
                pass
        if morph is None:
            lw = word.lower()
            is_adj_or_prtf = lw.endswith(('ый', 'ой', 'ий', 'ая'))
            is_noun = not is_adj_or_prtf

        if is_adj_or_prtf:
            out[i] = decline_word(word)
            if is_prtf:
                stop = True
            continue
        if is_noun:
            out[i] = decline_word(word)
            stop = True
            continue
        # Слово не распознано ни как прилагательное/причастие, ни как
        # существительное в им.падеже — дальше не трогаем.
        stop = True

    return ''.join(out)


def _to_gen_phrase(phrase: str) -> str:
    """Склонить ДОЛЖНОСТЬ в родительный падеж — тонкая обёртка над
    `_to_case_position` (головная группа, не пословно, см. её докстринг).
    Имя сохранено — много вызовов (contexts_extra.py,
    stages_approvers_list.py, initiator_position_gen и т.д.)."""
    return _to_case_position(phrase, 'gent')


def _to_dat_position(phrase: str) -> str:
    """Склонить ДОЛЖНОСТЬ в дательный падеж — тонкая обёртка над
    `_to_case_position` (см. её докстринг)."""
    return _to_case_position(phrase, 'datv')


def _to_ablt_position(phrase: str) -> str:
    """Склонить ДОЛЖНОСТЬ/название в творительный падеж — тонкая обёртка над
    `_to_case_position` (см. её докстринг)."""
    return _to_case_position(phrase, 'ablt')


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


def _is_patronymic(word: str) -> bool:
    """Похоже ли слово на русское отчество (мужское/женское)."""
    lower = word.lower().rstrip(',')
    return lower.endswith(('вич', 'вна', 'чна', 'ична'))


import re as _re_initials

_INITIALS_TOKEN_RE = _re_initials.compile(r'^[А-ЯA-ZЁ]\.(?:[А-ЯA-ZЁ]\.)?$')


def _looks_like_initials_token(word: str) -> bool:
    """«И.» или «И.О.» — одна/две заглавные буквы с точками, без остального
    текста ФИО (используется для bare «Фамилия И.О.» ниже)."""
    return bool(_INITIALS_TOKEN_RE.match(word))


# Типичные окончания ЖЕНСКИХ фамилий (androgynous-формы разные в самом
# именительном падеже — в отличие от имени/отчества, род фамилии обычно
# можно определить по её окончанию без отдельного патронимика).
_FEMALE_SURNAME_ENDINGS = ('ова', 'ева', 'ина', 'ына', 'ская', 'цкая', 'ая')


def _to_case_fio(full_name: str, case_name: str) -> str:
    """Склонить ФИО в заданный падеж через petrovich.

    ПРАВИЛО №6: единственное место склонения ФИО подписантов — используется
    и для инициатора, и для ответственного, и для исполнителя в договоре,
    для родительного (_to_gen_fio) и дательного (_to_dat_fio) падежей —
    обе тонкие обёртки над этой функцией, логика отбора слов/пола одна.

    *case_name* — имя атрибута `petrovich.enums.Case` ('GENITIVE'/'DATIVE').

    Petrovich умеет склонять только классическое русское «Фамилия Имя
    Отчество» (ровно 3 слова, третье — отчество) — опционально с «оглы»/
    «кызы» 4-м словом. Любое иностранное имя (2 слова, 4+ слов без оглы/
    кызы, запятые внутри и т.п.) petrovich склоняет наугад и теряет слова
    (баг: «Дефассье Лоран, Луи, Клод» → «Дефассье Лоран, Луи,» — «Клод»
    пропадал). Для таких случаев возвращаем ФИО как есть (без падежа),
    только нормализуя пробелы — лучше неизменённое ФИО, чем потерянное
    слово или выдуманное окончание.
    """
    if not full_name or not full_name.strip():
        return full_name
    # Нормализация пробелов, слова — как в исходной строке (с запятыми, если были)
    parts = full_name.strip().split()
    normalized = ' '.join(parts)

    petro_pack = _get_petro()
    if not petro_pack:
        return normalized

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name)

    # Случай 1: ровно 3 слова, третье — отчество → классическое ФИО.
    # Случай 2: 4 слова, четвёртое — «оглы»/«кызы» (тюркский патронимик,
    # не склоняется) → склоняем первые три, 4-е оставляем как есть.
    ogly_kyzy = {'оглы', 'кызы'}
    if len(parts) == 3 and _is_patronymic(parts[2]):
        fio_parts, suffix = parts, None
    elif len(parts) == 4 and parts[3].lower() in ogly_kyzy:
        fio_parts, suffix = parts[:3], parts[3]
    else:
        # Иностранное / неполное / с запятыми ФИО — не выдумываем падеж.
        return normalized

    try:
        gender = Gender.FEMALE if fio_parts[2].lower().endswith(('вна', 'чна', 'ична')) else Gender.MALE
        result = [
            _decline_name_part(petro, 'lastname', fio_parts[0], case, case_name, gender),
            _decline_name_part(petro, 'firstname', fio_parts[1], case, case_name, gender),
            _decline_name_part(petro, 'middlename', fio_parts[2], case, case_name, gender),
        ]
        if suffix:
            result.append(suffix)
        return ' '.join(result)
    except Exception:
        return normalized


def _to_gen_fio(full_name: str) -> str:
    """Склонить ФИО в родительный падеж — тонкая обёртка над `_to_case_fio`
    (поведение не изменилось, см. докстринг `_to_case_fio`)."""
    return _to_case_fio(full_name, 'GENITIVE')


def _to_dat_fio(full_name: str) -> str:
    """Склонить ФИО в дательный падеж — тонкая обёртка над `_to_case_fio`.

    «Артеева Анна Игоревна» → «Артеевой Анне Игоревне».
    Неклассическое ФИО (см. докстринг `_to_case_fio`) — возвращается как есть.
    """
    return _to_case_fio(full_name, 'DATIVE')


def _to_case_fio_initials(full_name: str, case_name: str) -> str:
    """«Фамилия И.О.» в падеже *case_name* ('GENITIVE'/'DATIVE'): фамилия
    склоняется (petrovich), инициалы имени/отчества — как в
    `formatting._fio_to_initials` (тот же расчёт инициалов, ПРАВИЛО №6 — не
    дублируем вторым алгоритмом).

    ПРАВИЛО №6: единственный расчёт — `_to_gen_fio_initials`/
    `_to_dat_fio_initials` ниже тонкие обёртки над этой функцией (обобщена
    из исходной `_to_dat_fio_initials`, второй копии для родительного падежа
    не заводим).

    «Артеева Анна Игоревна» (DATIVE) → «Артеевой А.И.»
    «Артеева Анна Игоревна» (GENITIVE) → «Артеевой А.И.» (у фамилий на -а/-я
    родительный и дательный часто совпадают по окончанию — это ожидаемо,
    не баг).
    Неклассическое ФИО или недоступный petrovich — возвращается
    `_fio_to_initials(full_name)` без падежа (лучше неизменённые инициалы,
    чем выдуманное окончание).

    Владелец (28.10.2026, баг «Титов Р.А.» не склонялось в приказе —
    полного ФИО не было, пришла уже сокращённая строка «Фамилия И.О.»):
    когда на вход приходит РОВНО «Фамилия И.О.»/«Фамилия И.» (2 слова,
    второе — инициалы с точками, без отчества — отличить от отчества
    нельзя, пол неизвестен), склоняем хотя бы фамилию — пол угадываем по
    типичным окончаниям женских фамилий (-ова/-ева/-ина/-ая и т.п., см.
    `_FEMALE_SURNAME_ENDINGS`), иначе мужской (большинство русских фамилий
    разных родов и так различаются в именительном падеже — см. docstring
    `_to_case_fio` про общий механизм). Инициалы не трогаем — это не ФИО,
    а уже сокращение.
    """
    if not full_name or not full_name.strip():
        return full_name
    from .formatting import _fio_to_initials
    nominative_initials = _fio_to_initials(full_name)

    parts = full_name.strip().split()
    ogly_kyzy = {'оглы', 'кызы'}
    is_classic = (len(parts) == 3 and _is_patronymic(parts[2])) or (
        len(parts) == 4 and parts[3].lower() in ogly_kyzy
    )

    if not is_classic:
        if len(parts) == 2 and _looks_like_initials_token(parts[1]):
            # `_fio_to_initials` выше считает исходную строку ещё НЕ
            # сокращённым ФИО — на 2 словах берёт только первую букву
            # второго слова («Титов Р.А.» → «Титов Р.», теряя «.А.»).
            # Здесь вход уже «Фамилия И.О.» — инициалы берём как есть,
            # склоняем только фамилию.
            return _decline_bare_surname_initials(parts[0], parts[1], case_name)
        return nominative_initials

    petro_pack = _get_petro()
    if not petro_pack:
        return nominative_initials

    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name)
    try:
        gender = Gender.FEMALE if parts[2].lower().endswith(('вна', 'чна', 'ична')) else Gender.MALE
        last_declined = _decline_name_part(petro, 'lastname', parts[0], case, case_name, gender)
    except Exception:
        return nominative_initials

    nom_words = nominative_initials.split(maxsplit=1)
    if len(nom_words) == 2:
        out = f"{last_declined} {nom_words[1]}"
    else:
        out = last_declined
    if parts[0][0].isupper():
        out = out[0].upper() + out[1:]
    return out


def _decline_bare_surname_initials(surname: str, initials_token: str, case_name: str) -> str:
    """Склоняет только ФАМИЛИЮ из уже сокращённого «Фамилия И.О.» — см.
    докстринг `_to_case_fio_initials` (ветка bare-surname). Пол неизвестен
    (нет отчества) — угадывается по окончанию фамилии. `initials_token` —
    второе слово как есть («Р.А.»/«Р.»), не трогается."""
    nominative = f"{surname} {initials_token}"
    petro_pack = _get_petro()
    if not petro_pack:
        return nominative
    petro, Case, Gender = petro_pack
    case = getattr(Case, case_name)
    gender = Gender.FEMALE if surname.lower().endswith(_FEMALE_SURNAME_ENDINGS) else Gender.MALE
    try:
        declined = _decline_name_part(petro, 'lastname', surname, case, case_name, gender)
    except Exception:
        return nominative
    if surname[0].isupper():
        declined = declined[0].upper() + declined[1:]
    return f"{declined} {initials_token}"


def _to_gen_fio_initials(full_name: str) -> str:
    """«Фамилия И.О.» в родительном падеже — тонкая обёртка над
    `_to_case_fio_initials` (см. её докстринг)."""
    return _to_case_fio_initials(full_name, 'GENITIVE')


def _to_dat_fio_initials(full_name: str) -> str:
    """«Фамилия И.О.» в дательном падеже — тонкая обёртка над
    `_to_case_fio_initials` (см. её докстринг).

    «Артеева Анна Игоревна» → «Артеевой А.И.»
    """
    return _to_case_fio_initials(full_name, 'DATIVE')
