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

from app.services.brand_code_fold import fold_brand_or_code
from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer
from app.services.product_tz_44fz_rules import STOP_BRAND_WORDS
from app.services.product_name_signature_props import (
    COLOR_WORDS, COUNTRY_WORDS, EXECUTION_PHRASES, EXECUTION_WORDS,
    FIRE_CLASS_RE, MATERIAL_WORDS, PACKAGING_PHRASES,
    PRODUCT_TYPE_PHRASES, PRODUCT_TYPE_WORDS, UNIT_WORDS,
    _PACKAGING_SET_RE,
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


_UNIT_SUFFIX_RE = re.compile(r"^(\d+)([a-zа-яё]{1,2})$")

# Число(-а) с единицей измерения в самом названии ("18 В", "1х5,0 Ач",
# "2,0 Дж", "950 Вт") — владелец, 27.10.2026 (ревью auto-пар kuvalda ↔
# baucenter_tools_hardware: у Бауцентра в названии часто дописаны такие
# числа, которых нет у Кувалды — "18 В 1х5,0 Ач 2,0 Дж" — и они ложно
# требовали точного совпадения как индекс модели, хотя это СВОЙСТВО
# (п.4), а не код). Лookbehind/lookahead — ТОЛЬКО не часть более длинного
# буквенно-цифрового кода (не вырезает "400" внутри слитного
# "д600*ш400*в400" — там прямо перед числом стоит буква без пробела, см.
# тест test_corrugated_box_different_dimensions_and_grade)."""
_UNIT_WORDS_ALT = "|".join(sorted((re.escape(u) for u in UNIT_WORDS), key=len, reverse=True))
_UNIT_QUANTITY_RE = re.compile(
    rf"(?<![0-9a-zA-Zа-яёА-ЯЁ])\d+(?:[.,]\d+)?(?:\s*[xXхХ]\s*\d+(?:[.,]\d+)?)*"
    rf"\s*(?:{_UNIT_WORDS_ALT})(?![0-9a-zA-Zа-яёА-ЯЁ])",
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


def _split_words(name: Optional[str]) -> list[str]:
    """Название → нормализованные слова (класс пожара вырезан, гомоглифы/
    регистр свёрнуты через fold_brand_or_code, пробелы схлопнуты, крайняя
    пунктуация у каждого слова срезана). Дефисы ВНУТРИ слова сохраняются на
    этом шаге — они срезаются только при вычислении digit_tokens (там код
    без дефисов)."""
    if not name:
        return []
    cleaned = _strip_unit_quantities(_strip_fire_class_spans(name))
    folded = fold_brand_or_code(cleaned)
    words = []
    for raw in folded.split():
        w = _EDGE_PUNCT_RE.sub("", raw)
        if w:
            words.append(w)
    return words


def _digit_tokens(words: list[str]) -> frozenset:
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
    а у другого её просто нет, и ровно тот же товар ложно не сводится."""
    out = set()
    for w in words:
        if _HAS_DIGIT_RE.search(w):
            norm = _KEEP_ALNUM_RE.sub("", w)
            if not norm:
                continue
            m = _UNIT_SUFFIX_RE.match(norm)
            if m and m.group(2) in UNIT_WORDS:
                continue
            out.add(norm)
    return frozenset(out)


def _word_set(words: list[str]) -> frozenset:
    return frozenset(w for w in words if not _HAS_DIGIT_RE.search(w) and w not in _STOPWORDS)


def _extract_product_type(name: Optional[str]) -> Optional[str]:
    """Вид товара — первое существительное названия (владелец, 27.10.2026,
    ревью auto-пар: "Шкаф для огнетушителя" ≠ "Пенал для огнетушителя" —
    один артикул производителя, разный вид изделия). Синонимы вида
    (ИБП/источник бесперебойного питания, МФУ/многофункциональное
    устройство, шуруповёрт-варианты, УШМ/болгарка) — см.
    product_name_signature_props.PRODUCT_TYPE_{PHRASES,WORDS}. Без записи в
    словаре вид = само первое слово (два разных обычных существительных —
    это и есть разные виды, второй словарь-угадайку не заводим)."""
    if not name:
        return None
    # Та же чистка, что и перед токенизацией индекса (см. _split_words) —
    # иначе слитное "ОУ-5-ВСЕ" и раздельное "ОУ-5 ВСЕ" дают РАЗНОЕ первое
    # слово только из-за формата написания класса пожара, а не потому что
    # это разный вид товара (регрессия на test_fire_class_fused_or_spaced_
    # still_matches, владелец, 27.10.2026).
    cleaned = _strip_unit_quantities(_strip_fire_class_spans(name))
    folded = fold_brand_or_code(cleaned)
    for phrase, canon in PRODUCT_TYPE_PHRASES.items():
        if re.match(rf"^{re.escape(phrase)}(?!\w)", folded):
            return canon
    m = re.match(r"[a-zа-яё0-9\-]+", folded)
    if not m:
        return None
    first = _EDGE_PUNCT_RE.sub("", m.group(0)).strip("-")
    if not first:
        return None
    return PRODUCT_TYPE_WORDS.get(first, first)


def _first_raw_word(name: str) -> Optional[str]:
    """Первое слово названия БЕЗ fold_brand_or_code — для сравнения "первое
    слово = бренд целиком" простым .lower() (см. build_signature)."""
    cleaned = _strip_unit_quantities(_strip_fire_class_spans(name or ""))
    m = re.match(r"\S+", cleaned.strip())
    if not m:
        return None
    return _EDGE_PUNCT_RE.sub("", m.group(0)).strip("-")


def _overlap_coefficient(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0 if (a or b) else 1.0
    inter = len(a & b)
    return inter / min(len(a), len(b))


# ---------------------------------------------------------------------------
# Свойства из названия (цвет/материал/страна/класс пожара/комплектация/
# исполнение) — группы и словари см. product_name_signature_props.py.
# ---------------------------------------------------------------------------

def _extract_name_properties(name: Optional[str]) -> dict:
    if not name:
        return {}
    props: dict = {}

    # Класс пожара — ТОЛЬКО по оригинальному тексту (регистр важен, см.
    # product_name_signature_props.FIRE_CLASS_RE): буквы класса пишутся
    # заглавными, строчные совпадения (обычные слова) не должны считаться.
    fire_classes = {m.group(1) for m in FIRE_CLASS_RE.finditer(name)}
    if fire_classes:
        props["класс пожара"] = fire_classes

    folded = fold_brand_or_code(name)
    words = [w for w in (_EDGE_PUNCT_RE.sub("", w) for w in folded.split()) if w]

    colors = {COLOR_WORDS[w] for w in words if w in COLOR_WORDS}
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

    packaging = set()
    for phrase, canon in PACKAGING_PHRASES.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            packaging.add(canon)
    m = _PACKAGING_SET_RE.search(folded)
    if m:
        packaging.add(f"набор {m.group(1)} шт")
    if packaging:
        props["комплектация"] = packaging

    return props


# ---------------------------------------------------------------------------
# Характеристики из JSON (characteristics: [{name, value, unit}, ...]) —
# масса (с переводом единиц) + "остальные" по совпавшему нормализованному
# имени. ОДНА функция извлечения (_characteristic_values), оба потребителя
# (вес-приоритет и общая проверка) читают из неё — ПРАВИЛО №6.
# ---------------------------------------------------------------------------

_MASS_TO_GRAMS = {"мг": 0.001, "г": 1.0, "кг": 1000.0, "т": 1_000_000.0}
_LENGTH_TO_MM = {"мм": 1.0, "см": 10.0, "дм": 100.0, "м": 1000.0, "км": 1_000_000.0}

_MASS_NAME_RE = re.compile(r"масс|вес")
_NUMERIC_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
# "(не более)", "(до)" и т.п. — уточнение способа измерения, не другая
# характеристика; срезается ПЕРЕД сравнением нормализованных имён.
_QUALIFIER_PAREN_RE = re.compile(r"\([^)]*\)")
_TRAILING_UNIT_RE = re.compile(r",\s*[a-zа-яё°²³/]+\.?$", re.IGNORECASE)

# Характеристики, не относящиеся к самому товару (логистика магазина,
# номера строки) — общая проверка их игнорирует, см. docstring
# from_store_nomenclature.py ("Магазин-источник"/"Артикул*" — то же решение).
_IGNORED_CHAR_NAME_SUBSTRINGS = ("магазин-источник", "артикул", "параметр ")


def _normalize_char_name(name: str) -> str:
    name = _QUALIFIER_PAREN_RE.sub("", name or "")
    name = _TRAILING_UNIT_RE.sub("", name)
    return fold_brand_or_code(name).strip()


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
        unit = ((c or {}).get("unit") or "").strip().lower()
        if not unit:
            # единица может быть внутри значения ("2 г", "5,8 кг")
            m = re.search(r"([a-zа-яё]+)\s*$", (value or "").strip().lower())
            if m:
                unit = m.group(1)
        number = _parse_number(value)
        if number is not None and unit in _MASS_TO_GRAMS:
            out[norm] = (raw_name, "mass", number * _MASS_TO_GRAMS[unit])
        elif number is not None and unit in _LENGTH_TO_MM:
            out[norm] = (raw_name, "length", number * _LENGTH_TO_MM[unit])
        else:
            text = fold_brand_or_code(str(value) if value is not None else "")
            out[norm] = (raw_name, "text", text)
    return out


def _mass_conflict(a_chars: dict, b_chars: dict) -> Optional[str]:
    a_mass = next(((k, v) for k, v in a_chars.items() if _MASS_NAME_RE.search(k) and v[1] == "mass"), None)
    b_mass = next(((k, v) for k, v in b_chars.items() if _MASS_NAME_RE.search(k) and v[1] == "mass"), None)
    if not a_mass or not b_mass:
        return None
    _, (a_disp, _, a_grams) = a_mass
    _, (b_disp, _, b_grams) = b_mass
    if abs(a_grams - b_grams) > 0.5:  # 0.5 г — защита от округления ввода
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
        if _MASS_NAME_RE.search(key):
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
    product_type: Optional[str] = None
    char_values: dict = field(default_factory=dict)
    raw_item: dict = field(default_factory=dict)


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
    elif brand_dictionary is not None:
        brand = brand_dictionary.find_in_name(name)

    # Бренд из одних цифр ("200") или стоп-слово (цвет/материал/страна/
    # общее слово по ошибке попавшее в manufacturer, "ОПС" и т.п. — тот же
    # STOP_BRAND_WORDS, что и у ТЗ 44-ФЗ, ПРАВИЛО №6, второй список не
    # заводим) — владелец, 27.10.2026: такой "бренд" считается НЕ
    # определённым (не participates в гейте сравнения брендов).
    if brand:
        key = _brand_compare_key(brand)
        if not key or key.isdigit() or key in _BRAND_STOPWORD_KEYS:
            brand = None

    words = _split_words(name)
    # Сравнение бренда — ВСЕГДА через _brand_compare_key (_fold + только
    # буквы/цифры): "MAKITA" = "Makita" = "makita", "Sturm!" = "Sturm",
    # "Tech-KREP" = "Techkrep" (владелец, 27.10.2026, найден дефект — см.
    # docstring _fold выше).
    brand_fold = _brand_compare_key(brand) if brand else ""

    product_type = _extract_product_type(name)
    # Если название начинается прямо с бренда ("Makita LXT DJR187Z" — без
    # родового слова типа "дрель"), первое "слово" — это бренд, а не вид
    # товара; вид в этом случае просто НЕ определён (не противоречие, п.4),
    # а не "вид=makita" — иначе короткое имя без родового слова ложно не
    # сводится с полным ("Сабельная пила ... Makita LXT DJR187Z"). Сравнение
    # через _brand_compare_key — та же нормализация, что у самого бренда.
    if product_type and brand and _brand_compare_key(_first_raw_word(name)) == brand_fold:
        product_type = None

    return ProductSignature(
        name=name,
        brand=brand,
        brand_fold=brand_fold,
        digit_tokens=_digit_tokens(words),
        word_set=_word_set(words),
        name_props=_extract_name_properties(name),
        product_type=product_type,
        char_values=_characteristic_values(item.get("characteristics") or []),
        raw_item=item,
    )


def digit_tokens_key(sig: ProductSignature) -> frozenset:
    """Ключ для эффективного поиска кандидатов (группировка по индексу/
    числам названия, не попарный перебор O(N×M) — см.
    backend/scripts/eval_name_signature.py)."""
    return sig.digit_tokens


_PROPERTY_CHECK_ORDER = ("класс пожара", "комплектация", "исполнение", "материал")


def _name_property_conflict(group: str, a: ProductSignature, b: ProductSignature) -> Optional[str]:
    va = a.name_props.get(group)
    vb = b.name_props.get(group)
    if va and vb and not (va & vb):
        return f"{group} {sorted(va)} ≠ {sorted(vb)}"
    return None


def match(a: ProductSignature, b: ProductSignature, peers_a: tuple = (), peers_b: tuple = ()) -> dict:
    """Решение «тот же товар» для двух строк РАЗНЫХ магазинов (п.6 —
    пары только между разными магазинами, этим занимается вызывающий код,
    здесь — только сама проверка). peers_a/peers_b — другие строки СВОЕГО
    магазина под тем же ключом (бренд+цифровые токены), для проверки
    однозначности (п.5)."""
    if a.brand_fold and b.brand_fold and a.brand_fold != b.brand_fold:
        return {"decision": "no", "reason": f"бренд «{a.brand}» ≠ «{b.brand}»"}

    if a.product_type and b.product_type and a.product_type != b.product_type:
        return {"decision": "no", "reason": f"вид товара {a.product_type} ≠ {b.product_type}"}

    if a.digit_tokens != b.digit_tokens:
        return {
            "decision": "no",
            "reason": f"числа/индекс в названии {sorted(a.digit_tokens)} ≠ {sorted(b.digit_tokens)}",
        }

    # Порядок проверки (владелец, уточнение 2): цвет → вес → страна →
    # остальные характеристики JSON → свойства из названия.
    color_conflict = _name_property_conflict("цвет", a, b)
    if color_conflict:
        return {"decision": "no", "reason": color_conflict}

    mass_conflict = _mass_conflict(a.char_values, b.char_values)
    if mass_conflict:
        return {"decision": "no", "reason": mass_conflict}

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

    ambiguity_reason = _ambiguity_reason(a, b, peers_a, peers_b)
    if ambiguity_reason:
        return {"decision": "check", "reason": ambiguity_reason}

    overlap = _overlap_coefficient(a.word_set, b.word_set)
    if overlap < NAME_OVERLAP_CHECK_THRESHOLD:
        return {
            "decision": "check",
            "reason": f"бренд и числа совпали, но названия слабо похожи (overlap={overlap:.2f})",
        }

    return {"decision": "auto", "reason": "бренд, числа и свойства совпадают, противоречий нет"}


def _group_compatible(sig: ProductSignature, group: tuple) -> bool:
    """Все товары группы (один магазин, один ключ) совместимы друг с другом
    и не различаются ни одним свойством (п.5, rule 5) — иначе однозначности
    нет."""
    for other in group:
        if other is sig:
            continue
        res = match(sig, other)
        if res["decision"] != "auto":
            return False
        if sig.product_type != other.product_type:
            return False
        # "не различаются ни одним свойством" — даже при decision=auto
        # (конфликтов нет) проверяем ТОЧНОЕ совпадение обнаруженных свойств,
        # а не только отсутствие противоречий.
        for grp in ("цвет", "страна", *_PROPERTY_CHECK_ORDER):
            if sig.name_props.get(grp) != other.name_props.get(grp):
                return False
    return True


def _ambiguity_reason(a: ProductSignature, b: ProductSignature,
                       peers_a: tuple, peers_b: tuple) -> Optional[str]:
    group_a = (a, *peers_a)
    group_b = (b, *peers_b)
    if len(group_a) > 1 and not _group_compatible(a, group_a):
        return (f"в магазине A под этим брендом+числами {len(group_a)} разных товара, "
                f"не сведённых в один (различаются свойствами)")
    if len(group_b) > 1 and not _group_compatible(b, group_b):
        return (f"в магазине B под этим брендом+числами {len(group_b)} разных товара, "
                f"не сведённых в один (различаются свойствами)")
    return None
