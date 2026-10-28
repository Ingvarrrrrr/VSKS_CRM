"""Разбор поисковой фразы пользователя («как помнит», этап 0 — владелец,
28.10.2026): «болгарка макита 125 с регулировкой», «огнетушитель порошковый
4 кг», «масло лукойл 5w40 4л» — с опечатками, лишними словами, без артикулов.

ПРАВИЛО №6 — второй разбор названия НЕ пишем: вся токенизация/словари
(бренд, цифровые токены-индекс модели, вид товара, величины с единицей
измерения) берутся из app.services.product_name_signature.build_signature —
того же механизма, что сводит товары разных магазинов между собой (см.
докстринг там). Этот модуль только раскладывает результат build_signature
на required/optional токены для ПОИСКА (а не для сравнения «тот же товар»)
и нормализует отображение величины/модели для равенства «4л»="4 л",
«5w40»="5W-40".

Словарь брендов (app.services.build_signature(..., brand_dictionary=...),
см. docstring product_name_signature.py): реальная реализация —
tools/catalog_enrich/brand_dictionary.BrandDictionary — строится из offline
JSON-выгрузок каталогов (разбор файлов на диске), не из БД, и не рассчитана
на вызов на каждый онлайн-запрос поиска (пересборка по файлам — не для
горячего пути HTTP-запроса). Поэтому здесь — ОТДЕЛЬНЫЙ, дёшевый источник:
get_manufacturer_brand_dictionary(db) кэширует DISTINCT Product.manufacturer
(отфильтрованный is_bogus_manufacturer, тот же гейт качества, что в
build_signature) в памяти процесса на BRAND_CACHE_TTL_SECONDS — ВТОРОЙ
«угадайкой бренда» это не считается (Правило №6): find_in_name там тоже
ищет целым словом через fold_brand_or_code, просто источник слов — manufacturer
из своей БД, а не чужие офлайн-файлы. parse_query() сам по себе синхронный
и чистый (без похода в БД) — вызывающая сторона передаёт brand_dictionary
по желанию (как и у build_signature); без него required-токен «бренд»
просто не определяется (specific по бренду не сработает), что для «этапа 0»
допустимо — получение/проводка словаря в search_products() — следующий шаг
(ПРИОСТАНОВЛЕН владельцем 28.10.2026, см. TASKS.md)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import bindparam, select, String, text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer
from app.services.brand_code_fold import fold_brand_or_code
from app.services.product_name_signature import (
    _brand_compare_key,
    _HAS_DIGIT_RE,
    _PRODUCT_TYPE_WINDOW,
    _split_words,
    _STOPWORDS as _PREPOSITION_STOPWORDS,
    build_signature,
)
from app.services.product_name_signature_props import (
    PRODUCT_TYPE_PHRASES,
    PRODUCT_TYPE_WORDS,
    UNIT_WORDS,
)

# Таблицы единиц — ПЕРЕИСПОЛЬЗУЕМ те же, что build_signature считает величины
# «прямо в названии» (_extract_name_quantities) — Правило №6, второй список
# единиц для «4л»/«4 кг» не завожено отдельно.
_MASS_TO_GRAMS = {"мг": 0.001, "г": 1.0, "кг": 1000.0, "т": 1_000_000.0}
_LENGTH_TO_MM = {"мм": 1.0, "см": 10.0, "дм": 100.0, "м": 1000.0, "км": 1_000_000.0}
_VOLUME_TO_ML = {"мл": 1.0, "л": 1000.0}
_VA_TO_VA = {"ва": 1.0, "ква": 1000.0}
_CAPACITY_TO_MAH = {"мач": 1.0, "ач": 1000.0}
_ENERGY_TO_J = {"дж": 1.0}
_POWER_TO_W = {"вт": 1.0, "квт": 1000.0, "мвт": 1_000_000.0}

_QUANTITY_UNIT_TABLES = {
    "мощность": _POWER_TO_W,
    "масса": _MASS_TO_GRAMS,
    "объём": _VOLUME_TO_ML,
    "длина": _LENGTH_TO_MM,
    "полная мощность": _VA_TO_VA,
    "ёмкость АКБ": _CAPACITY_TO_MAH,
    "энергия удара": _ENERGY_TO_J,
}


@dataclass
class ParsedQuery:
    """Результат разбора поисковой фразы.

    required — токены, без которых товар не может быть тем, что искали
    (вид товара канонический/бренд/модель-цифровой токен/величина с
    единицей, уже нормализованные); optional — прочие значимые слова
    (поднимают ранг, не исключают); dropped_stopwords — предлоги/союзы,
    выброшенные из разбора; specific — есть бренд ИЛИ цифровой/модельный
    токен ИЛИ величина с единицей (одного вида товара недостаточно, см.
    docstring parse_query)."""

    raw: str
    required: list = field(default_factory=list)
    optional: list = field(default_factory=list)
    dropped_stopwords: list = field(default_factory=list)
    specific: bool = False
    brand: Optional[str] = None
    product_type: Optional[str] = None
    # type_literal — ТО ЖЕ значение, что добавлено в required как «вид
    # товара» (литеральное слово/фраза ИЗ ЗАПРОСА, см. комментарий у
    # type_literal в parse_query ниже) — выделено отдельным полем, чтобы
    # product_search.py мог НАЙТИ этот конкретный required-токен и
    # заменить его на OR-группу всех написаний вида (product_type_synonyms)
    # без угадывания по совпадению строки (владелец, 28.10.2026, п.1
    # задания «поиск как помнит», доработка — синонимы вида товара)."""
    type_literal: Optional[str] = None


_MODEL_VISCOSITY_RE = re.compile(r"^(\d+)([a-zа-яё]+)(\d+)$")


def _normalize_model_token(tok: str) -> str:
    """«5w40» → «5W-40» (вязкость масла — буква-разделитель между двумя
    числами индекса модели, владелец, 28.10.2026). Остальные цифровые
    токены (чистые коды без буквы между двумя числами) возвращаются как
    есть — build_signature уже привёл их к одному нормализованному виду
    (нижний регистр, без разделителей)."""
    m = _MODEL_VISCOSITY_RE.match(tok)
    if m:
        return f"{m.group(1)}{m.group(2).upper()}-{m.group(3)}"
    return tok


def _fmt_num(num: float) -> str:
    r = round(num, 3)
    if r == int(r):
        return str(int(r))
    return f"{r:g}".replace(".", ",")


def _format_quantity(group: str, value: float) -> str:
    """Величина в базовой единице (из build_signature._extract_name_
    quantities, см. docstring модуля) → «человеческое» написание: «4л»/
    «4 л» → 4000 мл → «4 л» (крупнейшая единица, в которой значение >= 1,
    иначе — самая мелкая единица таблицы)."""
    table = _QUANTITY_UNIT_TABLES.get(group)
    if not table:
        return _fmt_num(value)
    candidates = sorted(table.items(), key=lambda kv: -kv[1])
    chosen_unit, chosen_factor = candidates[-1]
    for unit, factor in candidates:
        if value / factor >= 1:
            chosen_unit, chosen_factor = unit, factor
            break
    return f"{_fmt_num(value / chosen_factor)} {chosen_unit}"


def _product_type_phrase_words(product_type: str, folded_text: str) -> set:
    """Слова МНОГОсловной фразы словаря (PRODUCT_TYPE_PHRASES), давшей
    sig.product_type, — чтобы исключить ВСЕ слова фразы (не только одно) из
    optional ниже (см. docstring parse_query, почему нужно отдельно от
    PRODUCT_TYPE_WORDS — там один токен, тут несколько)."""
    out: set = set()
    for phrase, canon in PRODUCT_TYPE_PHRASES.items():
        if canon == product_type and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded_text):
            out.update(phrase.split())
    return out


def parse_query(q: Optional[str], brand_dictionary=None) -> ParsedQuery:
    """Разбирает поисковую фразу на required/optional токены поверх
    build_signature() (Правило №6 — см. docstring модуля). brand_dictionary —
    тот же контракт, что у build_signature (`.find_in_name(name) ->
    str | None`); можно не передавать — тогда бренд не определяется из
    текста фразы (specific по бренду не сработает, остальное — работает)."""
    raw = (q or "").strip()
    if not raw:
        return ParsedQuery(raw=raw)

    sig = build_signature({"name": raw}, brand_dictionary)

    required: list = []
    seen_required: set = set()

    def add_required(val: Optional[str]) -> None:
        if val and val not in seen_required:
            seen_required.add(val)
            required.append(val)

    words = _split_words(raw)
    folded_text = fold_brand_or_code(raw)

    # Вид товара — required несёт ЛИТЕРАЛЬНОЕ слово(а) ИЗ ФРАЗЫ, НЕ
    # канонический вид из словаря (владелец, 28.10.2026, найдено при
    # подключении встроенного полнотекстового поиска PostgreSQL):
    # product_name_signature.PRODUCT_TYPE_WORDS канонизирует синонимы ОДНОГО
    # вида для СРАВНЕНИЯ «тот же товар» ("болгарка"="шлифмашина"="УШМ") —
    # обратный эффект для ПОИСКА по тексту каталога: само название товара
    # обычно содержит ОДНО из этих слов (например, разговорное "болгарка"),
    # канонический термин в название может не попасть вовсе, и tsquery по
    # канону не найдёт ничего. sig.product_type (канон) остаётся в
    # ParsedQuery.product_type как метаданные (specific/отображение), но в
    # required идёт то слово, что написал пользователь.
    phrase_words: set = set()
    type_literal: Optional[str] = None
    if sig.product_type:
        phrase_words = _product_type_phrase_words(sig.product_type, folded_text)
        if phrase_words:
            type_literal = " ".join(w for w in words if w in phrase_words)
        else:
            for w in words:
                if PRODUCT_TYPE_WORDS.get(w) == sig.product_type:
                    type_literal = w
                    break

    add_required(sig.brand)
    add_required(type_literal)
    for tok in sorted(sig.digit_tokens):
        add_required(_normalize_model_token(tok))
    for group, values in sig.name_qty.items():
        for v in sorted(values):
            add_required(_format_quantity(group, v))

    optional: list = []
    dropped: list = []
    for w in words:
        wl = w.lower()
        if wl in _PREPOSITION_STOPWORDS:
            dropped.append(w)
            continue
        if _HAS_DIGIT_RE.search(w):
            # уже учтено через digit_tokens/name_qty выше (единицы/класс
            # пожара вырезаны из слов ДО этого места самим _split_words).
            continue
        if sig.brand_fold and _brand_compare_key(w) == sig.brand_fold:
            continue
        if sig.product_type and (PRODUCT_TYPE_WORDS.get(w) == sig.product_type or w in phrase_words):
            continue
        optional.append(w)

    specific = bool(sig.brand) or bool(sig.digit_tokens) or bool(sig.name_qty)

    return ParsedQuery(
        raw=raw,
        required=required,
        optional=optional,
        dropped_stopwords=dropped,
        specific=specific,
        brand=sig.brand,
        product_type=sig.product_type,
        type_literal=type_literal,
    )


# ---------------------------------------------------------------------------
# Синонимы вида товара для РАСШИРЕНИЯ поискового запроса (владелец,
# 28.10.2026, п.1 задания «поиск как помнит», доработка): «болгарка» и
# «УШМ»/«угловая шлифмашина» — ОДИН канонический вид в PRODUCT_TYPE_WORDS/
# PRODUCT_TYPE_PHRASES (Правило №6 — тот же словарь, что и у build_signature
# для сравнения «тот же товар», второй словарь видов не заводим), но для
# ПОИСКА по тексту каталога нужны ВСЕ написания этого вида (не только то,
# что ввёл пользователь) — товар может называться в каталоге любым из них.
# ---------------------------------------------------------------------------

def product_type_synonyms(product_type: Optional[str]) -> list[str]:
    """Все слова (PRODUCT_TYPE_WORDS) и фразы (PRODUCT_TYPE_PHRASES) из
    словаря, которые канонизируются в данный `product_type` — для
    product_search.py: tsquery по виду товара строится как OR этих
    написаний вместо ОДНОГО литерального слова из запроса. Пустой список —
    если product_type не передан или в словаре нет ни одной записи с таким
    каноном (защита от опечатки в вызывающем коде, не должно происходить
    на реальных данных — product_type всегда берётся из sig.product_type,
    который САМ построен из этого же словаря)."""
    if not product_type:
        return []
    out: set = set()
    for word, canon in PRODUCT_TYPE_WORDS.items():
        if canon == product_type:
            out.add(word)
    for phrase, canon in PRODUCT_TYPE_PHRASES.items():
        if canon == product_type:
            out.add(phrase)
    return sorted(out)


# ---------------------------------------------------------------------------
# Распознавание вида товара ПО СЛОВОФОРМЕ (владелец, 28.10.2026, QA-находка
# после доработки синонимов: "болгарка"→14, "болгарку"→2 — type_literal в
# parse_query() ищет ТОЧНОЕ слово из PRODUCT_TYPE_WORDS, "болгарку"/
# "болгарки"/"огнетушителя"/"рацию" (падежные формы) в словаре нет буквально,
# поэтому вид не распознаётся вовсе, OR-группа синонимов НЕ строится, и
# запрос уходит в общий "promoted" путь без расширения). ПРАВИЛО №6 — второй
# стеммер не пишем: используем ТОТ ЖЕ 'russian_stem' словарь Postgres, что
# и to_tsvector('russian', ...) в product_search.py (_FTS_DOC_SQL) — если
# стем словоформы запроса совпал со стемом слова из PRODUCT_TYPE_WORDS, вид
# товара распознан, даже когда буквального совпадения нет. Требует БД
# (ts_lexize — функция Postgres), поэтому синхронный parse_query() эту
# проверку не делает сам — отдельная async-функция, вызывается из
# product_search.search_products() ОДИН РАЗ, когда parse_query() вида не
# нашла (быстрый путь "нашли буквально" не трогаем лишним запросом).
# ---------------------------------------------------------------------------

_TYPE_STEM_CACHE_TTL_SECONDS = 30 * 60
_type_stem_cache: dict = {"index": None, "built_at": 0.0}


async def _get_type_stem_index(db: AsyncSession) -> dict:
    """stem(слово PRODUCT_TYPE_WORDS) → канонический вид — кэш в памяти
    процесса (тот же паттерн TTL, что у get_manufacturer_brand_dictionary
    выше): один SQL-запрос (unnest + ts_lexize по ВСЕМ словам словаря), не
    по запросу на слово. Коллизия стема (два разных слова с одним стемом,
    разные канон) — последнее в словаре побеждает, на реальном словаре не
    встречалось (словарь — одно слово на один канон почти всегда)."""
    now = time.monotonic()
    cached = _type_stem_cache["index"]
    if cached is not None and (now - _type_stem_cache["built_at"]) < _TYPE_STEM_CACHE_TTL_SECONDS:
        return cached

    words = sorted(PRODUCT_TYPE_WORDS.keys())
    stmt = sa_text(
        "SELECT w, (ts_lexize('russian_stem', w))[1] AS stem FROM unnest(:words) AS w"
    ).bindparams(bindparam("words", type_=PG_ARRAY(String)))
    rows = (await db.execute(stmt, {"words": words})).all()
    index: dict = {}
    for word, stem in rows:
        if stem:
            index[stem] = PRODUCT_TYPE_WORDS[word]
    _type_stem_cache["index"] = index
    _type_stem_cache["built_at"] = now
    return index


async def resolve_type_by_stem(db: AsyncSession, parsed: ParsedQuery) -> ParsedQuery:
    """Если parse_query() НЕ распознала вид товара буквально
    (parsed.product_type is None) — пробуем по СТЕМУ (см. docstring блока
    выше): слова исходной фразы (окно _PRODUCT_TYPE_WINDOW — то же, что у
    product_name_signature._extract_product_type, Правило №6 — то же
    окно, не второе) по очереди стемим и ищем в _get_type_stem_index.
    Первое совпадение — литеральное слово запроса переносится из optional
    в required (как type_literal), product_type проставляется каноном.
    Если parsed.product_type уже распознан (точным путём) — возвращает
    parsed БЕЗ ИЗМЕНЕНИЙ и БЕЗ похода в БД (быстрый путь не трогаем)."""
    if parsed.product_type is not None:
        return parsed

    words = _split_words(parsed.raw)[:_PRODUCT_TYPE_WINDOW]
    # Только слова, которые parse_query() оставила в optional (не бренд, не
    # цифра, не стоп-слово) — кандидаты на вид товара.
    candidates = [w for w in words if w in parsed.optional]
    if not candidates:
        return parsed

    index = await _get_type_stem_index(db)
    if not index:
        return parsed

    stmt = sa_text(
        "SELECT w, (ts_lexize('russian_stem', w))[1] AS stem FROM unnest(:words) AS w"
    ).bindparams(bindparam("words", type_=PG_ARRAY(String)))
    rows = (await db.execute(stmt, {"words": candidates})).all()
    stem_by_word = {word: stem for word, stem in rows}

    for w in candidates:
        canon = index.get(stem_by_word.get(w))
        if canon:
            new_required = [*parsed.required, w]
            new_optional = [o for o in parsed.optional if o != w]
            return ParsedQuery(
                raw=parsed.raw,
                required=new_required,
                optional=new_optional,
                dropped_stopwords=parsed.dropped_stopwords,
                specific=parsed.specific,
                brand=parsed.brand,
                product_type=canon,
                type_literal=w,
            )
    return parsed


# ---------------------------------------------------------------------------
# Словарь брендов из своей БД (manufacturer), с кэшем в памяти процесса —
# см. docstring модуля, почему НЕ tools/catalog_enrich/brand_dictionary
# (та собирается из офлайн-файлов, не годится для горячего HTTP-пути).
# Подключение в product_search.py — следующий шаг, см. TASKS.md
# (приостановлено владельцем 28.10.2026).
# ---------------------------------------------------------------------------

BRAND_CACHE_TTL_SECONDS = 30 * 60

_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_BOUNDARY_CHARS = r"a-zа-яё0-9"


# ---------------------------------------------------------------------------
# Кириллическое написание латинского бренда («болгарка макита», «перфоратор
# бош») — владелец, 28.10.2026: find_in_name выше ищет ТОЧНОЕ написание
# (fold_brand_or_code — только гомоглифы/регистр, НЕ транслит), бренды в
# словаре латиницей (Makita, Bosch, Karcher...) → кириллица мимо. Фонетический
# ключ ниже — ПЕРЕИСПОЛЬЗУЕТ разбиение на слова _split_words (Правило №6, та
# же токенизация, что и для required/optional выше), сам транслит — отдельная
# нормализация, не копия fold_brand_or_code (та для ДРУГОЙ задачи — гомоглифы
# ОДНОГО алфавита, не перевод между алфавитами).
# ---------------------------------------------------------------------------

_PHONETIC_MIN_WORD_LEN = 4
_PHONETIC_MIN_KEY_LEN = 4

# Побуквенный транслит кириллица→латиница (фонетический, не ГОСТ): цель —
# один и тот же ключ для "макита" и "Makita", не словарь ГОСТ-транслитерации.
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_DOUBLE_LETTER_RE = re.compile(r"(.)\1+")
_H_AFTER_VOWEL_RE = re.compile(r"(?<=[aeiou])h")


def _phonetic_fold(latin: str) -> str:
    """Сворачивает уже транслитерированную (или изначально латинскую)
    строку в фонетический ключ — одни и те же правки для обеих сторон
    сравнения (кириллица-после-транслита и исходная латиница бренда),
    поэтому "макита"→"makita" и "Makita"→"makita" дают один ключ."""
    s = latin.lower()
    s = s.replace("ä", "e").replace("ae", "e")
    s = s.replace("sch", "sh")  # Bosch/бош — до "ch"→"k" ниже
    s = s.replace("ph", "f")
    s = s.replace("ch", "k")
    s = s.replace("ck", "k")
    s = s.replace("q", "k").replace("c", "k")
    s = s.replace("w", "v")
    s = s.replace("x", "ks")
    s = s.replace("y", "i")
    s = _DOUBLE_LETTER_RE.sub(r"\1", s)
    s = _H_AFTER_VOWEL_RE.sub("", s)
    if s.endswith("h"):
        s = s[:-1]
    return s


def _brand_phonetic_key(text: str) -> str:
    """Транслит (если нужен) + _phonetic_fold — единая функция для слова
    запроса (кириллица) и названия бренда из словаря (обычно латиница);
    латинские буквы транслит не трогает (dict.get возвращает тот же символ)."""
    if not text:
        return ""
    translit = "".join(_CYR_TO_LAT.get(ch, ch) for ch in text.lower())
    return _phonetic_fold(translit)


def _phonetic_key_variants(text: str) -> frozenset:
    """Второй вариант ключа для немецкого начального st/sp («Stihl»/«штиль»
    — «sht», не «st»): кириллица «ш» транслитится прямо в «sh», латинское
    «st» нет — без варианта «stihl»→«stil» и «штиль»→«shtil» не совпадут."""
    base = _brand_phonetic_key(text)
    variants = {base}
    if base[:2] in ("st", "sp"):
        variants.add("sh" + base[1:])
    return frozenset(v for v in variants if v)


# Ручные алиасы — фонетика НЕ берёт (короткое слово «бош» короче порога
# _PHONETIC_MIN_WORD_LEN; «керхер»/«кархер» и «деволт»/«девольт» расходятся
# с латинским ключом гласной/группой букв, см. отчёт сессии 28.10.2026).
# Ключ — слово запроса (строчными, через fold_brand_or_code, как и остальные
# сравнения здесь), значение — варианты написания бренда для поиска в своём
# словаре manufacturer (используется первое, что реально есть в БД).
_MANUAL_BRAND_PHONETIC_ALIASES = {
    "бош": ("Bosch",),
    "керхер": ("Karcher", "Kärcher"),
    "кархер": ("Karcher", "Kärcher"),
    "деволт": ("DeWalt",),
    "девольт": ("DeWalt",),
}


# ---------------------------------------------------------------------------
# Короткие/буквенно-цифровые "бренды" в поле manufacturer — ЛОЖНЫЕ срабатывания
# (владелец, 28.10.2026, аудит прод-словаря 3733 значений manufacturer): на
# ТОЧНОМ пути (self._combined — ищет ЛЮБОЙ fold_brand_or_code(manufacturer)
# целым словом) не было никаких ограничений вроде тех, что уже стоят у
# фонетики (_PHONETIC_MIN_WORD_LEN/_PHONETIC_MIN_KEY_LEN) — короткие коды
# упаковки/маркировки, случайно попавшие в manufacturer при импорте каталога
# ("бумага офисная А4"→«А4», "футболка XL"→XL, "кабель SE"→SE, "аптечка
# ST"→ST, "рация GT"→GT, "трос ET 5м"→ET, "фонарь GP"→GP — 266 значений с
# ключом ≤3 символа в прод-словаре на 28.10.2026), ложно «узнавались» бредом.
# Настоящие короткие бренды (HP, LG, WD...) при этом существуют — убрать
# короткие коды совсем нельзя. Белый список — ЕДИНСТВЕННЫЙ способ короткому
# значению участвовать в распознавании бренда из текста запроса; остальные
# короткие значения в self._entries (а значит — и в recognition) не
# попадают вовсе — в каталоге/полнотексте они как значение manufacturer
# остаются (эта фильтрация — только для разбора ЗАПРОСА, не для каталога).
#
# Список составлен из кандидатов владельца, ПРОВЕРЕННЫХ по прод-словарю
# (28.10.2026): HP/LG/WD/ABB/IEK/EKF/DKC/TDM/DDE/AMD/MSI/TCL реально
# встречаются как manufacturer в проде и являются настоящими
# производителями; 3M/AEG/BBK/JBL/ZTE/OBI владелец предложил, но в
# прод-словаре на момент проверки НЕ встретились — не включены (список
# нельзя засорять непроверяемыми записями; добавить при реальном случае).
_SHORT_BRAND_MAX_KEY_LEN = 3

_SHORT_BRAND_WHITELIST = frozenset({
    "HP", "LG", "WD", "ABB", "IEK", "EKF", "DKC", "TDM", "DDE", "AMD", "MSI", "TCL",
})
_SHORT_BRAND_WHITELIST_KEYS = frozenset(_brand_compare_key(b) for b in _SHORT_BRAND_WHITELIST)


# Размерные обозначения (одежда/бумага) — НЕ бренды ни при каких условиях
# (владелец, 28.10.2026, п.3 задания). Готового словаря размеров в проекте
# не нашлось (grep: нет _SIZE_WORDS/CLOTHING_SIZE/PAPER_SIZE ни в
# product_name_signature*, ни в product_tz_44fz_*) — список маленький,
# только для этого фильтра; ключи — через fold_brand_or_code, тот же способ
# сравнения, что и у остальных множеств здесь (единая нормализация, Правило
# №6: второй способ сравнения не завожен).
_SIZE_TOKEN_LITERALS = (
    "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL",
    "А0", "А1", "А2", "А3", "А4", "А5", "А6",
)
_SIZE_TOKENS = frozenset(fold_brand_or_code(t) for t in _SIZE_TOKEN_LITERALS)


def _is_recognizable_brand_word(word: str) -> bool:
    """Слово НЕ предлог/союз (_PREPOSITION_STOPWORDS), НЕ вид товара
    (PRODUCT_TYPE_WORDS) и НЕ размерное обозначение (_SIZE_TOKENS) — ОБЩИЙ
    фильтр для ТОЧНОГО (find_in_name) и ФОНЕТИЧЕСКОГО (_find_phonetic) пути
    распознавания бренда в тексте запроса (владелец, 28.10.2026, п.2 задания
    — один хелпер, не копия фильтра на каждый путь, Правило №6). `word` —
    уже в том же нормализованном виде, что даёт fold_brand_or_code/
    _split_words (строчные буквы, гомоглифы свёрнуты)."""
    return (
        word not in _PREPOSITION_STOPWORDS
        and word not in PRODUCT_TYPE_WORDS
        and word not in _SIZE_TOKENS
    )


class ManufacturerBrandDictionary:
    """`.find_in_name` того же контракта, что и BrandDictionary из
    tools/catalog_enrich — но построен из DISTINCT Product.manufacturer
    своей БД (is_bogus_manufacturer — тот же гейт качества, что в
    build_signature, Правило №6 — второй фильтр мусорных значений не
    заводим)."""

    def __init__(self, manufacturers: list) -> None:
        entries: dict = {}
        for name in manufacturers:
            if not name or is_bogus_manufacturer(name, ""):
                continue
            # Короткий (≤3 символа после _brand_compare_key) код НЕ из
            # белого списка — не участвует в распознавании бренда из
            # запроса (см. docstring блока _SHORT_BRAND_WHITELIST выше);
            # сам manufacturer в каталоге/полнотексте при этом не трогаем —
            # это фильтр только этого словаря-распознавателя.
            cmp_key = _brand_compare_key(name)
            if len(cmp_key) <= _SHORT_BRAND_MAX_KEY_LEN and cmp_key not in _SHORT_BRAND_WHITELIST_KEYS:
                continue
            key = fold_brand_or_code(name)
            if key and key not in entries:
                entries[key] = name
        self._entries = entries

        # ОДИН компилированный regex с альтернацией вместо N отдельных
        # re.compile() на каждый бренд (владелец, 28.10.2026, замер «этап
        # 0» ревью: ~530 манифактур → ~520 отдельных compile() ≈ 200-260мс
        # холодного построения; один re.compile() с тем же числом
        # альтернатив — заметно быстрее, см. отчёт сессии). Самые длинные
        # ключи — первыми (альтернация регэкспа жадная по порядку —
        # длинное совпадение не должно проигрывать более короткому
        # префиксу, та же причина, что у tools/catalog_enrich/
        # brand_dictionary.BrandDictionary.finalize()). Само совпадение
        # матчится литерально, затем ищется в self._entries по той же
        # ключевой строке — группы regex не нужны (Правило №6, не второй
        # способ разбора совпадения).
        if entries:
            sorted_keys = sorted(entries, key=len, reverse=True)
            alternation = "|".join(re.escape(k) for k in sorted_keys)
            self._combined = re.compile(
                rf"(?<![{_WORD_BOUNDARY_CHARS}])(?:{alternation})(?![{_WORD_BOUNDARY_CHARS}])",
                re.IGNORECASE,
            )
        else:
            self._combined = None

        # Фонетический индекс — только брендов с ключом не короче
        # _PHONETIC_MIN_KEY_LEN (короче — слишком велик риск случайного
        # совпадения, см. docstring _MANUAL_BRAND_PHONETIC_ALIASES выше;
        # считаем один раз на пересборку кэша (BRAND_CACHE_TTL_SECONDS), не
        # на каждый запрос).
        phonetic_index: dict = {}
        for key, original in entries.items():
            for variant in _phonetic_key_variants(original):
                if len(variant) >= _PHONETIC_MIN_KEY_LEN:
                    phonetic_index[variant] = original
        self._phonetic_index = phonetic_index

        # Ручные алиасы — резолвим здесь, один раз, под реально существующие
        # в своей БД написания (алиас на бренд, которого в каталоге нет, —
        # молчаливо не используется).
        manual: dict = {}
        for word, candidates in _MANUAL_BRAND_PHONETIC_ALIASES.items():
            for candidate in candidates:
                key = fold_brand_or_code(candidate)
                if key in entries:
                    manual[word] = entries[key]
                    break
        self._manual_phonetic_aliases = manual

    def find_in_name(self, name: str) -> Optional[str]:
        if not name:
            return None
        if self._combined is not None:
            folded = fold_brand_or_code(name)
            # finditer, не search: первое совпадение регэкспа может быть
            # предлогом/видом товара/размером, случайно совпавшим с
            # manufacturer-значением в словаре ("до"→бренд "ДО" — реальная
            # находка аудита 28.10.2026) — _is_recognizable_brand_word
            # (общий хелпер, см. выше) пропускает такое совпадение и ищет
            # следующее, а не сдаётся сразу.
            for m in self._combined.finditer(folded):
                matched = m.group(0).lower()
                if not _is_recognizable_brand_word(matched):
                    continue
                hit = self._entries.get(matched)
                if hit:
                    return hit
        return self._find_phonetic(name)

    def _find_phonetic(self, name: str) -> Optional[str]:
        """Кириллическое написание латинского бренда («макита», «бош») —
        см. docstring блока _phonetic_fold/_MANUAL_BRAND_PHONETIC_ALIASES
        выше. Слово короче _PHONETIC_MIN_WORD_LEN или не прошло
        _is_recognizable_brand_word (общий фильтр с точным путём выше,
        владелец 28.10.2026, п.2 задания) фонетикой не проверяем — только
        ручные алиасы (бош — короче порога) обходят длину."""
        if not self._phonetic_index and not self._manual_phonetic_aliases:
            return None
        for word in _split_words(name):
            if word in self._manual_phonetic_aliases:
                return self._manual_phonetic_aliases[word]
            if len(word) < _PHONETIC_MIN_WORD_LEN:
                continue
            if not _is_recognizable_brand_word(word):
                continue
            if not self._phonetic_index:
                continue
            for variant in _phonetic_key_variants(word):
                hit = self._phonetic_index.get(variant)
                if hit:
                    return hit
        return None

    def __len__(self) -> int:
        return len(self._entries)


_brand_dict_cache: dict = {"dictionary": None, "built_at": 0.0}


async def get_manufacturer_brand_dictionary(db: AsyncSession) -> ManufacturerBrandDictionary:
    """Кэшированный (BRAND_CACHE_TTL_SECONDS) словарь брендов из своих
    Product.manufacturer — дёшево (один DISTINCT-запрос раз в N минут, не на
    каждый HTTP-запрос поиска)."""
    now = time.monotonic()
    cached = _brand_dict_cache["dictionary"]
    if cached is not None and (now - _brand_dict_cache["built_at"]) < BRAND_CACHE_TTL_SECONDS:
        return cached

    rows = (
        await db.execute(select(Product.manufacturer).distinct().where(Product.manufacturer.isnot(None)))
    ).scalars().all()
    dictionary = ManufacturerBrandDictionary(rows)
    _brand_dict_cache["dictionary"] = dictionary
    _brand_dict_cache["built_at"] = now
    return dictionary
