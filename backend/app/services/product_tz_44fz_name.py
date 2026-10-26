"""Чистка НАЗВАНИЯ товара и вырезание брендов из названия/значений — часть
ЕДИНСТВЕННОГО генератора ТЗ 44-ФЗ (app/services/product_tz_44fz.py,
ПРАВИЛО №6). Вынесено отдельным модулем по ПРАВИЛУ №5 (разрезание
product_tz_44fz.py, 809 строк, QA-ревью 26.10.2026, п.3).

Правила (ревью v1-v3, 26.10.2026 — см. докстринг product_tz_44fz.py):
  - Из названия убираются ВСЕ латинские слова/коды модели, кроме белого
    списка технических терминов и размерных токенов (20А, 65", d40х45см).
  - Голые числа без единицы убираются ТОЛЬКО если идут СРАЗУ за вырезанным
    бренд/модель-токеном (цепочкой), а не "где угодно после первого
    удаления" (ревью v3, п.C).
  - Бренд вырезается границей по слову (дефис — часть слова, не граница),
    РЕГИСТРОЗАВИСИМО — КРОМЕ латинских брендов длиной >= 4 символов, которые
    вырезаются регистронезависимо как ПРЕФИКС слова ("eskaro" находит
    "Eskarocolor") — QA-ревью 26.10.2026 (после v3), п.2.
  - Цвета/материалы/страны/общие слова (STOP_BRAND_WORDS) никогда не
    считаются брендом, даже если затесались в характеристику "Бренд/
    Производитель" у кого-то в каталоге.
"""
import re
from typing import Optional

from app.services.product_tz_44fz_rules import (
    BRAND_CHARACTERISTIC_NAME_KEYWORDS,
    MANUFACTURER_KEYWORD_FALSE_POSITIVE_RE,
    STOP_BRAND_WORDS,
    WHITELIST_TECH_NAME_WORDS,
)

_LT_CODE_RE = re.compile(r"\(\s*LT-\d+\s*\)", re.IGNORECASE)

# Единицы-слова — "NUM <слово>" с пробелом (не одним токеном, как
# размерные "20А") всё равно НЕ голое число для чистки названия: "20
# литров", "2 т", "2 шт." и т.п.
_UNIT_WORDS = frozenset({
    "л", "литр", "литра", "литров", "шт", "шт.", "кг", "г", "мм", "см",
    "м", "т", "вт", "гц", "дюйм", "дюйма", "дюймов", "мл", "мин", "сек",
    "ч", "см.",
    # Электрические/физические однобуквенные единицы, идущие отдельным
    # токеном после числа через пробел ("800 А", "220 В", "100 Ом").
    "а", "в", "ом", "па", "дб", "кв", "мпа", "кпа", "вар",
})
# "N в N" (комплектность, "3 в 1") — числа внутри этой фразы в названии не
# трогаем, даже если дальше по строке что-то вырезалось.
_COUNT_PHRASE_RE = re.compile(r"\b\d+\s+в\s+\d+\b")

# Токен-"размер" в наименовании (20А, 4,5кА, 5л, 65", 1.5м, d40х45см) — не
# вырезается как латинский код, даже если содержит латинскую букву ('d' —
# диаметр) или цифры+буквы вместе. (?=.*[^\d]) требует хоть один НЕ-цифровой
# символ — иначе под этот паттерн подошло бы и голое число "410".
_SIZE_TOKEN_RE = re.compile(
    r'^(?=.*[^\d])d?\d+(?:[.,]\d+)?(?:[xх×]\d+(?:[.,]\d+)?){0,2}(?:[a-zA-Zа-яёА-ЯЁ]{1,4}|")?$'
)
_IP_RATING_RE = re.compile(r"^IP\d{1,3}$")
_DIMENSION_SEPARATOR_RE = re.compile(r"^[xх×]$", re.IGNORECASE)
_DUPLICATE_PAREN_RE = re.compile(r"(?P<w>\S+)\s*\(\s*(?P=w)\s*\)")
_QUOTED_BRAND_RE = re.compile(r'[«"]([^»"]{2,40})[»"]')

# Прод-ревью 26.10.2026 (п.A4): токен-ток автоматического выключателя
# (буква характеристики кривой + число + опциональная "A"/"А") — "C50A",
# "B16", "D32" — технический, не бренд/модель, оставляем даже когда он
# слит через "/" с другими техническими под-токенами ("C50A/3п/").
_BREAKER_CURVE_RE = re.compile(r"^[A-Za-zА-Яа-я]{1,2}\d{1,4}[AА]?$")

# Прод-ревью 26.10.2026 (п.2, пятый заход): "d=7.5", "D=10", "L=2м", "h=30" —
# буква-обозначение размера (диаметр/длина/высота) через "=", технический
# токен, не бренд/модель.
_LETTER_EQ_NUM_RE = re.compile(
    r"^[A-Za-zА-Яа-яЁё]=\d+(?:[.,]\d+)?(?:[a-zA-Zа-яёА-ЯЁ]{1,4})?$"
)

# Прод-ревью 26.10.2026 (п.3, пятый заход): класс огнетушителя/пожара —
# буквы ТОЛЬКО из {A,B,C,D,E,F} (латиница или кириллица А/В/С/Е, визуально
# совпадающая с латиницей), 1-6 букв, ОБЯЗАТЕЛЬНОЕ "-цифры" (без него
# одинокая буква-модели типа "TV A 65" ложно считается классом пожара —
# QA после первой версии regex) и необязательная "(буква)" ("ABCE-01(А)",
# "ОП-2(3)" — тут "ОП" кириллица вне набора, см. отдельную ветку в
# _classify_name_token для "ОП-2(3)", которая остаётся через общий путь
# "не-латиница => keep"). Сравнение регистронезависимое.
_FIRE_CLASS_RE = re.compile(
    r"^[ABCDEFАВСЕ]{1,6}-\d+(?:\(?[ABCDEFАВСЕ]\)?)?$", re.IGNORECASE
)

# Прод-ревью 26.10.2026 (п.A5): незакрытая скобка в КОНЦЕ названия (срез
# исходных данных каталога типа "... (Севкабель С-Петерб") — всё от "(" до
# конца строки отбрасываем целиком, это не содержательная часть названия.
_UNCLOSED_TRAILING_PAREN_RE = re.compile(r"\([^()]*$")
# Скобка, в которой после вырезания бренда/токена осталось ≤1 слово
# ("(типа" из "(типа ESFR)" после удаления ESFR) — скобка удаляется ВМЕСТЕ
# с этим остатком, не только пустая пара.
_SPARSE_PAREN_RE = re.compile(r"\(([^()]*)\)")

# Границы бренда: дефис — ЧАСТЬ слова ("алюминий-цинк" не должен терять
# половину из-за бренда "Цинк") — левая/правая граница — НЕ \w И НЕ дефис.
_BRAND_LEFT = r"(?<![\w-])"
_BRAND_RIGHT = r"(?![\w-])"
# Латинский бренд >= 4 символов — вырезается КАК ПРЕФИКС слова,
# регистронезависимо ("eskaro" находит "Eskarocolor"); кириллический или
# короткий (< 4) — только как целое слово, с учётом регистра.
_LATIN_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*$")


def _is_stop_brand_word(word: str) -> bool:
    return (word or "").strip().lower() in STOP_BRAND_WORDS


def _is_latin_prefix_brand(word: str) -> bool:
    return bool(_LATIN_ONLY_RE.match(word)) and len(word) >= 4


def brand_word_pattern(word: str) -> "re.Pattern":
    """ЕДИНСТВЕННОЕ место, решающее, как вырезать ОДНО бренд-слово
    (manufacturer/article/локальный бренд характеристики) — используется
    и для названия, и для значений характеристик (ПРАВИЛО №6, второй
    такой выбор где-то ещё не заводить)."""
    word = word.strip()
    if _is_latin_prefix_brand(word):
        return re.compile(_BRAND_LEFT + re.escape(word), re.IGNORECASE)
    return re.compile(_BRAND_LEFT + re.escape(word) + _BRAND_RIGHT)


def brand_word_sub(text: str, word: str) -> tuple:
    if not word or not word.strip():
        return text, False
    pattern = brand_word_pattern(word)
    new_text, count = pattern.subn(" ", text)
    return new_text, count > 0


_GLOBAL_BRAND_PATTERN_CACHE: dict = {}


def _global_brand_pattern(brands):
    """Компилирует ОДИН alternation-паттерн на весь каталожный набор брендов
    (собирает вызывающий — см. product_tz_44fz_brands.py) и кеширует его НА
    ВРЕМЯ ЖИЗНИ процесса/запуска скрипта. Кеш ключуется СОДЕРЖИМЫМ набора
    (frozenset хешируем по содержимому), а не id(brands) — id() может
    совпасть у двух РАЗНЫХ короткоживущих frozenset-объектов после сборки
    мусора (классическая ловушка id()-кеша в CPython).

    Латинские бренды длиной >= 4 — ОТДЕЛЬНАЯ группа альтернатив с scoped
    inline-флагом регистронезависимости (?i:...) и БЕЗ правой границы
    (префиксное совпадение, "eskaro" находит "Eskarocolor"); остальные —
    как целое слово, с учётом регистра (как записано в каталоге)."""
    if not brands:
        return None
    key = brands if isinstance(brands, frozenset) else frozenset(brands)
    cached = _GLOBAL_BRAND_PATTERN_CACHE.get(key)
    if cached is not None:
        return cached

    exact_words = []
    prefix_words = []
    for b in brands:
        if not b or len(b) < 3 or _is_stop_brand_word(b):
            continue
        if _is_latin_prefix_brand(b):
            prefix_words.append(b)
        else:
            exact_words.append(b)

    parts = []
    if exact_words:
        escaped = sorted((re.escape(w) for w in exact_words), key=len, reverse=True)
        parts.append(_BRAND_LEFT + "(?:" + "|".join(escaped) + ")" + _BRAND_RIGHT)
    if prefix_words:
        escaped = sorted((re.escape(w) for w in prefix_words), key=len, reverse=True)
        parts.append("(?i:" + _BRAND_LEFT + "(?:" + "|".join(escaped) + "))")

    pattern = re.compile("|".join(parts)) if parts else None
    _GLOBAL_BRAND_PATTERN_CACHE[key] = pattern
    return pattern


def _collect_local_brand_words(characteristics, manufacturer, article):
    """Собирает бренд-слова ТОВАРА (не весь каталог — см. _global_brand_pattern)
    для вырезания из наименования/значений. Для характеристик «Бренд/
    Производитель/...» (fallback-разбор description часто отдаёт значение
    вида "СОРОКИН (ЗАО ТД «Сорокин»)") добавляем ещё первое слово значения
    и текст в кавычках — иначе полная строка не совпадёт с коротким
    упоминанием бренда в названии ("... канистра 10л Сорокин")."""
    words = set()
    if manufacturer and manufacturer.strip() and not _is_stop_brand_word(manufacturer):
        words.add(manufacturer.strip())
    if article and article.strip():
        words.add(article.strip())
    for item in characteristics or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").lower()
        # "производител" — ЕДИНСТВЕННЫЙ общий regex MANUFACTURER_KEYWORD_
        # FALSE_POSITIVE_RE (product_tz_44fz_rules.py, ПРАВИЛО №6), иначе
        # "Коэффициент производительности" ложно читается как характеристика
        # бренда/производителя (прод-ревью 26.10.2026, п.A7) и собственное
        # числовое значение характеристики улетает в local_brand_words.
        is_brand_characteristic = MANUFACTURER_KEYWORD_FALSE_POSITIVE_RE.search(name) or any(
            kw in name for kw in BRAND_CHARACTERISTIC_NAME_KEYWORDS if kw != "производител"
        )
        if is_brand_characteristic:
            value = (item.get("value") or "").strip()
            if value and len(value) >= 2 and not _is_stop_brand_word(value):
                words.add(value)
                first_word = value.split()[0].strip(",.()«»\"'") if value.split() else ""
                if first_word and len(first_word) >= 3 and not _is_stop_brand_word(first_word):
                    words.add(first_word)
                for qm in _QUOTED_BRAND_RE.finditer(value):
                    quoted = qm.group(1).strip()
                    if len(quoted) >= 3 and not _is_stop_brand_word(quoted):
                        words.add(quoted)
    return [w for w in words if w]


def _strip_empty_brackets(text: str) -> str:
    """Опустевшие скобки/кавычки, оставшиеся ПОСЛЕ вырезания бренда целым
    словом ("детектор « » v.4" → "детектор v.4") — убираем пустую пару
    целиком; с границами по слову (не подстрокой) обычные составные слова
    типа "алюминий-цинк" до этого не доходят."""
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[«\"']\s*[»\"']", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _strip_brand_mentions(value: str, local_words, global_brands) -> tuple:
    """Вырезает бренд-слова ИЗ ЗНАЧЕНИЯ характеристики (не названия) — те
    же local_words/global_brands, что и для названия, та же функция выбора
    паттерна (brand_word_pattern/_global_brand_pattern), ПРАВИЛО №6."""
    removed = False
    text = value
    for w in local_words:
        text_after, changed = brand_word_sub(text, w)
        if changed:
            text = text_after
            removed = True
    global_pattern = _global_brand_pattern(global_brands)
    if global_pattern and global_pattern.search(text):
        text = global_pattern.sub(" ", text)
        removed = True
    if removed:
        text = _strip_empty_brackets(text)
        text = re.sub(r"\s{2,}", " ", text).strip(" ,.-")
    return text, removed


# ------------------------------------------------------- наименование ----

def _is_keepable_tech_subpart(sub: str) -> bool:
    """Один под-токен слитой через "/" технической записи ("C50A/3п/") —
    пустой хвост от висящего слэша, белый список, размерный токен или
    буква-кривая+число (см. _BREAKER_CURVE_RE) — технический, не брендовый."""
    if not sub:
        return True
    upper = sub.upper()
    if upper in WHITELIST_TECH_NAME_WORDS or _IP_RATING_RE.match(upper):
        return True
    if _SIZE_TOKEN_RE.match(sub):
        return True
    if _BREAKER_CURVE_RE.match(sub):
        return True
    return False


def _classify_name_token(core: str) -> str:
    # Одинокое "x"/"х"/"×" между двумя числами ("32 x 38") — разделитель
    # размеров, не латинское слово-код.
    if _DIMENSION_SEPARATOR_RE.match(core):
        return "keep"
    upper = core.upper()
    if upper in WHITELIST_TECH_NAME_WORDS or _IP_RATING_RE.match(upper):
        return "keep"
    # Составное слово типа "Din-рейку"/"USB-кабель" — технический термин
    # внутри дефисного/слэшевого составного токена тоже оставляем ВЕСЬ
    # токен целиком (не разбиваем его), а не только чистое "Din".
    if any(part.upper() in WHITELIST_TECH_NAME_WORDS for part in re.split(r"[-/]", core) if part):
        return "keep"
    if _SIZE_TOKEN_RE.match(core):
        return "keep"
    if _LETTER_EQ_NUM_RE.match(core):
        return "keep"
    if _FIRE_CLASS_RE.match(core):
        return "keep"
    # Слитая через "/" запись из нескольких технических под-токенов
    # ("C50A/3п/", "3P/50А") — держим целиком, если ВСЕ под-токены (кроме
    # пустых хвостов от висящего слэша) технические (п.A4).
    if "/" in core:
        sub_parts = core.split("/")
        if any(sub_parts) and all(_is_keepable_tech_subpart(p) for p in sub_parts):
            return "keep"
    has_latin = bool(re.search(r"[A-Za-z]", core))
    if not has_latin:
        if re.fullmatch(r"\d{1,4}", core):
            return "bare_number"
        if re.fullmatch(r"\d{5,}", core):
            return "remove"  # длинный каталожный номер без единицы
        return "keep"
    return "remove"  # латинское слово/код модели — не из белого списка/не размер


def _filter_name_tokens(text: str, any_removed: bool = False) -> tuple:
    """Убирает латинские слова/модели из наименования, оставляя белый
    список технических терминов и размерные токены. Возвращает
    (strict_text, lenient_text, removed_tokens):
      - strict_text — "голые" числа без единицы ТОЖЕ убраны, но ТОЛЬКО если
        идут СРАЗУ за вырезанным токеном (цепочкой: "A 65 2026" → оба числа
        после "A"; "STELS, двухсторонний 32 x 38" не теряет "32 x 38", т.к.
        между STELS и этими числами есть настоящее слово) — кроме "N в N"
        и "NUM <слово-единица>" (20 литров, 2 т).
      - lenient_text — числа НЕ убираются (более мягкий вариант) —
        подстраховка: если после strict_text осталось < 2 слов, лучше
        вернуть lenient_text (бренды всё равно вырезаны), чем откатываться
        к ПОЛНОСТЬЮ исходному названию с брендом внутри.
    removed_tokens нужны вызывающему, чтобы вырезать те же бренд/
    модель-коды из ЗНАЧЕНИЙ характеристик этого же товара."""
    protected = {}

    def _protect(m):
        key = f"{len(protected)}"
        protected[key] = m.group(0)
        return key

    protected_text = _COUNT_PHRASE_RE.sub(_protect, text)
    tokens = re.findall(r"\S+|\s+", protected_text)
    out_strict = []
    out_lenient = []
    removed_tokens = []
    # chain_removed — сбрасывается в False НА ЛЮБОМ "оставленном" токене
    # (не висит до конца строки) — "голое" число убирается ТОЛЬКО если оно
    # идёт СРАЗУ за вырезанным бренд/модель-кодом.
    chain_removed = any_removed
    prev_model_prefix = False
    for idx, tok in enumerate(tokens):
        if tok.isspace():
            out_strict.append(tok)
            out_lenient.append(tok)
            continue
        core = tok.strip(",.;:()[]{}'")
        if not core:
            out_strict.append(tok)
            out_lenient.append(tok)
            chain_removed = False
            continue
        if core in protected:
            out_strict.append(tok)
            out_lenient.append(tok)
            prev_model_prefix = False
            chain_removed = False
            continue
        cls = _classify_name_token(core)
        if cls == "remove":
            prev_model_prefix = bool(re.fullmatch(r"[a-z]{2,6}", core))
            chain_removed = True
            if re.search(r"[A-Za-z]", core) and len(core) >= 3:
                removed_tokens.append(core)
            continue
        if cls == "bare_number":
            out_lenient.append(tok)
            if prev_model_prefix:
                prev_model_prefix = False
                continue
            # "NUM <ед.слово>" (с пробелом, не одним токеном) — заглядываем
            # на следующий непустой токен; число защищено даже посреди
            # цепочки удалений.
            next_core = None
            for nxt in tokens[idx + 1:]:
                if nxt.isspace():
                    continue
                next_core = nxt.strip(",.;:()[]{}'").lower()
                break
            if next_core in _UNIT_WORDS:
                out_strict.append(tok)
                prev_model_prefix = False
                chain_removed = False
                continue
            if chain_removed:
                # "Голое" число — остаток цепочки удалений (продолжаем её,
                # следующее такое же число тоже считается хвостом).
                continue
            out_strict.append(tok)
            prev_model_prefix = False
            continue
        out_strict.append(tok)
        out_lenient.append(tok)
        prev_model_prefix = False
        chain_removed = False

    def _restore(parts):
        joined = "".join(parts)
        for key, original_fragment in protected.items():
            joined = joined.replace(key, original_fragment)
        return joined

    return _restore(out_strict), _restore(out_lenient), removed_tokens


def _clean_name(name: str, characteristics, manufacturer, article, brands) -> tuple:
    """Возвращает (очищенное_наименование, needs_review, removed_tokens).
    needs_review=True, если после чистки осталось меньше 2 слов — тогда
    возвращается исходное имя без изменений, владельцу нужно проверить
    руками (removed_tokens в этом случае — пустой список)."""
    original = (name or "").strip()
    # (LT-N) — внутренний суффикс лота этого каталога, убираем ДАЖЕ из
    # "исходного" имени, которое вернётся при needs_review — это не
    # содержательная часть названия ни в каком случае.
    original_without_lt = _LT_CODE_RE.sub(" ", original)
    original_without_lt = re.sub(r"\s{2,}", " ", original_without_lt).strip(" ,.-")
    text = original_without_lt

    # upstream_removed — что-то уже вырезалось ДО токенизации (бренд/
    # производитель/артикул, через alternation-паттерн) — отдельно
    # отслеживаем, чтобы _filter_name_tokens тоже начал "глотать" голые
    # числа-хвосты сразу после такого удаления.
    upstream_removed = False

    text_after, changed = brand_word_sub(text, manufacturer or "")
    upstream_removed = upstream_removed or changed
    text = text_after
    text_after, changed = brand_word_sub(text, article or "")
    upstream_removed = upstream_removed or changed
    text = text_after
    local_words = _collect_local_brand_words(characteristics, None, None)
    for w in local_words:
        text_after, changed = brand_word_sub(text, w)
        upstream_removed = upstream_removed or changed
        text = text_after
    global_pattern = _global_brand_pattern(brands)
    if global_pattern:
        text_after = global_pattern.sub(" ", text)
        upstream_removed = upstream_removed or (text_after != text)
        text = text_after

    strict_text, lenient_text, removed_tokens = _filter_name_tokens(text, any_removed=upstream_removed)

    def _postprocess(candidate: str) -> str:
        # Дубль "СЛОВО (СЛОВО)" ("20L (20L)" → "20L") — ДО удаления слэша,
        # который в "12/24 В" НАДО сохранить (слэш между двумя числами без
        # пробелов не трогаем).
        candidate = _DUPLICATE_PAREN_RE.sub(r"\g<w>", candidate)
        candidate = _UNCLOSED_TRAILING_PAREN_RE.sub("", candidate)

        def _drop_sparse_paren(m):
            words = [w for w in m.group(1).strip().split() if w]
            # Удаляем скобку ТОЛЬКО если единственное оставшееся слово —
            # обычное буквенное слово-связка ("типа", "марки") длиной >= 2,
            # похожее на остаток ПОСЛЕ вырезанного бренда/токена. Короткие
            # буквенно-числовые коды ("3", "А", "41 HRC" — последнее не
            # попадает сюда, т.к. это 2 слова) НЕ трогаем — "(3)"/"(А)" в
            # "ОП-2(3), ABCE-01(А)" это паспортные обозначения, не остаток.
            if len(words) == 1 and words[0].isalpha() and len(words[0]) >= 2:
                return ""
            return m.group(0)

        candidate = _SPARSE_PAREN_RE.sub(_drop_sparse_paren, candidate)
        candidate = _strip_empty_brackets(candidate)
        # Одинокий слэш, повисший ПОСЛЕ вырезанного слова ("AM/ Micro-B" →
        # "AM/" после удаления Micro-B) — убираем ТОЛЬКО если граничит с
        # пробелом с какой-то стороны.
        candidate = re.sub(r"(?<=\s)/|/(?=\s)", "", candidate)
        candidate = re.sub(r"(?<=[\s,])-(?=[\s,])", " ", candidate)  # одинокое тире после вырезанного слова
        candidate = re.sub(r"\s+,", ",", candidate)
        candidate = re.sub(r",{2,}", ",", candidate)
        candidate = re.sub(r"\s{2,}", " ", candidate).strip(" ,.-/")
        return candidate

    strict_text = _postprocess(strict_text)
    if len([w for w in strict_text.split() if w]) >= 2:
        return strict_text, False, removed_tokens

    # Строгий вариант (без "голых" чисел) ушёл меньше 2 слов — не
    # откатываем ВСЁ до исходного названия с брендом внутри (бренд уже
    # легитимно вырезан выше): пробуем мягкий вариант (числа оставлены), и
    # только если он ТОЖЕ короче 2 слов — показываем needs_review с
    # полностью исходным именем.
    lenient_text = _postprocess(lenient_text)
    if len([w for w in lenient_text.split() if w]) >= 2:
        return lenient_text, False, removed_tokens

    return original_without_lt, True, []


def _resolve_name_source(name: Optional[str], characteristics: Optional[list]) -> str:
    """Характеристика "Наименование" (если есть, с непустым значением) —
    источник имени ВМЕСТО Product.name; сама она исключена из строк
    параметров через EXCLUDED_CHARACTERISTIC_NAME_KEYWORDS ("наименован")."""
    for item in characteristics or []:
        if not isinstance(item, dict):
            continue
        item_name = (item.get("name") or "").strip().lower()
        if item_name == "наименование":
            value = (item.get("value") or "").strip()
            if value:
                return value
    return name or ""
