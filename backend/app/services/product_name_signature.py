"""Одно общее правило «тот же товар» по названию — как решает человек, по
бренду и ЦИФРОВЫМ токенам названия (индекс модели, числа), без отдельных
таблиц под каждый вид товара (владелец, 27.10.2026, затем уточнение
алгоритма тем же днём — см. история решений ниже). Единственное место этой
логики для будущих сведений каталога (ПРАВИЛО №6) — product_similar.py и
products_import_match.py при подключении ДОЛЖНЫ вызывать match()/
build_signature() отсюда, а не писать вторую «похожесть».

ИСТОРИЯ РЕШЕНИЯ (владелец, 27.10.2026, один день, три уточнения):
  1. Первая постановка: бренд + множество "буква+цифра" токенов (индекс
     модели) ДОЛЖНО совпасть точно; числа с единицами и чистые числа —
     "свойства", сравниваются отдельно по группам (цвет/материал/страна/
     класс пожара/комплектация/исполнение).
  2. Уточнение алгоритма: кандидат — названия "примерно одинаковые" (мера
     похожести по множеству СЛОВ, overlap-коэффициент — см. docstring
     `_overlap_coefficient`, порог подобран на реальных данных,
     backend/scripts/eval_name_signature.py), НО ЖЁСТКО — **любой токен
     названия, в котором есть хоть одна цифра** (не только "буква+цифра"),
     должен совпасть ТОЧНО как множество между двумя названиями. Это и есть
     индекс/код/число, которое отличает один товар от другого (ОП-2 ≠
     ОП-20, ASUS ZenBook 14 ≠ ZenBook 13, "д600*ш400*в400" ≠
     "д500*ш370*в120" — размеры и "марка Т24" ≠ "марка Т22" это просто
     токены с цифрой, второй словарь под "размеры" не нужен).
  3. Проверка свойств ПО ПОРЯДКУКУ, из характеристик JSON (characteristics)
     И из названия: цвет → вес (с переводом единиц, "2 кг"="2000 г") →
     страна производства → остальные характеристики (по совпавшему
     нормализованному имени характеристики — где нормализованные имена не
     совпали, НЕ сравниваем, см. docstring `_other_characteristics_diff`) →
     свойства из названия (класс пожара/комплектация/исполнение/материал).
     Признак задан у ОБОИХ и отличается → `decision: "no"`; задан у одного —
     не мешает (п.4 исходной постановки).

ПОВОД «не fuzzy без цифр» (инцидент июня, владелец запретил повторять):
"примерное" сравнение без жёсткой проверки цифровых токенов однажды ложно
склеило разные товары (разные размеры гофрокороба, разные марки). Поэтому
цифровые токены здесь — НЕ часть "похожести", а отдельный ОБЯЗАТЕЛЬНЫЙ гейт,
который overlap-коэффициент не может переопределить.

ПОВОД «бренд латиницей не распознан → порог обойти нельзя» (владелец, доп.
ревью пробного прогона merge_by_name_model, 27.10.2026, п.2): "Аккумуляторная
батарея Delta DT 1240" и "... Security Force SF 1240" были сведены — бренды
РАЗНЫЕ, manufacturer/словарь их не знают, а совпавший словарный вид товара
обходил overlap-порог. Теперь обход порога по совпавшему виду ДОПУСТИМ ТОЛЬКО
если у обоих распознан (manufacturer/словарь) ОДИНАКОВЫЙ бренд; иначе, если в
названии с обеих сторон есть латинское слово-кандидат в бренд (Title Case/
ВСЕ ЗАГЛАВНЫЕ) и множества таких слов не пересекаются — `decision: "no"`
("вероятно разные бренды"), см. `_extract_brand_like_words`. Там же —
размеры Д×Ш×В через "х" ("198х166х170" ≠ "195х165х170") сравниваются целой
последовательностью осей, не отдельными числами, см. `_extract_name_dimensions`.

Переиспользуется (ПРАВИЛО №6, не копируется):
  - app.services.brand_code_fold.fold_brand_or_code — свёртка
    кириллица/латиница-гомоглифов и регистра для сравнения;
  - app.services.catalog_gala.manufacturer_quality.is_bogus_manufacturer —
    отсев мусорного значения manufacturer;
  - app.services.product_name_signature_props — словари групп свойств
    (цвет/материал/страна/класс пожара/комплектация/исполнение/единицы);
  - словарь брендов (поиск бренда в названии) — вызывающий код передаёт
    любой объект с `.find_in_name(name) -> str | None`, см.
    tools/catalog_enrich/brand_dictionary.BrandDictionary (вторую
    "угадайку бренда" здесь не заводим)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.brand_code_fold import fold_brand_or_code, fold_text_preserving_script
from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer
from app.services.product_characteristics_parse import (
    clean_characteristics_list,
    normalize_characteristic_unit,
)
from app.services.product_tz_44fz_rules import STOP_BRAND_WORDS
from app.services.product_name_signature_props import (
    ACCESSORY_MARKERS, CARRY_CASE_PHRASES, CHARGER_PHRASES, COATING_PHRASES,
    COATING_WORDS, COLOR_WORDS, COUNTRY_WORDS, EXECUTION_PHRASES,
    EXECUTION_WORDS, EXTINGUISHER_SUBTYPE_WORDS, EXTRA_PACKAGING_PHRASES,
    FIRE_CLASS_RE, FUSED_CODE_SUFFIX, HOSE_TYPE_WORDS, INSTALL_MODE_WORDS,
    MATERIAL_WORDS, NOZZLE_TYPE_WORDS, ORDER_REFERENCE_RE, PACKAGING_PHRASES,
    PRODUCT_TYPE_PHRASES, PRODUCT_TYPE_WORDS, SHUTOFF_WORDS, SIDEDNESS_WORDS,
    UNIT_WORDS, _BATTERY_CAPACITY_RE, _BATTERY_COUNT_RE, _PACKAGING_SET_RE,
)

# ---------------------------------------------------------------------------
# Токенизация названия
# ---------------------------------------------------------------------------

# Правило overlap-меры (владелец, 27.10.2026, уточнение 2): overlap-
# коэффициент (|A∩B| / min(|A|,|B|)) выбран вместо Жаккара специально, чтобы
# "Сабельная пила Makita LXT DJR187Z" (лишние слова ТОЛЬКО у длинной стороны)
# не штрафовался за объединение множеств — короткое название целиком входит
# в длинное → overlap=1.0, Жаккар дал бы ~0.4 и ломал бы тест на этом же
# примере. Порог см. NAME_OVERLAP_CHECK_THRESHOLD ниже и распределение в
# отчёте eval_name_signature.py — overlap ТОЛЬКО понижает auto→check (не
# блокирует match), цифровые токены и бренд — обязательный гейт выше него.
NAME_OVERLAP_CHECK_THRESHOLD = 0.35

_EDGE_PUNCT_RE = re.compile(r'^[«»"\'“”,;:()\[\]]+|[«»"\'“”,;:()\[\]]+$')
_HAS_DIGIT_RE = re.compile(r"\d")
_KEEP_ALNUM_RE = re.compile(r"[^0-9a-zа-яё]")


_NON_ALNUM_RE = re.compile(r"[^0-9a-zа-яё]")


def _brand_compare_key(text: Optional[str]) -> str:
    """Ключ для сравнения бренда (и любого "как есть НЕ сравниваем" места) —
    fold_brand_or_code (регистр/гомоглифы — исправлено в самой функции,
    владелец, 27.10.2026, см. docstring brand_code_fold.py) И убрано всё,
    кроме букв/цифр: "Sturm!" = "Sturm" = "sturm", "Tech-KREP" = "Techkrep",
    "СТЕЛЛА-ТЕХНИК" = "стеллатехник"."""
    return _NON_ALNUM_RE.sub("", fold_brand_or_code(text))


# STOP_BRAND_WORDS — переиспользуем словарь ТЗ 44-ФЗ (app.services.
# product_tz_44fz_rules, ПРАВИЛО №6: цвета/материалы/страны/общие слова,
# которые по ошибке попадают в manufacturer, уже перечислены там одним
# списком, второй здесь не заводим); ключи приведены через
# _brand_compare_key один раз на импорт модуля.
_BRAND_STOPWORD_KEYS = frozenset(_brand_compare_key(w) for w in STOP_BRAND_WORDS)

# Короткие предлоги/союзы — не несут опознавательной силы, выброс из
# word_set (но НЕ из digit_tokens — там цифровых слов не бывает).
_STOPWORDS = {
    "и", "с", "со", "для", "от", "до", "на", "в", "во", "без", "не", "по",
    "из", "а", "но", "или", "к", "у", "о", "об", "при", "за",
}

# ---------------------------------------------------------------------------
# Фонетическое сопоставление брендов и слов (кириллица ↔ латиница + удвоенные
# буквы) и фильтрация коротких/размерных ложных брендов (ПРАВИЛО №6 — единое
# место, переиспользуется в product_query_parse.py и store_search/relevance.py).
# ---------------------------------------------------------------------------

_PHONETIC_MIN_WORD_LEN = 4
_PHONETIC_MIN_KEY_LEN = 4

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
    """Сворачивает транслитерированную или латинскую строку в фонетический
    ключ («макита»→«makita» и «Makita»→«makita», «Hakkapeliitta»→«hakapelita»)."""
    s = latin.lower()
    s = s.replace("ä", "e").replace("ae", "e")
    s = s.replace("sch", "sh")
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
    if not text:
        return ""
    translit = "".join(_CYR_TO_LAT.get(ch, ch) for ch in text.lower())
    return _phonetic_fold(translit)


def _phonetic_key_variants(text: str) -> frozenset:
    base = _brand_phonetic_key(text)
    variants = {base}
    if base[:2] in ("st", "sp"):
        variants.add("sh" + base[1:])
    return frozenset(v for v in variants if v)


_MANUAL_BRAND_PHONETIC_ALIASES = {
    "бош": ("Bosch",),
    "керхер": ("Karcher", "Kärcher"),
    "кархер": ("Karcher", "Kärcher"),
    "деволт": ("DeWalt",),
    "девольт": ("DeWalt",),
}


def _brand_phonetic_keys_for(brand: Optional[str]) -> frozenset:
    """Множество фонетических ключей бренда (с учётом ручных алиасов «бош»↔«Bosch»,
    «керхер»↔«Karcher», «деволт»↔«DeWalt») для сравнения брендов в кириллице и
    латинице."""
    if not brand:
        return frozenset()
    cleaned = _NON_ALNUM_RE.sub("", str(brand).lower())
    if not cleaned:
        return frozenset()
    keys = set(_phonetic_key_variants(cleaned))
    folded = fold_brand_or_code(brand).strip()
    if folded in _MANUAL_BRAND_PHONETIC_ALIASES:
        for alias in _MANUAL_BRAND_PHONETIC_ALIASES[folded]:
            keys.update(_phonetic_key_variants(_NON_ALNUM_RE.sub("", alias.lower())))
    return frozenset(k for k in keys if len(k) >= 3)


_SHORT_BRAND_MAX_KEY_LEN = 3

_SHORT_BRAND_WHITELIST = frozenset({
    "HP", "LG", "WD", "ABB", "IEK", "EKF", "DKC", "TDM", "DDE", "AMD", "MSI", "TCL",
    "РИФ", "МИГ", "3M", "AEG", "JBL", "ZTE", "BBK", "CBR", "DLT", "ADA", "ПТС", "ВСВ",
})
_SHORT_BRAND_WHITELIST_KEYS = frozenset(_brand_compare_key(b) for b in _SHORT_BRAND_WHITELIST)

_SIZE_TOKEN_LITERALS = (
    "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL",
    "А0", "А1", "А2", "А3", "А4", "А5", "А6",
)
_SIZE_TOKENS = frozenset(fold_brand_or_code(t) for t in _SIZE_TOKEN_LITERALS)


def _is_recognizable_brand_word(word: str) -> bool:
    """Слово НЕ предлог/союз (_STOPWORDS), НЕ вид товара (PRODUCT_TYPE_WORDS)
    и НЕ размерное обозначение (_SIZE_TOKENS)."""
    return (
        word not in _STOPWORDS
        and word not in PRODUCT_TYPE_WORDS
        and word not in _SIZE_TOKENS
    )


_UNIT_SUFFIX_RE = re.compile(r"^(\d+)([a-zа-яё]{1,2})$")

# Буква-модификатор модели: одиночная буква (или 1-2 буквы) отдельным
# словом СРАЗУ после кода модели ("ДИН2 Д", "ГПС-200 П", "СЗП-02ГУ М",
# "ОУ-5 Б") — владелец, ревью 113 авто-пар 27.10.2026 (п.1): часть индекса
# модели, ОБЯЗАНА совпасть как цифровой токен (не "похожесть" — см.
# докстринг модуля про digit_tokens-гейт). Отличать от числа-с-единицей
# ("24 В", "5 А", "10 Л") НЕ нужно отдельно — тот случай уже вырезан ДО
# этого места _strip_unit_quantities (число+единица идёт СРАЗУ после
# цифры, без буквенного кода между ними) — см. _split_words/_UNIT_QUANTITY_
# RE; то, что добирается сюда (буква после буквенно-цифрового КОДА, не
# после голого числа), — всегда индекс/модификация, UNIT_WORDS здесь
# поэтому НЕ проверяем.
_MODEL_MODIFIER_LETTER_RE = re.compile(r"^[a-zа-яё]{1,2}$")

# Региональный суффикс артикула производителя (владелец, доп. ревью
# Кувалда↔Бауцентр, 27.10.2026, п.4): «RH1183»=«RH1183SE00»,
# «DCF887N»=«DCF887N-XJ» (дефис уже вырезан на этом шаге, т.к. он не
# буква/цифра). Список ЗАКРЫТ — общее правило "совпал префикс" не заводим:
# «DHR242Z» ≠ «DHR242RT» — это разная комплектация, а не суффикс региона.
_MARKET_SUFFIXES = ("se00", "se01", "xj", "xe", "ks", "qw", "gb", "ru", "eu")
# Суффиксы сравниваем в том же свёрнутом виде, что и сами токены (norm
# идёт через fold_brand_or_code в _split_words) — иначе латинские "e"/"x"
# внутри суффикса не совпадут с кириллическими гомоглифами "е"/"х", в
# которые их сворачивает fold_brand_or_code (баг найден на тесте
# «RH1183SE00»: «e» в «SE00» после фолда — кириллическая «е»).
_MARKET_SUFFIXES_SORTED = tuple(
    sorted({*(_MARKET_SUFFIXES), *(fold_brand_or_code(s) for s in _MARKET_SUFFIXES)}, key=len, reverse=True)
)


def _strip_known_market_suffix(norm: str) -> str:
    for suf in _MARKET_SUFFIXES_SORTED:
        if norm.endswith(suf) and len(norm) > len(suf) + 1:
            base = norm[: -len(suf)]
            if _HAS_DIGIT_RE.search(base):
                return base
    return norm


# Хвостовые коды магазина в названии — НЕ индекс модели (владелец, доп.
# ревью Кувалда↔Бауцентр, 27.10.2026, п.3): числа с дефисом/слэшем в
# скобках и после них ("(063-4086) 063-4086", "792-179" — чисто цифровые,
# разделитель внутри, без единой буквы — у настоящего индекса модели
# буква почти всегда есть); длинные чисто цифровые EAN-подобные (≥8 цифр,
# "4687206150287"); коды с кириллической буквенной приставкой магазина
# (2-4 буквы + ≥5 цифр, "ЭдЭБ05888", "НС-1706812") — ЭТИ только в хвосте
# названия (последние 3 токена), иначе случайно отрежем настоящий код,
# стоящий не в конце.
_PURE_NUMERIC_DASH_RE = re.compile(r"^\d+[-/]\d+$")
_LONG_NUMERIC_RE = re.compile(r"^\d{8,}$")
_STORE_PREFIX_CODE_RE = re.compile(r"^[а-яё]{2,4}-?\d{5,}$")


def _is_store_tail_code(word: str, idx: int, total: int) -> bool:
    if _PURE_NUMERIC_DASH_RE.match(word):
        return True
    norm = _KEEP_ALNUM_RE.sub("", word)
    if _LONG_NUMERIC_RE.match(norm):
        return True
    if idx >= total - 3 and _STORE_PREFIX_CODE_RE.match(word):
        return True
    return False

# Число(-а) с единицей измерения в самом названии ("18 В", "1х5,0 Ач",
# "2,0 Дж", "950 Вт") — владелец, 27.10.2026 (ревью auto-пар kuvalda ↔
# baucenter_tools_hardware: у Бауцентра в названии часто дописаны такие
# числа, которых нет у Кувалды — "18 В 1х5,0 Ач 2,0 Дж" — и они ложно
# требовали точного совпадения как индекс модели, хотя это СВОЙСТВО
# (п.4), а не код). Лookbehind/lookahead — ТОЛЬКО не часть более длинного
# буквенно-цифрового кода (не вырезает "400" внутри слитного
# "д600*ш400*в400" — там прямо перед числом стоит буква без пробела, см.
# тест test_corrugated_box_different_dimensions_and_grade)."""
_MULTI_LETTER_UNIT_WORDS = sorted(
    (u for u in UNIT_WORDS if len(u) > 1), key=len, reverse=True,
)
_SINGLE_LETTER_UNIT_WORDS = sorted((u for u in UNIT_WORDS if len(u) == 1), key=len, reverse=True)
_UNIT_WORDS_ALT = "|".join(re.escape(u) for u in _MULTI_LETTER_UNIT_WORDS)
_SINGLE_LETTER_UNIT_WORDS_ALT = "|".join(re.escape(u) for u in _SINGLE_LETTER_UNIT_WORDS)

# Общее начало числа — ТОЛЬКО после пробела/открывающей скобки/начала строки
# (владелец, доп. ревью стволов РС-50, 28.10.2026): раньше достаточно было
# "не буква/цифра перед числом", а дефис перед числом (а он — не буква/цифра)
# этому не мешал — "РС-50А" ложно читалось как "РС-" + "50 Ампер" (буква "А" —
# тоже единица UNIT_WORDS, ампер) и терялся КАК КОД МОДЕЛИ целиком, хотя "А"
# здесь суффикс материала (алюминий), а не единица измерения. Числа-с-единицей
# в реальных названиях ВСЕГДА отделены пробелом/скобкой от предыдущего слова
# ("18 В", "(12В 40Ач)") — слитные с кодом модели через дефис/точку больше не
# считаются количеством.
_UNIT_QUANTITY_NUM_RE = r"(?:(?<=^)|(?<=[\s([«]))\d+(?:[.,]\d+)?(?:\s*[xXхХ×*]\s*\d+(?:[.,]\d+)?)*"

# Однобуквенная единица ("с"/"м"/"г"/"л"/"т"/"в"/"а"/"н"/"c") — ОТДЕЛЬНАЯ
# ветка регэкспа (дефект найден при разработке 29.10.2026 на «болгарка макита 125
# с регулировкой»): предлог «с» ("со мной" → "с регулировкой") — буквально то
# же слово, что и единица "с" (секунды/°C, UNIT_WORDS). Общая проверка выше
# "не буква/цифра СРАЗУ после единицы" этот случай не ловит — после "с" идёт
# ПРОБЕЛ, а не буква, лимит проверяет только непосредственно следующий символ.
# Правило: однобуквенная единица засчитывается единицей
# ТОЛЬКО если за ней (через необязательный пробел) НЕ следует слово из букв —
# т.е. следом идёт конец строки, знак препинания/скобка, цифра или "/".
# Многобуквенные единицы ("кг", "мин", "шт"...) этим доп. условием не
# ограничены — коллизия с обычным словом у них практически не встречается.
_UNIT_QUANTITY_RE = re.compile(
    rf"{_UNIT_QUANTITY_NUM_RE}\s*(?:{_UNIT_WORDS_ALT})(?![0-9a-zA-Zа-яёА-ЯЁ])"
    rf"|{_UNIT_QUANTITY_NUM_RE}\s*(?:{_SINGLE_LETTER_UNIT_WORDS_ALT})"
    rf"(?![0-9a-zA-Zа-яёА-ЯЁ])(?!\s*[a-zA-Zа-яёА-ЯЁ])",
    re.IGNORECASE,
)


def _strip_unit_quantities(name: str) -> str:
    """Вырезает "число(-а)-с-единицей" из названия ДО токенизации — см.
    docstring _UNIT_QUANTITY_RE выше. Это СВОЙСТВО (п.4 — указано у одного,
    у другого нет, не противоречие для индекса), не код модели."""
    return _UNIT_QUANTITY_RE.sub(" ", name or "")


def _strip_fire_class_spans(name: str) -> str:
    """Убирает подстроки класса пожара (ВСЕ/АВСЕ/...) из названия ДО
    разбивки на слова — иначе при слитном написании без пробела ("ОУ-5-
    ВСЕ") класс склеивается с индексом модели в ОДИН токен с цифрой и ломает
    точное сравнение цифровых токенов с тем же товаром, где класс написан
    через пробел ("ОУ-5 ВСЕ") — тест владельца, 27.10.2026. Сам класс пожара
    как СВОЙСТВО всё равно извлекается отдельно, из оригинального текста
    (см. _extract_name_properties) — здесь он просто вырезается ради
    токенизации индекса/чисел."""
    return FIRE_CLASS_RE.sub(" ", name or "")


# Номер приказа/ГОСТа/ТУ ("№1164н", "приказ № 1080н", "ГОСТ 12.4.026") и
# "аналог X" (владелец, доп. ревью 28.10.2026: "Ствол лафетный ЛС-П20
# (аналог СЛК-П20)" ≠ "Ствол лафетный СЛК-П20 (ПЛС-П20)" — "аналог" это
# ДРУГОЙ товар, код после слова "аналог" не относится к ЭТОМУ товару и не
# должен участвовать в индексе/коде модели) — вырезаются из названия ДО
# токенизации, тем же приёмом, что _strip_unit_quantities/_strip_fire_
# class_spans выше (ОДНА функция-обёртка _pre_clean ниже, ПРАВИЛО №6 — не
# повторять одну и ту же цепочку вызовов в каждом месте модуля).
_ANALOG_RE = re.compile(r"аналог[а-яё]*\s+\S+", re.IGNORECASE)


def _strip_reference_and_analog(name: str) -> str:
    name = ORDER_REFERENCE_RE.sub(" ", name or "")
    name = _ANALOG_RE.sub(" ", name)
    return name


# Диагональ в дюймах ("27\"", "24''", "32 дюйма") — владелец, срочная правка
# 28.10.2026 (прод, 998 "неоднозначных" групп): "Монитор Hisense 27G3Q" ≠
# "Монитор Hisense 27\" 27G3Q" ложно получали no — голое число "27" (из
# диагонали, БЕЗ кода модели рядом) попадало в digit_tokens и требовало
# точного совпадения множества, хотя это СВОЙСТВО (диагональ экрана), а не
# индекс/код. Вырезается из названия ДО токенизации кода (как число-с-
# единицей), значение — отдельно в name_qty (группа "диагональ", см.
# _extract_name_quantities) — ОДНА функция/группа чисел-с-единицей, вторую
# не заводим (ПРАВИЛО №6)."""
_INCH_RE = re.compile(
    r"(?<![0-9a-zA-Zа-яёА-ЯЁ])(\d+(?:[.,]\d+)?)\s*(?:\"|''|дюйм(?:а|ов)?\.?)"
    r"(?![0-9a-zA-Zа-яёА-ЯЁ])",
    re.IGNORECASE,
)


def _strip_inch_spans(name: str) -> str:
    return _INCH_RE.sub(" ", name or "")


def _extract_inch_diagonal(name: Optional[str]) -> set:
    if not name:
        return set()
    vals = set()
    for m in _INCH_RE.finditer(name):
        n = _parse_number(m.group(1))
        if n is not None:
            vals.add(round(n, 2))
    return vals


# Раздельное написание кириллической аббревиатуры модели и цифры через пробел
# («Огнетушитель ОП 2» = «Огнетушитель ОП-2», «ОУ 5» = «ОУ-5», «РСК 50» = «РСК-50»):
# склеиваем дефисом ТОЛЬКО 2-4 заглавные кириллические буквы перед цифрой, если
# это не предлог, не словарный вид товара и не общая аббревиатура/стоп-слово.
# Латинские слова перед числом ("Delta DT 1240", "Dell 24") НЕ трогаем, чтобы
# не задеть гейт латинских слов-кандидатов в бренд (_extract_brand_like_words).
_CYR_CODE_PREFIX_SPLIT_RE = re.compile(
    r"(?<![0-9a-zA-Zа-яёА-ЯЁ])([А-ЯЁ]{2,4}|(?:оп|оу|овэ|овп|рск|спрут|спи))\s+(?=\d)"
)
_CYR_NON_MODEL_PREFIXES = frozenset({
    "ГОСТ", "ТУ", "РФ", "УХЛ", "АКБ", "ЗУ", "СИЗ", "МЧС", "МВД", "ДНР", "ЛНР",
    "ВСЕ", "АВСЕ",
})


def _merge_cyr_code_prefix(name: str) -> str:
    def _repl(m: re.Match) -> str:
        prefix = m.group(1)
        if prefix.upper() in _CYR_NON_MODEL_PREFIXES:
            return m.group(0)
        folded = fold_brand_or_code(prefix)
        if (
            not _is_recognizable_brand_word(folded)
            or folded in UNIT_WORDS
            or _brand_compare_key(prefix) in _BRAND_STOPWORD_KEYS
        ):
            return m.group(0)
        return f"{prefix}-"
    return _CYR_CODE_PREFIX_SPLIT_RE.sub(_repl, name or "")


_IS_EXTINGUISHER_RE = re.compile(r"огнетушител|\b(?:оп|оу|овэ|овп)[-\s]?\d", re.IGNORECASE)
_EXT_ZPU_AND_CITY_RE = re.compile(
    r"\(\s*зпу\s*[^)]*\)|\bзпу\s*(?:китай|россия|рф|латунь)\b|\(\s*г\.?\s*[а-яё\-]+\s*\)",
    re.IGNORECASE,
)
_EXT_TYPO_Z3_RE = re.compile(r"(\b(?:оп|оу|овэ|овп)[-\s]?\d+)\s*\(3\)", re.IGNORECASE)


def _strip_extinguisher_notes(name: str) -> str:
    """Для огнетушителей: исправляет опечатку '(3)' вместо '(з)' после кода
    модели ('ОП-2(3)' → 'ОП-2(з)') и убирает уточнения по запорно-пусковому
    устройству ('ЗПУ Китай', 'ЗПУ Россия', '(ЗПУ латунь)') и городу
    производителя ('(г. Ярославль)'), которые не делают сам огнетушитель
    другим товаром. Самостоятельные товары 'ЗПУ Китай' / 'ЗПУ Россия' (без
    слова 'огнетушитель' и кода ОП/ОУ) не затрагиваются."""
    if not name or not _IS_EXTINGUISHER_RE.search(name):
        return name or ""
    s = _EXT_TYPO_Z3_RE.sub(r"\1(з)", name)
    return _EXT_ZPU_AND_CITY_RE.sub(" ", s)


def _pre_clean(name: Optional[str]) -> str:
    """Общая чистка названия ПЕРЕД любой токенизацией (индекс/вид/бренд-
    слова/размеры) — порядок: уточнения ЗПУ/города у огнетушителей → номер
    приказа/ГОСТ/"аналог X" → диагональ в дюймах → класс пожара →
    число-с-единицей → склейка кириллической марки через пробел («ОП 2» → «ОП-2»)."""
    return _merge_cyr_code_prefix(_strip_unit_quantities(_strip_fire_class_spans(
        _strip_inch_spans(_strip_reference_and_analog(_strip_extinguisher_notes(name or ""))))))


def _split_words(name: Optional[str], *, fold_homoglyphs: bool = True) -> list[str]:
    """Название → нормализованные слова (класс пожара вырезан, гомоглифы/
    регистр свёрнуты через fold_brand_or_code, пробелы схлопнуты, крайняя
    пунктуация у каждого слова срезана). Дефисы ВНУТРИ слова сохраняются на
    этом шаге — они срезаются только при вычислении digit_tokens (там код
    без дефисов).

    fold_homoglyphs=False — для разбора поискового запроса (product_query_parse,
    store_search): сохраняет исходный алфавит букв (латиница остаётся латиницей),
    чтобы слова вроде 'nokian', 'hakkapeliitta', 'hr2470' не превращались в
    смешанный кириллическо-латинский 'nокiаn', 'нr2470'."""
    if not name:
        return []
    cleaned = _pre_clean(name)
    folded = fold_brand_or_code(cleaned) if fold_homoglyphs else fold_text_preserving_script(cleaned)
    words = []
    for raw in folded.split():
        w = _EDGE_PUNCT_RE.sub("", raw)
        if w:
            w = EXTINGUISHER_SUBTYPE_WORDS.get(w, w)
            words.append(w)
    return words


def _digit_tokens(words: list[str]) -> tuple:
    """Любое слово с хотя бы одной цифрой — индекс/код/число (владелец,
    уточнение 2: это ОБЯЗАТЕЛЬНЫЙ гейт, не "похожесть"). Нормализация —
    только цифры и буквы (дефисы/скобки/точки/запятые убраны), поэтому
    "ОП-2" и "ОП—2" (вариант дефиса уже свёрнут fold_brand_or_code) дают
    один и тот же ключ, а "ОП-2"/"ОП-20" — разные (цифры не тронуты).

    Исключение: токен вида "<число><1-2 буквы единицы>" слитно ("55В",
    "350Вт" — буквы из того же UNIT_WORDS, что и у characteristics,
    ПРАВИЛО №6) — это число-с-единицей/классификационная отметка
    (необязательное уточнение, п.4: "указано у одного, у другого нет — не
    противоречие"), а не код модели, который ОБЯЗАН совпасть — иначе
    у одного магазина в названии указана доп. классификация (55В, С, Е),
    а у другого её просто нет, и ровно тот же товар ложно не сводится.

    Возвращает (frozenset(digit_tokens), fused_props) — fused_props —
    {группа: set(значений)} для суффиксов FUSED_CODE_SUFFIX, слитных с
    кодом без пробела ("РС-50А" → код "рс50" + материал "алюминий", см.
    docstring FUSED_CODE_SUFFIX в product_name_signature_props.py);
    build_signature сливает fused_props в name_props/check_props — второй
    словарь свойств из цифрового токена здесь не заводим (ПРАВИЛО №6)."""
    out = set()
    fused_props: dict = {}
    total = len(words)
    for i, w in enumerate(words):
        if _HAS_DIGIT_RE.search(w):
            if _is_store_tail_code(w, i, total):
                continue
            norm = _KEEP_ALNUM_RE.sub("", w)
            if not norm:
                continue
            m = _UNIT_SUFFIX_RE.match(norm)
            if m and (m.group(2) in UNIT_WORDS or fold_brand_or_code(m.group(2)) in UNIT_WORDS):
                continue
            norm = _strip_known_market_suffix(norm)
            # Суффикс материала/свойства, слитный с кодом (см. docstring
            # FUSED_CODE_SUFFIX) — снимается ТОЛЬКО если перед ним стоит
            # цифра (иначе это не суффикс кода модели, а обычная буква
            # внутри слова, например часть аббревиатуры).
            last_folded = fold_brand_or_code(norm[-1]) if norm else ""
            if len(norm) > 3 and last_folded in FUSED_CODE_SUFFIX and norm[-2].isdigit():
                group, value = FUSED_CODE_SUFFIX[last_folded]
                fused_props.setdefault(group, set()).add(value)
                norm = norm[:-1]
            out.add(norm)
            # буква-модификатор модели сразу после кода (см. docstring
            # _MODEL_MODIFIER_LETTER_RE выше) — добавляем СОСТАВНЫМ токеном
            # (не заменяем базовый код), поэтому разница "код+буква" vs
            # просто "код" делает множества разными (гейт), а при совпадении
            # буквы с обеих сторон множества остаются равными.
            if i + 1 < total:
                nxt = words[i + 1]
                if (_MODEL_MODIFIER_LETTER_RE.match(nxt)
                        and not _HAS_DIGIT_RE.search(nxt)
                        and nxt not in _STOPWORDS):
                    if nxt == "з" and "з" in FUSED_CODE_SUFFIX:
                        # «ОП-2 (з)» через пробел — то же свойство «закачной»,
                        # что и слитное «ОП-2(з)» (см. FUSED_CODE_SUFFIX["з"]),
                        # не модификатор индекса модели.
                        group, value = FUSED_CODE_SUFFIX["з"]
                        fused_props.setdefault(group, set()).add(value)
                    else:
                        out.add(f"{norm}·{nxt}")
    return frozenset(out), fused_props


def _word_set(words: list[str]) -> frozenset:
    return frozenset(
        w for i, w in enumerate(words)
        if not _HAS_DIGIT_RE.search(w)
        and w not in _STOPWORDS
        and not (w == "з" and i > 0 and _HAS_DIGIT_RE.search(words[i - 1]))
    )


_HAS_LETTER_RE = re.compile(r"[a-zа-яё]")
_DIM_LIKE_TOKEN_RE = re.compile(r"^\d+(?:[хx]\d+)+$")
_PAPER_FORMAT_TOKENS = frozenset({"а0", "а1", "а2", "а3", "а4", "а5", "а6"})


def _model_code_tokens(digit_tokens: frozenset) -> frozenset:
    """Подмножество digit_tokens, где ХОТЬ ОДНА буква есть в токене — это
    настоящий код/индекс модели (РС-50, ОУ-5, СЛК-П20). "Голые" числа без
    единой буквы (43, 6005, 3247), чисто размерные токены вида NхM (5х10,
    20х20) и форматы бумаги (А4, А3) сюда не входят (владелец, 28.10.2026,
    п.1 — "голые числа без букв сами по себе пары не образуют"): такие токены
    остаются в digit_tokens (match() всё равно требует их точного совпадения),
    но для ПОИСКА кандидатов на сведение (group_key ниже) они недостаточны."""
    return frozenset(
        t for t in digit_tokens
        if _HAS_LETTER_RE.search(t)
        and not _DIM_LIKE_TOKEN_RE.match(t)
        and t not in _PAPER_FORMAT_TOKENS
    )


_PRODUCT_TYPE_WINDOW = 5


_PRODUCT_TYPE_STOP_PREPOSITIONS = frozenset({"для", "под", "к", "от"})


def _extract_product_type(name: Optional[str]) -> Optional[str]:
    """Вид товара — СУЩЕСТВИТЕЛЬНОЕ-вид ИЗ СЛОВАРЯ (product_name_signature_
    props.PRODUCT_TYPE_{PHRASES,WORDS}), найденное СРЕДИ ПЕРВЫХ 5 СЛОВ
    названия (владелец, доп. ревью Кувалда↔Бауцентр, 27.10.2026) — ПЕРЕДЕЛАНО
    со старого "вид = первое слово": Бауцентр часто ставит первым
    прилагательное ("Отбойный молоток", "Ленточная шлифмашина", "Угловая
    шлифмашина"), и старое правило ложно считало вид неопределённым или
    видело "первое слово = прилагательное" как сам вид. Прилагательные в
    словарь НЕ заводятся — они просто пропускаются при поиске, и находится
    следующее слово-существительное. Если словарное существительное не
    нашлось ни в одной из первых 5 слов НИ У ОДНОЙ стороны — вид не
    участвует в сравнении (не противоречие, п.4 исходной постановки), а не
    "вид = само слово" (второй словарь-угадайку сверх PRODUCT_TYPE_WORDS не
    заводим).

    Ограничение по предлогам назначения ("для", "под", "к", "от") и
    ACCESSORY_MARKERS: у принадлежностей ("Подставка под огнетушитель ОП-2",
    "Держатель для рации", "Чехол для болгарки") существительное ПОСЛЕ
    предлога — это целевой предмет, а не вид самого товара."""
    if not name:
        return None
    # Та же чистка, что и перед токенизацией индекса (см. _split_words) —
    # иначе слитное "ОУ-5-ВСЕ" и раздельное "ОУ-5 ВСЕ" дают РАЗНЫЕ слова
    # только из-за формата написания класса пожара, а не потому что это
    # разный вид товара (регрессия на test_fire_class_fused_or_spaced_
    # still_matches, владелец, 27.10.2026).
    cleaned = _pre_clean(name)
    folded = fold_brand_or_code(cleaned)
    words = [w for w in (_EDGE_PUNCT_RE.sub("", w) for w in folded.split()) if w]
    raw_window = words[:_PRODUCT_TYPE_WINDOW]
    if not raw_window:
        return None
    window = []
    for idx, w in enumerate(raw_window):
        w_clean = w.strip("-")
        if idx > 0 and w_clean in _PRODUCT_TYPE_STOP_PREPOSITIONS:
            break
        window.append(w)
    if not window:
        return None
    window_text = " ".join(window)

    # Многословные фразы — по вхождению ЛЮБОГО места в окне (не только с
    # начала строки), самое раннее совпадение в окне побеждает (при равных
    # позициях — более длинная фраза, поэтому сортировка по длине убыв.).
    best_canon, best_pos = None, None
    for phrase, canon in sorted(PRODUCT_TYPE_PHRASES.items(), key=lambda kv: -len(kv[0])):
        m = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", window_text)
        if m and (best_pos is None or m.start() < best_pos):
            best_canon, best_pos = canon, m.start()
    if best_canon:
        return best_canon

    for w in window:
        w_clean = w.strip("-")
        canon = PRODUCT_TYPE_WORDS.get(w_clean)
        if canon:
            return canon
    return None


def _first_raw_word(name: str) -> Optional[str]:
    """Первое слово названия БЕЗ fold_brand_or_code — для сравнения "первое
    слово = бренд целиком" простым .lower() (см. build_signature)."""
    cleaned = _pre_clean(name)
    m = re.match(r"\S+", cleaned.strip())
    if not m:
        return None
    return _EDGE_PUNCT_RE.sub("", m.group(0)).strip("-")


def _overlap_coefficient(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0 if (a or b) else 1.0
    exact = a & b
    inter = len(exact)
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    rem_small = small - exact
    rem_large = large - exact
    if rem_small and rem_large:
        large_phonetic: set = set()
        for w in rem_large:
            if len(w) >= _PHONETIC_MIN_WORD_LEN or w in _MANUAL_BRAND_PHONETIC_ALIASES:
                large_phonetic.update(_brand_phonetic_keys_for(w))
        if large_phonetic:
            for w in rem_small:
                if len(w) >= _PHONETIC_MIN_WORD_LEN or w in _MANUAL_BRAND_PHONETIC_ALIASES:
                    if _brand_phonetic_keys_for(w) & large_phonetic:
                        inter += 1
    return min(1.0, inter / min(len(a), len(b)))


# ---------------------------------------------------------------------------
# Слово, "похожее на бренд", латиницей (владелец, доп. ревью Delta/Security
# Force/BT аккумуляторов, 27.10.2026, п.2 дефекта пробного прогона
# merge_by_name_model: "Delta DT 1240" и "Security Force SF 1240" были
# сведены — бренды РАЗНЫЕ, но ни manufacturer, ни словарь брендов их не
# распознали, а порог похожести слов (_overlap_coefficient) был обойдён,
# т.к. совпал словарный вид товара "аккумулятор"). Если официальный бренд
# НЕ подтвердил совпадение (пустой или не совпал хотя бы с одной стороны —
# иначе разный brand_fold уже дал бы "no" раньше в match()), а в названии
# есть латинское слово с заглавной буквы (Title Case, "Delta") или ВСЕ
# ЗАГЛАВНЫЕ ("SF", "BT", "DT", не словарное слово вида/свойства — те все
# кириллические, см. product_name_signature_props.py, поэтому отдельно их
# исключать не нужно) — это, скорее всего, тоже бренд/код, который словарь
# просто не знает. Обе стороны назвали такое слово и множества НЕ
# пересекаются → разные бренды, не повод доверять overlap общих родовых слов
# названия ("аккумуляторная батарея").
_LATIN_WORD_RE = re.compile(r"^[A-Za-z]+$")


def _is_brand_like_word(word: str) -> bool:
    if len(word) < 2 or not _LATIN_WORD_RE.match(word):
        return False
    return word.isupper() or (word[0].isupper() and word[1:].islower())


def _extract_brand_like_words(name: Optional[str]) -> frozenset:
    """Латинские слова-кандидаты в бренд — из ОРИГИНАЛЬНОГО текста (НЕ через
    fold_brand_or_code: та функция схлопывает часть латиницы в кириллицу-
    гомоглиф и ломает регистр, а здесь важен именно регистр написания, см.
    docstring выше). Чистка единиц/класса пожара — та же, что у _split_words
    (для единообразия; "200х200" и т.п. всё равно отсеются фильтром "только
    буквы")."""
    if not name:
        return frozenset()
    cleaned = _pre_clean(name)
    words = (_EDGE_PUNCT_RE.sub("", w) for w in cleaned.split())
    return frozenset(w.lower() for w in words if w and _is_brand_like_word(w))


# ---------------------------------------------------------------------------
# Свойства из названия (цвет/материал/страна/класс пожара/комплектация/
# исполнение) — группы и словари см. product_name_signature_props.py.
# ---------------------------------------------------------------------------

_FIRE_CLASS_LATIN_TO_CYR = str.maketrans("ABCED", "АВСЕД")
_POWDER_EXT_RE = re.compile(r"\bоп[-\s]?\d|порошков|поршков", re.IGNORECASE)


def _extract_name_properties(name: Optional[str]) -> dict:
    if not name:
        return {}
    props: dict = {}
    cleaned_for_props = _strip_extinguisher_notes(name)
    is_powder_ext = bool(_POWDER_EXT_RE.search(cleaned_for_props))

    # Класс пожара — ТОЛЬКО по оригинальному тексту (регистр важен, см.
    # product_name_signature_props.FIRE_CLASS_RE): буквы класса пишутся
    # заглавными, строчные совпадения (обычные слова) не должны считаться.
    fire_classes = set()
    for m in FIRE_CLASS_RE.finditer(cleaned_for_props):
        raw_fc = m.group(1) or m.group(2)
        if not raw_fc:
            continue
        fc = raw_fc.upper().translate(_FIRE_CLASS_LATIN_TO_CYR)
        if is_powder_ext and fc == "ВСЕ":
            fc = "АВСЕ"
        fire_classes.add(fc)
    if fire_classes:
        props["класс пожара"] = fire_classes

    folded = fold_brand_or_code(cleaned_for_props)
    words = [w for w in (_EDGE_PUNCT_RE.sub("", w) for w in folded.split()) if w]
    raw_color_tokens = [
        _EDGE_PUNCT_RE.sub("", w)
        for w in re.split(r"[\s\-/]+", cleaned_for_props.lower())
        if w
    ]

    colors = {COLOR_WORDS[w] for w in words if w in COLOR_WORDS} | {
        COLOR_WORDS[w] for w in raw_color_tokens if w in COLOR_WORDS
    }
    if colors:
        props["цвет"] = colors

    materials = {MATERIAL_WORDS[w] for w in words if w in MATERIAL_WORDS}
    if materials:
        props["материал"] = materials

    countries = {COUNTRY_WORDS[w] for w in words if w in COUNTRY_WORDS}
    if countries:
        props["страна"] = countries

    executions = {EXECUTION_WORDS[w] for w in words if w in EXECUTION_WORDS}
    for phrase, canon in EXECUTION_PHRASES.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            executions.add(canon)
    if executions:
        props["исполнение"] = executions

    ext_subtypes = {EXTINGUISHER_SUBTYPE_WORDS[w] for w in words if w in EXTINGUISHER_SUBTYPE_WORDS}
    if ext_subtypes:
        props["тип огнетушителя"] = ext_subtypes

    packaging = set()
    for phrase, canon in PACKAGING_PHRASES.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            packaging.add(canon)
    m = _PACKAGING_SET_RE.search(folded)
    if m:
        packaging.add(f"набор {m.group(1)} шт")
    m = _BATTERY_COUNT_RE.search(folded)
    if m:
        packaging.add(f"{m.group(1)} акб")
    m = _BATTERY_CAPACITY_RE.search(folded)
    if m:
        packaging.add(f"{m.group(1)}x{m.group(2).replace(',', '.')} ач")
    if packaging:
        props["комплектация"] = packaging

    return props


# ---------------------------------------------------------------------------
# Группы "указано у одного ⇒ check" (владелец, ревью 113 авто-пар,
# 27.10.2026, п.2) — см. докстринг словарей в product_name_signature_props.
# Отдельная функция/отдельные группы от _extract_name_properties ВЫШЕ —
# семантика разная (там "указано у одного — не мешает", здесь "указано у
# одного — check"), поэтому ключи групп НЕ пересекаются с теми props.
# ---------------------------------------------------------------------------

_CHECK_WORD_GROUPS = (
    ("сторонность", SIDEDNESS_WORDS),
    ("перекрывной", SHUTOFF_WORDS),
    ("тип рукава", HOSE_TYPE_WORDS),
    ("покрытие", COATING_WORDS),
    ("установка", INSTALL_MODE_WORDS),
    ("тип ствола", NOZZLE_TYPE_WORDS),
)
_CHECK_PHRASE_GROUPS = (
    ("комплектация(доп)", EXTRA_PACKAGING_PHRASES),
    ("покрытие", COATING_PHRASES),
    ("зарядное устройство", CHARGER_PHRASES),
    ("упаковка", CARRY_CASE_PHRASES),
)


def _extract_check_properties(name: Optional[str]) -> dict:
    if not name:
        return {}
    props: dict = {}
    cleaned = _strip_extinguisher_notes(name)
    folded = fold_brand_or_code(cleaned)
    words = [w for w in (_EDGE_PUNCT_RE.sub("", w) for w in folded.split()) if w]

    for group, word_dict in _CHECK_WORD_GROUPS:
        values = {word_dict[w] for w in words if w in word_dict}
        if values:
            props.setdefault(group, set()).update(values)

    for group, phrase_dict in _CHECK_PHRASE_GROUPS:
        for phrase, canon in phrase_dict.items():
            if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
                props.setdefault(group, set()).add(canon)

    return props


# ---------------------------------------------------------------------------
# Характеристики из JSON (characteristics: [{name, value, unit}, ...]) —
# масса (с переводом единиц) + "остальные" по совпавшему нормализованному
# имени. ОДНА функция извлечения (_characteristic_values), оба потребителя
# (вес-приоритет и общая проверка) читают из неё — ПРАВИЛО №6.
# ---------------------------------------------------------------------------

_MASS_TO_GRAMS = {
    "мг": 0.001, "г": 1.0, "гр": 1.0, "грамм": 1.0,
    "кг": 1000.0, "килограмм": 1000.0, "т": 1_000_000.0, "тонна": 1_000_000.0,
}
_LENGTH_TO_MM = {
    "мм": 1.0, "миллиметр": 1.0, "см": 10.0, "сантиметр": 10.0,
    "дм": 100.0, "м": 1000.0, "метр": 1000.0, "км": 1_000_000.0,
}

_MASS_NAME_RE = re.compile(r"масс|вес")
_NON_TOTAL_MASS_NAME_RE = re.compile(
    r"состав|заряд|отв\b|веществ|порошк|пуст|человек|пользовател|нагрузк|бель|подставк"
)
_NUMERIC_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
# "(не более)", "(до)" и т.п. — уточнение способа измерения, не другая
# характеристика; срезается ПЕРЕД сравнением нормализованных имён.
_QUALIFIER_PAREN_RE = re.compile(r"\([^)]*\)")
_TRAILING_UNIT_RE = re.compile(r",\s*[a-zа-яё°²³/]+\.?$", re.IGNORECASE)

# Характеристики, не относящиеся к самому товару (логистика магазина,
# номера строки) или дублирующие поля бренда/габаритов упаковки — общая
# проверка их игнорирует, см. docstring from_store_nomenclature.py.
_IGNORED_CHAR_NAME_SUBSTRINGS = (
    "магазин-источник", "артикул", "параметр ", "раздел", "категория",
    "модель производителя", "торговая марка", "бренд", "производитель",
    "габарит", "высота", "длина", "ширина", "глубина", "диаметр",
    "сроки, заявленные", "при активации",
)


def _normalize_char_name(name: str) -> str:
    name = _QUALIFIER_PAREN_RE.sub("", name or "")
    name = _TRAILING_UNIT_RE.sub("", name)
    return fold_brand_or_code(name).strip()


def merge_characteristics(primary: Optional[list], secondary: Optional[list]) -> list:
    """ЕДИНСТВЕННАЯ функция слияния списков характеристик без потери данных
    (ПРАВИЛО №6 — переиспользует _normalize_char_name и clean_characteristics_list,
    вызывается из product_merge.py, products_import_apply.py и офлайн-консолидатора
    JSON). Все характеристики primary сохраняются (с очисткой единиц и квалификаторов);
    из secondary дописываются те, чьего нормализованного имени ещё нет в primary."""
    if not primary and not secondary:
        return []
    combined = list(primary or []) + list(secondary or [])
    cleaned = clean_characteristics_list(combined)
    out: list[dict] = []
    seen_keys: set[str] = set()
    for c in cleaned:
        k = _normalize_char_name(c.get("name") or "")
        if not k or k in seen_keys:
            continue
        seen_keys.add(k)
        out.append(c)
    return out


def merge_price_links(
    primary: Optional[list],
    secondary: Optional[list],
    *,
    update_existing_prices: bool = False,
) -> list:
    """ЕДИНСТВЕННАЯ функция объединения массивов ссылок и цен [{url, price, ...}]
    по URL (ПРАВИЛО №6 — используется в product_merge.py, products_import_apply.py
    и офлайн-консолидаторе JSON). Новые URL добавляются в конец; для уже
    существующего URL цена обновляется, если update_existing_prices=True (импорт
    свежей строки) или если у существующей записи price пуст."""
    if not primary and not secondary:
        return []
    out: list[dict] = []
    by_url: dict[str, dict] = {}
    for item in (primary or []):
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url or url in by_url:
            continue
        entry = dict(item)
        by_url[url] = entry
        out.append(entry)

    for item in (secondary or []):
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        new_price = item.get("price")
        if url in by_url:
            existing = by_url[url]
            if new_price is not None and (update_existing_prices or existing.get("price") is None):
                existing["price"] = new_price
            for k, v in item.items():
                if k not in ("url", "price") and v is not None and not existing.get(k):
                    existing[k] = v
        else:
            entry = dict(item)
            by_url[url] = entry
            out.append(entry)
    return out


def _parse_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = _NUMERIC_RE.search(value.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _characteristic_values(characteristics: list) -> dict:
    """normalized_name -> (display_name, tag, numeric_or_text). tag ∈
    {"mass", "length", "text"} — единицы, которые умеем переводить для
    сравнения; "text" сравнивается как нормализованная строка. Первая
    характеристика с данным нормализованным именем побеждает (обычно их
    ровно одна)."""
    out: dict = {}
    for c in characteristics or []:
        raw_name = (c or {}).get("name") or ""
        norm = _normalize_char_name(raw_name)
        if not norm or any(s in norm for s in _IGNORED_CHAR_NAME_SUBSTRINGS):
            continue
        if norm in out:
            continue
        value = (c or {}).get("value")
        raw_unit = ((c or {}).get("unit") or "").strip()
        unit = (normalize_characteristic_unit(raw_unit) or raw_unit).lower()
        if not unit:
            # единица может быть внутри значения ("2 г", "5,8 кг")
            m = re.search(r"([a-zа-яё]+)\.?\s*$", (value or "").strip().lower())
            if m:
                u_cand = m.group(1)
                unit = (normalize_characteristic_unit(u_cand) or u_cand).lower()
        number = _parse_number(value)
        if number is not None and unit in _MASS_TO_GRAMS:
            out[norm] = (raw_name, "mass", number * _MASS_TO_GRAMS[unit])
        elif number is not None and unit in _LENGTH_TO_MM:
            out[norm] = (raw_name, "length", number * _LENGTH_TO_MM[unit])
        else:
            text = fold_brand_or_code(str(value) if value is not None else "")
            out[norm] = (raw_name, "text", text)
    return out


def _is_total_mass_key(k: str) -> bool:
    return bool(_MASS_NAME_RE.search(k)) and not bool(_NON_TOTAL_MASS_NAME_RE.search(k))


def _mass_conflict(a_chars: dict, b_chars: dict, *, has_model_code: bool = False) -> Optional[str]:
    a_mass = next(((k, v) for k, v in a_chars.items() if _is_total_mass_key(k) and v[1] == "mass"), None)
    b_mass = next(((k, v) for k, v in b_chars.items() if _is_total_mass_key(k) and v[1] == "mass"), None)
    if not a_mass or not b_mass:
        return None
    _, (a_disp, _, a_grams) = a_mass
    _, (b_disp, _, b_grams) = b_mass
    # При совпавшем коде модели (например, ОП-2) разные магазины указывают вес
    # нетто/брутто/паспортный предел с разбросом до ~15% (2,79 кг vs 2,9 кг vs 3,2 кг);
    # расхождение ≥20% (4 кг vs 5 кг) по-прежнему блокирует слияние.
    tol = max(50.0, 0.15 * max(abs(a_grams), abs(b_grams))) if has_model_code else 0.5
    if abs(a_grams - b_grams) > tol:
        return (f"масса различается: «{a_disp}»={a_grams / 1000:g} кг "
                f"≠ «{b_disp}»={b_grams / 1000:g} кг")
    return None


def _other_characteristics_diff(a_chars: dict, b_chars: dict) -> Optional[str]:
    """Сравнивает характеристики, у которых нормализованное имя совпало
    буквально между товарами (масса уже проверена отдельно — пропускаем).
    Где имена НЕ совпали — не сравниваем (владелец, уточнение 2: "где не
    уверен — не сравнивай", вторую словарь синонимов характеристик здесь не
    заводим)."""
    for key, (a_disp, a_tag, a_val) in a_chars.items():
        if _is_total_mass_key(key):
            continue
        b_entry = b_chars.get(key)
        if not b_entry:
            continue
        b_disp, b_tag, b_val = b_entry
        if a_tag != b_tag:
            continue  # разный тип значения — не уверены, не сравниваем
        if a_tag == "text":
            if a_val and b_val and a_val != b_val:
                return f"«{a_disp}» {a_val!r} ≠ «{b_disp}» {b_val!r}"
        else:
            if abs(a_val - b_val) > max(0.5, 0.01 * max(abs(a_val), abs(b_val))):
                return f"«{a_disp}» {a_val:g} ≠ «{b_disp}» {b_val:g}"
    return None


# ---------------------------------------------------------------------------
# Числа-с-единицей ПРЯМО В НАЗВАНИИ (владелец, доп. ревью Кувалда↔Бауцентр,
# 27.10.2026, последняя правка): раньше такие числа ("18 В", "2,0 кВт",
# "950 Вт") были только "свойством, не индексом" (п.4 — не блокируют индекс-
# гейт) и больше ни с чем не сравнивались. Теперь — ОТДЕЛЬНЫЙ гейт: если
# ОБЕ стороны называют одну и ту же физическую величину (мощность/масса/
# объём/длина/полная мощность/ёмкость АКБ/энергия удара) ПРЯМО В НАЗВАНИИ,
# переводим в одну единицу (кВт↔Вт, кг↔г, л↔мл, м↔см↔мм, кВА↔ВА, Ач↔мАч) и
# сравниваем — "2,0 кВт" (=2000 Вт) ≠ "2500 Вт" → no. Указано у ОДНОЙ
# стороны (мощности в названии нет совсем) — НЕ противоречие (п.4
# сохраняется), см. test "MAKITA M8701B" (мощность только у Бауцентра).
# Переводные таблицы — ПЕРЕИСПОЛЬЗУЕМ _MASS_TO_GRAMS/_LENGTH_TO_MM
# (ПРАВИЛО №6, та же масса/длина, что и у characteristics JSON выше).
_VOLUME_TO_ML = {"мл": 1.0, "л": 1000.0}
_VA_TO_VA = {"ва": 1.0, "ква": 1000.0}
_CAPACITY_TO_MAH = {"мач": 1.0, "ач": 1000.0}
_ENERGY_TO_J = {"дж": 1.0}
_POWER_TO_W = {"вт": 1.0, "квт": 1000.0, "мвт": 1_000_000.0}
_COUNT_TO_PCS = {"шт": 1.0, "компл": 1.0}
_VOLTAGE_TO_V = {"в": 1.0, "кв": 1000.0}


def _build_name_quantity_unit_re(unit_table: dict) -> re.Pattern:
    # Та же сборка, но с ЗАХВАТОМ самой единицы (группа 2) — нужна, чтобы
    # узнать, КАКАЯ единица сработала, и перевести по таблице.
    alt = "|".join(sorted((re.escape(u) for u in unit_table), key=len, reverse=True))
    return re.compile(
        rf"(?<![0-9a-zA-Zа-яёА-ЯЁ\-])(\d+(?:[.,]\d+)?)\s*({alt})"
        rf"(?![0-9a-zA-Zа-яёА-ЯЁ])",
        re.IGNORECASE,
    )


_NAME_QUANTITY_GROUPS = (
    ("мощность", _build_name_quantity_unit_re(_POWER_TO_W), _POWER_TO_W),
    ("масса", _build_name_quantity_unit_re(_MASS_TO_GRAMS), _MASS_TO_GRAMS),
    ("объём", _build_name_quantity_unit_re(_VOLUME_TO_ML), _VOLUME_TO_ML),
    ("длина", _build_name_quantity_unit_re(_LENGTH_TO_MM), _LENGTH_TO_MM),
    ("полная мощность", _build_name_quantity_unit_re(_VA_TO_VA), _VA_TO_VA),
    ("ёмкость АКБ", _build_name_quantity_unit_re(_CAPACITY_TO_MAH), _CAPACITY_TO_MAH),
    ("энергия удара", _build_name_quantity_unit_re(_ENERGY_TO_J), _ENERGY_TO_J),
    ("количество", _build_name_quantity_unit_re(_COUNT_TO_PCS), _COUNT_TO_PCS),
    ("напряжение", _build_name_quantity_unit_re(_VOLTAGE_TO_V), _VOLTAGE_TO_V),
)


def _extract_name_quantities(name: Optional[str]) -> dict:
    """group -> множество значений в базовой единице (Вт/г/мл/мм/ВА/мАч/Дж),
    извлечённых ПРЯМО из названия (не из characteristics JSON — та же
    "вес"-логика, что у _characteristic_values, но от текста, см. docstring
    блока выше). Несколько чисел одной группы в одном названии — редкость,
    но собираем множеством на случай "800/1000 Вт" двух режимов."""
    if not name:
        return {}
    folded = fold_brand_or_code(name)
    out: dict = {}
    for group, regex, table in _NAME_QUANTITY_GROUPS:
        values = set()
        for m in regex.finditer(folded):
            number = _parse_number(m.group(1))
            unit = m.group(2)
            if number is None or unit not in table:
                continue
            values.add(round(number * table[unit], 3))
        if values:
            out[group] = values
    inch_vals = _extract_inch_diagonal(name)
    if inch_vals:
        out["диагональ"] = inch_vals
    return out


def _name_quantity_conflict(a_qty: dict, b_qty: dict) -> Optional[str]:
    """Указано у ОБЕИХ сторон и не совпадает (с допуском на округление —
    та же формула, что у _other_characteristics_diff) → противоречие;
    указано только у одной — НЕ противоречие (п.4)."""
    for group, a_vals in a_qty.items():
        b_vals = b_qty.get(group)
        if not b_vals:
            continue
        tol = lambda v: max(0.5, 0.01 * abs(v))  # noqa: E731
        if len(a_vals) == len(b_vals) and len(a_vals) > 1:
            sa, sb = sorted(a_vals), sorted(b_vals)
            if not all(abs(av - bv) <= max(tol(av), tol(bv)) for av, bv in zip(sa, sb)):
                return f"{group} в названии {sa} ≠ {sb}"
        elif not any(abs(av - bv) <= max(tol(av), tol(bv)) for av in a_vals for bv in b_vals):
            return f"{group} в названии {sorted(a_vals)} ≠ {sorted(b_vals)}"
    return None


# ---------------------------------------------------------------------------
# Размеры Д*Ш*В ЧЕРЕЗ "х"/"x" ПРЯМО В НАЗВАНИИ (владелец, доп. ревью Delta/
# Security Force/BT аккумуляторов, 27.10.2026, п.2 дефекта: "198х166х170 мм"
# ≠ "195х165х170 мм" — последняя ось совпала, но это НЕ повод считать
# габарит одним и тем же). ОТДЕЛЬНО от _NAME_QUANTITY_GROUPS выше (ПРАВИЛО
# №6 — это не дубль той же проверки, а другая форма данных): там "указано у
# обоих хоть одно совпавшее значение — не противоречие" — верно для ОДНОЙ
# физической величины, измеренной по-разному; здесь — ТРИ РАЗНЫЕ оси одного
# габарита разом, совпадение одной оси ("170") ничего не говорит об
# остальных, поэтому сравниваем целую последовательность чисел, а не
# множество отдельных значений. Единицы — ТЕ ЖЕ _LENGTH_TO_MM (ПРАВИЛО №6,
# второй список единиц длины не заводим).
_DIM_LENGTH_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _LENGTH_TO_MM), key=len, reverse=True))
_NAME_DIMENSIONS_RE = re.compile(
    rf"(?<![0-9a-zA-Zа-яёА-ЯЁ])(\d+(?:[.,]\d+)?(?:\s*[xXхХ×*]\s*\d+(?:[.,]\d+)?)+)"
    rf"\s*({_DIM_LENGTH_UNIT_ALT})(?![0-9a-zA-Zа-яёА-ЯЁ])",
    re.IGNORECASE,
)

# Та же величина, но единица измерения повторена ПРИ КАЖДОЙ оси ("300мм х
# 300мм", а не слитное "300х300 мм") — владелец, доп. ревью клапанов,
# 28.10.2026: "Клапан противопожарный КЛОП-1 300мм х 300мм" — без этого
# разбора 300/300 не распознаются как Д×Ш вообще (не попадают ни в
# digit_tokens как код — число+единица вырезается _strip_unit_quantities
# ДО токенизации, — ни в _NAME_DIMENSIONS_RE, рассчитанный на ОДНУ единицу
# в конце всей последовательности). Находим целый СПАН (две и более пары
# "число+единица", разделённые х/x), затем разбираем его парами через
# _DIM_PAIR_RE — отдельная единица на каждой оси допускает разные написания
# на разных осях ("300мм х 30см"), что для Д×Ш×В магазинов не характерно,
# но и не мешает (переводим обе в мм одной и той же таблицей).
_DIM_PAIR_RE = re.compile(rf"(\d+(?:[.,]\d+)?)\s*({_DIM_LENGTH_UNIT_ALT})", re.IGNORECASE)
_NAME_DIMENSIONS_SPACED_SPAN_RE = re.compile(
    rf"(?<![0-9a-zA-Zа-яёА-ЯЁ])\d+(?:[.,]\d+)?\s*(?:{_DIM_LENGTH_UNIT_ALT})"
    rf"(?:\s*[xXхХ×*]\s*\d+(?:[.,]\d+)?\s*(?:{_DIM_LENGTH_UNIT_ALT}))+"
    rf"(?![0-9a-zA-Zа-яёА-ЯЁ])",
    re.IGNORECASE,
)


def _extract_name_dimensions(name: Optional[str]) -> frozenset:
    """Множество кортежей чисел (в мм) — каждое найденное "NхNхN...+единица"
    (фьюжн, _NAME_DIMENSIONS_RE) ИЛИ "N+единица х N+единица..." (единица на
    каждой оси, _NAME_DIMENSIONS_SPACED_SPAN_RE) в названии как ЦЕЛАЯ
    последовательность (не отдельные числа, см. docstring блока выше)."""
    if not name:
        return frozenset()
    folded = fold_brand_or_code(name)
    out = set()
    for m in _NAME_DIMENSIONS_RE.finditer(folded):
        factor = _LENGTH_TO_MM.get(m.group(2))
        if factor is None:
            continue
        nums = []
        for part in re.split(r"[xXхХ×*]", m.group(1)):
            n = _parse_number(part)
            if n is None:
                nums = None
                break
            nums.append(round(n * factor, 3))
        if nums:
            out.add(tuple(nums))
    for span in _NAME_DIMENSIONS_SPACED_SPAN_RE.finditer(folded):
        pairs = _DIM_PAIR_RE.findall(span.group(0))
        nums = []
        for num_str, unit in pairs:
            factor = _LENGTH_TO_MM.get(unit.lower())
            n = _parse_number(num_str)
            if factor is None or n is None:
                nums = None
                break
            nums.append(round(n * factor, 3))
        if nums and len(nums) >= 2:
            out.add(tuple(nums))
    return frozenset(out)


def _name_dimensions_conflict(
    a_dims: frozenset,
    b_dims: frozenset,
    a_qty: Optional[dict] = None,
    b_qty: Optional[dict] = None,
) -> Optional[str]:
    """Указано у ОБЕИХ сторон (хотя бы один габарит с каждой) и НИ ОДНА пара
    одинаковой длины (кол-ва осей) не совпадает по ВСЕМ осям разом (с
    допуском на округление) → противоречие; указано только у одной — не
    противоречие (п.4), КРОМЕ случая, когда у одной стороны задан многоосевой
    размер Д×Ш (например, электроды «3,0x350 мм»), а у другой — одиночный
    размер в мм («2,5 мм») и ни одно значение одиночного размера не совпадает
    ни с одной осью многоосевого габарита."""
    tol = lambda v: max(0.5, 0.01 * abs(v))  # noqa: E731
    if a_dims and b_dims:
        for a_tuple in a_dims:
            for b_tuple in b_dims:
                if len(a_tuple) == len(b_tuple) and all(
                    abs(x - y) <= max(tol(x), tol(y)) for x, y in zip(a_tuple, b_tuple)
                ):
                    return None
        return f"размеры в названии {sorted(a_dims)} ≠ {sorted(b_dims)}"
    a_len = (a_qty or {}).get("длина")
    b_len = (b_qty or {}).get("длина")
    if a_dims and not b_dims and b_len and not a_len:
        axes = {axis for tup in a_dims for axis in tup}
        if not any(abs(lv - ax) <= min(0.2, 0.01 * max(abs(lv), abs(ax))) for lv in b_len for ax in axes):
            return f"размеры в названии {sorted(a_dims)} ≠ {sorted(b_len)}"
    if b_dims and not a_dims and a_len and not b_len:
        axes = {axis for tup in b_dims for axis in tup}
        if not any(abs(lv - ax) <= min(0.2, 0.01 * max(abs(lv), abs(ax))) for lv in a_len for ax in axes):
            return f"размеры в названии {sorted(a_len)} ≠ {sorted(b_dims)}"
    return None


# ---------------------------------------------------------------------------
# Сигнатура товара и match()
# ---------------------------------------------------------------------------

@dataclass
class ProductSignature:
    name: str
    brand: Optional[str]
    brand_fold: str
    digit_tokens: frozenset
    word_set: frozenset
    name_props: dict
    check_props: dict = field(default_factory=dict)
    product_type: Optional[str] = None
    char_values: dict = field(default_factory=dict)
    name_qty: dict = field(default_factory=dict)
    name_dims: frozenset = field(default_factory=frozenset)
    brand_like_words: frozenset = field(default_factory=frozenset)
    # Подмножество digit_tokens с буквой — настоящий код/индекс модели (см.
    # _model_code_tokens) — используется ТОЛЬКО для поиска кандидатов
    # (grouping_key), match() как и раньше сравнивает ПОЛНЫЙ digit_tokens.
    model_code_tokens: frozenset = field(default_factory=frozenset)
    brand_phonetic_keys: frozenset = field(default_factory=frozenset)
    raw_item: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Вид товара — явное поле выгрузки/карточки (Product.product_type/item
# ["product_type"]), ЕСЛИ оно содержательное, иначе — словарь по названию
# (владелец, 28.10.2026, п.1). "Содержательное" проверяется ТЕМ ЖЕ словарём
# PRODUCT_TYPE_WORDS/PHRASES (ПРАВИЛО №6 — не второй, менее строгий критерий
# "не пусто"): на реальных выгрузках (k_spasatel) поле product_type часто
# зашумлено брендом/моделью строки ("STRONG", "Aqua", "2-х") — такое значение
# НЕ каноническое слово-вид, и его слепое доверие дало бы вид=бренд. Если
# явное поле не подтверждено словарём ИЛИ совпадает с категорией (не несёт
# доп. информации) — используется старый путь, _extract_product_type(name).
# ---------------------------------------------------------------------------

_INVISIBLE_RE = re.compile(r"[​‌‍﻿\xa0]")


def _canon_product_type_value(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = _INVISIBLE_RE.sub("", raw).strip()
    if not cleaned:
        return None
    folded = fold_brand_or_code(cleaned).strip()
    canon = PRODUCT_TYPE_WORDS.get(folded)
    if canon:
        return canon
    for phrase, c in PRODUCT_TYPE_PHRASES.items():
        if phrase in folded:
            return c
    return None


def _resolve_product_type(item: dict, name: str) -> Optional[str]:
    explicit = item.get("product_type")
    category = item.get("category")
    if explicit and (not category or _INVISIBLE_RE.sub("", explicit).strip().lower()
                      != _INVISIBLE_RE.sub("", category).strip().lower()):
        canon = _canon_product_type_value(explicit)
        if canon:
            return canon
    return _extract_product_type(name)


def build_signature(item: dict, brand_dictionary=None) -> ProductSignature:
    """item — запись в формате GALA (name/manufacturer/characteristics...,
    см. app.services.catalog_gala.format). brand_dictionary — любой объект
    с `.find_in_name(name) -> str | None` (см. docstring модуля); можно не
    передавать — тогда бренд берётся только из manufacturer."""
    name = item.get("name") or ""
    manufacturer = item.get("manufacturer")

    # Порядок (п.1 исходной постановки): manufacturer, если не мусор —
    # ПЕРВЫЙ источник (и единственный для большинства строк: на реальных
    # выгрузках у sima_land/kns/regard/baucenter/kuvalda manufacturer не
    # мусорный почти всегда — см. backend/scripts/eval_name_signature.py).
    # Словарь брендов — ТОЛЬКО когда manufacturer пуст/мусорный (так и
    # эффективнее: find_in_name перебирает все известные бренды регуляркой,
    # вызывать это на каждой строке стотысячного каталога, где manufacturer
    # и так есть, — O(N×брендов) без всякой пользы).
    brand = None
    if manufacturer and not is_bogus_manufacturer(manufacturer, name):
        brand = manufacturer
    if not brand:
        for ch in item.get("characteristics") or []:
            if not isinstance(ch, dict):
                continue
            cname = (ch.get("name") or "").strip().lower()
            cval = (ch.get("value") or "").strip()
            if cname in ("бренд", "торговая марка", "производитель", "марка") and cval:
                if not is_bogus_manufacturer(cval, name):
                    brand = cval
                    break
    if not brand and brand_dictionary is not None:
        brand = brand_dictionary.find_in_name(name)
        if not brand and item.get("description"):
            brand = brand_dictionary.find_in_name(str(item.get("description"))[:160])

    # Бренд из одних цифр ("200") или стоп-слово (цвет/материал/страна/
    # общее слово по ошибке попавшее в manufacturer, "ОПС" и т.п. — тот же
    # STOP_BRAND_WORDS, что и у ТЗ 44-ФЗ, ПРАВИЛО №6, второй список не
    # заводим) — владелец, 27.10.2026: такой "бренд" считается НЕ
    # определённым (не participates в гейте сравнения брендов).
    if brand:
        key = _brand_compare_key(brand)
        folded_brand = fold_brand_or_code(brand).strip()
        if (
            not key
            or key.isdigit()
            or key in _BRAND_STOPWORD_KEYS
            or not _is_recognizable_brand_word(folded_brand)
        ):
            brand = None

    words = _split_words(name)
    # Сравнение бренда — ВСЕГДА через _brand_compare_key (_fold + только
    # буквы/цифры): "MAKITA" = "Makita" = "makita", "Sturm!" = "Sturm",
    # "Tech-KREP" = "Techkrep" (владелец, 27.10.2026, найден дефект — см.
    # docstring _fold выше).
    brand_fold = _brand_compare_key(brand) if brand else ""
    brand_phonetic_keys = _brand_phonetic_keys_for(brand) if brand else frozenset()

    # Вид товара — явное поле выгрузки, если содержательное (см.
    # _resolve_product_type), иначе по словарю PRODUCT_TYPE_WORDS/PHRASES,
    # найденному среди первых 5 слов (см. docstring _extract_product_type) —
    # брендовое слово само по себе в словарь не входит (это не родовое
    # существительное), поэтому отдельно "вид = бренд" больше не нужно
    # отсекать, как было со старым правилом "вид = первое слово" (владелец,
    # 27.10.2026, доп. ревью Кувалда↔Бауцентр): "Makita LXT DJR187Z" просто
    # не находит вид ни в одном слове — не противоречие (п.4).
    product_type = _resolve_product_type(item, name)

    digit_tokens, fused_props = _digit_tokens(words)
    name_props = _extract_name_properties(name)
    check_props = _extract_check_properties(name)
    # Суффиксы, слитные с кодом модели (см. FUSED_CODE_SUFFIX) — "материал"
    # и "закачной" сливаются в name_props (если указано только у одного — не
    # блокирует auto по п.4).
    for group, values in fused_props.items():
        if group in ("материал", "закачной"):
            name_props.setdefault(group, set()).update(values)
        else:
            check_props.setdefault(group, set()).update(values)

    return ProductSignature(
        name=name,
        brand=brand,
        brand_fold=brand_fold,
        digit_tokens=digit_tokens,
        word_set=_word_set(words),
        name_props=name_props,
        check_props=check_props,
        product_type=product_type,
        char_values=_characteristic_values(item.get("characteristics") or []),
        name_qty=_extract_name_quantities(name),
        name_dims=_extract_name_dimensions(name),
        brand_like_words=_extract_brand_like_words(name),
        model_code_tokens=_model_code_tokens(digit_tokens),
        brand_phonetic_keys=brand_phonetic_keys,
        raw_item=item,
    )


def grouping_key(sig: ProductSignature) -> Optional[tuple]:
    """Ключ группировки кандидатов на сведение (владелец, 28.10.2026, п.1):
    вид товара + код модели (цифро-буквенный токен, см.
    _model_code_tokens) — ПРАВИЛО №6, одна функция, её использует и
    scripts/merge_by_name_model.py, и services/products_import_match_name_
    model.py (вместо прежней группировки по ЛЮБОМУ общему числу названия,
    из-за которой "Тапочки размер 43"/"Коврик 43×28"/"KEDI Teste 43"
    случайно оказывались кандидатами друг на друга — общий был только
    голый номер без единой буквы).

    Возвращает None, если у сигнатуры НЕТ ни одного буквенно-цифрового кода
    в названии — "голые" числа сами по себе недостаточны как ключ поиска
    кандидатов (match() всё равно потом жёстко сравнивает ПОЛНЫЙ
    digit_tokens у конкретной пары — здесь только эффективный предварительный
    отбор, не ослабление самого гейта)."""
    if not sig.model_code_tokens:
        return None
    return (sig.product_type, sig.model_code_tokens)


_PROPERTY_CHECK_ORDER = ("класс пожара", "тип огнетушителя", "комплектация", "исполнение", "материал")


def _name_property_conflict(group: str, a: ProductSignature, b: ProductSignature) -> Optional[str]:
    va = a.name_props.get(group)
    vb = b.name_props.get(group)
    if va and vb and not (va & vb):
        return f"{group} {sorted(va)} ≠ {sorted(vb)}"
    return None


_ONE_SIDED_CHECK_GROUP_ORDER = (
    "сторонность", "перекрывной", "тип рукава", "комплектация(доп)",
    "покрытие", "зарядное устройство", "упаковка", "установка",
    "тип ствола",
)

# Группы, где расхождение у ОБЕИХ сторон — МЯГКИЙ сигнал ("check", не "no"):
# владелец, доп. ревью стволов 28.10.2026 — "РСК-50 (комбинированный)" ≠
# "РСК-50 (распылительный)" это, скорее всего, разные насадки, но не
# настолько очевидно, как расхождение цвета/материала/страны, чтобы решать
# автоматически "no" — решает человек. Остальные группы _ONE_SIDED_CHECK_
# GROUP_ORDER при расхождении у обоих остаются "no" (прежнее поведение).
_SOFT_CONFLICT_GROUPS = frozenset({"тип ствола"})


def _one_sided_property_result(a: ProductSignature, b: ProductSignature) -> Optional[dict]:
    """Группы из п.2 (владелец, ревью 113 авто-пар, 27.10.2026): указано у
    ОБОИХ и множества не пересекаются → "no" (разные товары, та же логика,
    что у _name_property_conflict), КРОМЕ _SOFT_CONFLICT_GROUPS выше — там
    расхождение у обоих тоже даёт только "check"; указано ТОЛЬКО у одного →
    "check" (не противоречие, но и не "совсем не важно" — решает человек).
    Проверяем ВСЕ группы (не выходим по первому "check"), чтобы "no" из
    группы, проверенной позже, не потерялось за более ранним "check"."""
    check_reason = None
    for group in _ONE_SIDED_CHECK_GROUP_ORDER:
        va = a.check_props.get(group)
        vb = b.check_props.get(group)
        if va and vb:
            if not (va & vb):
                reason = f"{group} {sorted(va)} ≠ {sorted(vb)}"
                if group in _SOFT_CONFLICT_GROUPS:
                    if check_reason is None:
                        check_reason = reason
                    continue
                return {"decision": "no", "reason": reason}
        elif va or vb:
            if check_reason is None:
                only = va or vb
                check_reason = f"{group} указан(о) только у одного: {sorted(only)}"
    if check_reason:
        return {"decision": "check", "reason": check_reason}
    return None


def _brands_match(a: ProductSignature, b: ProductSignature) -> bool:
    """Точное (через _brand_compare_key) ИЛИ фонетическое (кириллица↔латиница,
    двойные согласные: «Макита»=«Makita», «Бош»=«Bosch», «Штиль»=«Stihl»)
    совпадение бренда."""
    if not a.brand_fold or not b.brand_fold:
        return False
    if a.brand_fold == b.brand_fold:
        return True
    keys_a = a.brand_phonetic_keys or _brand_phonetic_keys_for(a.brand)
    keys_b = b.brand_phonetic_keys or _brand_phonetic_keys_for(b.brand)
    return bool(keys_a and keys_b and (keys_a & keys_b))


def _brand_like_words_match(words_a: frozenset, words_b: frozenset) -> bool:
    if not words_a or not words_b:
        return False
    if words_a & words_b:
        return True
    keys_a = {k for w in words_a for k in _brand_phonetic_keys_for(w)}
    keys_b = {k for w in words_b for k in _brand_phonetic_keys_for(w)}
    return bool(keys_a and keys_b and (keys_a & keys_b))


def match(a: ProductSignature, b: ProductSignature, peers_a: tuple = (), peers_b: tuple = ()) -> dict:
    """Решение «тот же товар» для двух строк РАЗНЫХ магазинов (п.6 —
    пары только между разными магазинами, этим занимается вызывающий код,
    здесь — только сама проверка). peers_a/peers_b — другие строки СВОЕГО
    магазина под тем же ключом (бренд+цифровые токены), для проверки
    однозначности (п.5)."""
    if a.brand_fold and b.brand_fold and not _brands_match(a, b):
        return {"decision": "no", "reason": f"бренд «{a.brand}» ≠ «{b.brand}»"}

    if a.product_type and b.product_type and a.product_type != b.product_type:
        return {"decision": "no", "reason": f"вид товара {a.product_type} ≠ {b.product_type}"}

    # Код модели (буква+цифра, model_code_tokens) — ЖЁСТКИЙ гейт, как и
    # раньше. "Голые" числа без единой буквы (digit_tokens - model_code_
    # tokens) — срочная правка владельца, 28.10.2026 (прод, 998
    # "неоднозначных" групп): "Монитор Hisense 27G3Q" ≠ "Монитор Hisense
    # 27\" 27G3Q" ложно получали "no" — голое число диагонали "27" требовало
    # точного совпадения множества вместе с кодом "27g3q". Теперь голые
    # числа — СВОЙСТВО: противоречие ТОЛЬКО если они есть у ОБЕИХ сторон И
    # множества различаются (гофрокороб д600 vs д500 остаётся no — там
    # цифры внутри буквенно-цифровых токенов "д600"/"ш400", то есть часть
    # model_code_tokens, не голые числа); указано только у одной стороны —
    # не противоречие (та же логика п.4, что и у остальных свойств).
    if a.model_code_tokens != b.model_code_tokens:
        return {
            "decision": "no",
            "reason": f"код модели в названии {sorted(a.model_code_tokens)} ≠ {sorted(b.model_code_tokens)}",
        }

    a_bare_numbers = a.digit_tokens - a.model_code_tokens
    b_bare_numbers = b.digit_tokens - b.model_code_tokens
    if a_bare_numbers and b_bare_numbers and a_bare_numbers != b_bare_numbers:
        return {
            "decision": "no",
            "reason": f"голые числа в названии {sorted(a_bare_numbers)} ≠ {sorted(b_bare_numbers)}",
        }

    # Брендов manufacturer/словарь НЕ подтвердил совпадение — но в названии
    # с обеих сторон есть латинское слово-кандидат в бренд, и множества не
    # пересекаются ("Delta" ≠ "Security Force" ≠ "BT") — вероятно разные
    # бренды, не словарные (см. docstring _extract_brand_like_words).
    # Проверяем ТОЛЬКО когда официальный бренд НЕ подтвердил совпадение —
    # иначе лишнее латинское слово у одной стороны при уже подтверждённом
    # общем бренде (manufacturer) не должно ложно давать "no" (тест ИБП CBR/
    # HP — там manufacturer совпадает, эта проверка не должна срабатывать).
    confirmed_same_brand = _brands_match(a, b)
    if (not confirmed_same_brand and a.brand_like_words and b.brand_like_words
            and not _brand_like_words_match(a.brand_like_words, b.brand_like_words)):
        return {
            "decision": "no",
            "reason": f"вероятно разные бренды: {sorted(a.brand_like_words)} ≠ {sorted(b.brand_like_words)}",
        }

    # Порядок проверки (владелец, уточнение 2): цвет → вес → страна →
    # остальные характеристики JSON → свойства из названия.
    color_conflict = _name_property_conflict("цвет", a, b)
    if color_conflict:
        return {"decision": "no", "reason": color_conflict}

    mass_conflict = _mass_conflict(
        a.char_values, b.char_values,
        has_model_code=bool(a.model_code_tokens and b.model_code_tokens),
    )
    if mass_conflict:
        return {"decision": "no", "reason": mass_conflict}

    name_qty_conflict = _name_quantity_conflict(a.name_qty, b.name_qty)
    if name_qty_conflict:
        return {"decision": "no", "reason": name_qty_conflict}

    name_dims_conflict = _name_dimensions_conflict(a.name_dims, b.name_dims, a.name_qty, b.name_qty)
    if name_dims_conflict:
        return {"decision": "no", "reason": name_dims_conflict}

    country_conflict = _name_property_conflict("страна", a, b)
    if country_conflict:
        return {"decision": "no", "reason": country_conflict}

    other_char_conflict = _other_characteristics_diff(a.char_values, b.char_values)
    if other_char_conflict:
        return {"decision": "no", "reason": other_char_conflict}

    for group in _PROPERTY_CHECK_ORDER:
        conflict = _name_property_conflict(group, a, b)
        if conflict:
            return {"decision": "no", "reason": conflict}

    # Группы "указано у одного ⇒ check" (п.2) — "no" при противоречии
    # возвращаем немедленно (та же сила, что у проверок выше); "check"
    # придерживаем и отдаём ТОЛЬКО если ничего сильнее (ambiguity/overlap)
    # не нашлось — иначе одно "check" маскирует другое.
    one_sided = _one_sided_property_result(a, b)
    if one_sided and one_sided["decision"] == "no":
        return one_sided

    ambiguity_reason = _ambiguity_reason(a, b, peers_a, peers_b)
    if ambiguity_reason:
        return {"decision": "check", "reason": ambiguity_reason}

    # Совпавший вид товара ИЗ СЛОВАРЯ (п.4 доп. ревью Кувалда↔Бауцентр,
    # 27.10.2026) — сильнее общего overlap-порога: "Молот ... SKIL RH1792"
    # / "Отбойный молоток ... SKIL RH1792SE00" — бренд+индекс+вид совпали,
    # но слова вокруг (ударный/сетевой/SDS-Max/отбойный) не overlap'ятся —
    # не повод уходить в check, раз словарный вид явно подтверждён с обеих
    # сторон (сюда доходим только когда a.product_type == b.product_type,
    # иначе вид-конфликт уже вернул "no" выше). ИСПРАВЛЕНО (владелец, доп.
    # ревью Delta/Security Force/BT, 27.10.2026, п.2 дефекта): обход порога
    # по виду товара допустим ТОЛЬКО если у ОБЕИХ сторон бренд совпал —
    # официально (manufacturer/словарь, confirmed_same_brand) ИЛИ через то
    # же латинское слово-кандидат ("SKIL"/"Hanskonner" встречается с обеих
    # сторон — тот же сигнал, что и у гейта "вероятно разные бренды" выше,
    # только здесь пересечение, а не его отсутствие). Иначе совпавший
    # родовой вид ("аккумулятор") при НЕИЗВЕСТНОМ/РАЗНОМ бренде больше не
    # обходит порог похожести слов (ровно так ложно сошлись Delta/Security
    # Force/BT — общие слова "аккумуляторная батарея" держали overlap выше
    # порога).
    brand_confirmed_match = confirmed_same_brand or _brand_like_words_match(a.brand_like_words, b.brand_like_words)
    if not (a.product_type and b.product_type and brand_confirmed_match):
        overlap = _overlap_coefficient(a.word_set, b.word_set)
        if overlap < NAME_OVERLAP_CHECK_THRESHOLD:
            return {
                "decision": "check",
                "reason": f"бренд и числа совпали, но названия слабо похожи (overlap={overlap:.2f})",
            }

    if one_sided:
        return one_sided

    return {"decision": "auto", "reason": "бренд, числа и свойства совпадают, противоречий нет"}


def _group_compatible(sig: ProductSignature, group: tuple) -> bool:
    """Все товары группы (один магазин, один ключ) совместимы друг с другом
    и не различаются ни одним свойством (п.5, rule 5) — иначе однозначности
    нет."""
    for i, item_a in enumerate(group):
        for item_b in group[i + 1:]:
            res = match(item_a, item_b)
            if res["decision"] != "auto":
                return False
            if item_a.product_type and item_b.product_type and item_a.product_type != item_b.product_type:
                return False
            for grp in ("цвет", "страна", "комплектация", "исполнение", "материал"):
                if item_a.name_props.get(grp) != item_b.name_props.get(grp):
                    return False
    return True


def _relevant_peers(sig: ProductSignature, peers: tuple) -> tuple:
    """Оставляет среди peers своего магазина только те карточки, которые
    относятся к тому же бренду (или не имеют распознанного бренда). Карточка
    другого явно указанного бренда в том же магазине (например, ОП-2 Меланти
    рядом с ОП-2 Ярпожинвест) — это товар другого производителя, а не
    вторая неоднозначная карточка того же бренда."""
    if not sig.brand_fold:
        return peers
    return tuple(p for p in peers if not p.brand_fold or _brands_match(sig, p))


def _ambiguity_reason(a: ProductSignature, b: ProductSignature,
                       peers_a: tuple, peers_b: tuple) -> Optional[str]:
    group_a = (a, *_relevant_peers(a, peers_a))
    group_b = (b, *_relevant_peers(b, peers_b))
    if len(group_a) > 1 and not _group_compatible(a, group_a):
        return (f"в магазине A под этим брендом+числами {len(group_a)} разных товара, "
                f"не сведённых в один (различаются свойствами)")
    if len(group_b) > 1 and not _group_compatible(b, group_b):
        return (f"в магазине B под этим брендом+числами {len(group_b)} разных товара, "
                f"не сведённых в один (различаются свойствами)")
    return None
