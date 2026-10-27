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
    CARRY_CASE_PHRASES, CHARGER_PHRASES, COATING_PHRASES, COATING_WORDS,
    COLOR_WORDS, COUNTRY_WORDS, EXECUTION_PHRASES, EXECUTION_WORDS,
    EXTRA_PACKAGING_PHRASES, FIRE_CLASS_RE, HOSE_TYPE_WORDS,
    INSTALL_MODE_WORDS, MATERIAL_WORDS, PACKAGING_PHRASES,
    PRODUCT_TYPE_PHRASES, PRODUCT_TYPE_WORDS, SHUTOFF_WORDS,
    SIDEDNESS_WORDS, UNIT_WORDS,
    _BATTERY_CAPACITY_RE, _BATTERY_COUNT_RE, _PACKAGING_SET_RE,
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
    sorted((fold_brand_or_code(s) for s in _MARKET_SUFFIXES), key=len, reverse=True)
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
    total = len(words)
    for i, w in enumerate(words):
        if _HAS_DIGIT_RE.search(w):
            if _is_store_tail_code(w, i, total):
                continue
            norm = _KEEP_ALNUM_RE.sub("", w)
            if not norm:
                continue
            m = _UNIT_SUFFIX_RE.match(norm)
            if m and m.group(2) in UNIT_WORDS:
                continue
            norm = _strip_known_market_suffix(norm)
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
                    out.add(f"{norm}·{nxt}")
    return frozenset(out)


def _word_set(words: list[str]) -> frozenset:
    return frozenset(w for w in words if not _HAS_DIGIT_RE.search(w) and w not in _STOPWORDS)


_PRODUCT_TYPE_WINDOW = 5


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
    заводим)."""
    if not name:
        return None
    # Та же чистка, что и перед токенизацией индекса (см. _split_words) —
    # иначе слитное "ОУ-5-ВСЕ" и раздельное "ОУ-5 ВСЕ" дают РАЗНЫЕ слова
    # только из-за формата написания класса пожара, а не потому что это
    # разный вид товара (регрессия на test_fire_class_fused_or_spaced_
    # still_matches, владелец, 27.10.2026).
    cleaned = _strip_unit_quantities(_strip_fire_class_spans(name))
    folded = fold_brand_or_code(cleaned)
    words = [w for w in (_EDGE_PUNCT_RE.sub("", w) for w in folded.split()) if w]
    window = words[:_PRODUCT_TYPE_WINDOW]
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
    folded = fold_brand_or_code(name)
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


def _build_name_quantity_unit_re(unit_table: dict) -> re.Pattern:
    # Та же сборка, но с ЗАХВАТОМ самой единицы (группа 2) — нужна, чтобы
    # узнать, КАКАЯ единица сработала, и перевести по таблице.
    alt = "|".join(sorted((re.escape(u) for u in unit_table), key=len, reverse=True))
    return re.compile(
        rf"(?<![0-9a-zA-Zа-яёА-ЯЁ])(\d+(?:[.,]\d+)?)\s*({alt})"
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
        if not any(abs(av - bv) <= max(tol(av), tol(bv)) for av in a_vals for bv in b_vals):
            return f"{group} в названии {sorted(a_vals)} ≠ {sorted(b_vals)}"
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

    # Вид товара — теперь по словарю PRODUCT_TYPE_WORDS/PHRASES, найденному
    # среди первых 5 слов (см. docstring _extract_product_type) — брендовое
    # слово само по себе в словарь не входит (это не родовое существительное),
    # поэтому отдельно "вид = бренд" больше не нужно отсекать, как было со
    # старым правилом "вид = первое слово" (владелец, 27.10.2026, доп.
    # ревью Кувалда↔Бауцентр): "Makita LXT DJR187Z" просто не находит вид
    # ни в одном слове — не противоречие (п.4).
    product_type = _extract_product_type(name)

    return ProductSignature(
        name=name,
        brand=brand,
        brand_fold=brand_fold,
        digit_tokens=_digit_tokens(words),
        word_set=_word_set(words),
        name_props=_extract_name_properties(name),
        check_props=_extract_check_properties(name),
        product_type=product_type,
        char_values=_characteristic_values(item.get("characteristics") or []),
        name_qty=_extract_name_quantities(name),
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


_ONE_SIDED_CHECK_GROUP_ORDER = (
    "сторонность", "перекрывной", "тип рукава", "комплектация(доп)",
    "покрытие", "зарядное устройство", "упаковка", "установка",
)


def _one_sided_property_result(a: ProductSignature, b: ProductSignature) -> Optional[dict]:
    """Группы из п.2 (владелец, ревью 113 авто-пар, 27.10.2026): указано у
    ОБОИХ и множества не пересекаются → "no" (разные товары, та же логика,
    что у _name_property_conflict); указано ТОЛЬКО у одного → "check" (не
    противоречие, но и не "совсем не важно" — решает человек). Проверяем
    ВСЕ группы (не выходим по первому "check"), чтобы "no" из группы,
    проверенной позже, не потерялось за более ранним "check"."""
    check_reason = None
    for group in _ONE_SIDED_CHECK_GROUP_ORDER:
        va = a.check_props.get(group)
        vb = b.check_props.get(group)
        if va and vb:
            if not (va & vb):
                return {"decision": "no", "reason": f"{group} {sorted(va)} ≠ {sorted(vb)}"}
        elif va or vb:
            if check_reason is None:
                only = va or vb
                check_reason = f"{group} указан(о) только у одного: {sorted(only)}"
    if check_reason:
        return {"decision": "check", "reason": check_reason}
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

    name_qty_conflict = _name_quantity_conflict(a.name_qty, b.name_qty)
    if name_qty_conflict:
        return {"decision": "no", "reason": name_qty_conflict}

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
    # иначе вид-конфликт уже вернул "no" выше).
    if not (a.product_type and b.product_type):
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
