"""Ключ вида товара — огнетушитель (владелец, 27.10.2026). Разбор ТОЛЬКО
этого вида — общие helpers (fold/blob/find_brand/TypeKeyResult) живут в
app.services.product_type_keys, см. докстринг там (ПРАВИЛО №5 — один файл
на вид товара)."""
import re
from typing import Optional

from app.services.product_type_keys import TypeKeyResult, blob as _blob, fold as _fold, find_brand as _find_brand

# "о" + (вп|вэ|п|у) + опциональный дефис + цифры модели. Порядок альтернатив
# важен: "вп"/"вэ" ДО одиночных "п"/"у", иначе "овп-4" разбёрется как "о"+"в"
# (не входит в список) — нет, это не страшно само по себе, но порядок всё
# равно важен, чтобы "овп" не спутался с "оп" из-за альтернации (regex
# alternation берёт первый подходящий вариант по порядку).
_MODEL_RE = re.compile(r"\bо(вп|вэ|п|у)-?(\d+)\b")

# Класс пожара — после fold латиница ABCE уже кириллица (A->а, B->в, C->с,
# E->е, см. brand_code_fold._HOMOGLYPH_MAP) — значит "ABCE" и "АВСЕ" после
# fold неразличимы, сравниваются как одна строка "авсе". Токен — 2-4 РАЗНЫЕ
# буквы из набора а/в/с/е (без повторов — реальные коды классов букву не
# повторяют). Ищем ТОЛЬКО в окне сразу после модели (не по всему блобу) —
# иначе слово "все" (обычное русское "всё") из описания/характеристики
# ложно сработает.
_FIRE_CLASS_RE = re.compile(r"\b([авсе]{2,4})\b")


def _fire_class_in_window(window: str) -> Optional[str]:
    for match in _FIRE_CLASS_RE.finditer(window):
        token = match.group(1)
        if len(set(token)) == len(token):  # без повторов буквы
            return token
    return None


# ЗПУ — запорно-пусковое устройство: материал/страна упоминаются рядом со
# словом "зпу" (ищем окно в 20 символов после "зпу", не по всему блобу —
# иначе "металл"/"латунь" из описания корпуса огнетушителя (не ЗПУ) ложно
# попадёт в признак ЗПУ).
_ZPU_WINDOW_RE = re.compile(r"зпу(.{0,20})")
_ZPU_MATERIAL_WORDS = ("латунь", "металл", "пластик")
_ZPU_COUNTRY_WORDS = ("китай", "росси")  # "росси" покрывает россия/российский

# Признаки закачного огнетушителя — "(з)" сразу после модели, ИЛИ опечатка
# магазина "(3)" (Сима-ленд; владелец, 27.10.2026: "3" тут не цифра, а
# кириллическая "з" с опечаткой), ИЛИ слово "закачн*". Ищутся В ОКНЕ сразу
# после модели (та же причина, что у класса пожара).
_ZAKACHNY_SUFFIX_RE = re.compile(r"^\(\s*[зЗ3]\s*\)")

_EXEC_FLAGS = {
    "передвижной": ("передвижн",),
    "хромированный": ("хромированн",),
    "нержавеющая сталь": ("нержавеющ", "нержавейк"),
    "чёрный": ("черн",),
    "интерьерный": ("интерьерн",),
    "разборный": ("разборн",),
    "в сборе": ("в сборе", "всборе"),
    "одобрение МРС": ("мрс",),
}


def _exec_flags(text: str) -> tuple:
    flags = []
    for label, stems in _EXEC_FLAGS.items():
        if any(stem in text for stem in stems):
            flags.append(label)
    return tuple(sorted(flags))


# Тип баллона/трубы — "бесшовная труба" / "эл./сварная труба" (владелец,
# 27.10.2026, правка после обзора 40 пар: ОУ-3 d=133 бесшовная и d=133/114
# сварная — РАЗНЫЕ товары, не варианты одного). Опциональный признак (как
# ЗПУ выше) — не указан ни у кого — не мешает; указан у одной стороны и не
# у другой — ключ разойдётся, уйдёт на "проверить" (не блокируется
# совсем — у решает человек).
_CYLINDER_TYPE_WORDS = (("бесшовная", "бесшовн"), ("сварная", "сварн"))

# "разобран." — состояние баллона при перезарядке (НЕ то же самое, что ЗПУ
# "разборный"/"в сборе" из _EXEC_FLAGS выше — разный корень, разный смысл).
# Старое альтернативное обозначение в скобках вида "(ОУ-10)"/"(ОУ-80)" —
# НЕ признак (владелец, 27.10.2026) — тут не разбирается вовсе.
_DISASSEMBLED_RE = re.compile(r"разобран")


def _cylinder_type(text: str) -> Optional[str]:
    for label, stem in _CYLINDER_TYPE_WORDS:
        if stem in text:
            return label
    return None


def _cylinder_assembly(text: str) -> Optional[str]:
    return "разобран" if _DISASSEMBLED_RE.search(text) else None


def ognetushitel_key(name, characteristics, manufacturer, category_path) -> TypeKeyResult:
    text = _blob(name, characteristics, category_path)
    missing = []

    model_match = _MODEL_RE.search(text)
    model = None
    zakachny = False
    fire_class = None
    if model_match:
        model = "о" + model_match.group(1) + model_match.group(2)
        window = text[model_match.end():model_match.end() + 40]
        if _ZAKACHNY_SUFFIX_RE.match(window):
            zakachny = True
        if "закачн" in text:
            zakachny = True
        fire_class = _fire_class_in_window(window)
    else:
        missing.append("модель")

    if fire_class is None:
        missing.append("класс пожара")

    # ЗПУ (материал/страна) — признак ОПЦИОНАЛЬНЫЙ: большинство карточек его
    # вообще не упоминают. Отсутствие (None) на обеих сторонах — легитимное
    # совпадающее значение; "missing" только для отчёта человеку, key НЕ
    # блокирует. Если он указан у ОДНОЙ стороны и не указан у другой — key
    # не совпадёт (None != "латунь"), сработает откат на partial
    # ("проверить") — ровно то поведение, которого хочет владелец.
    zpu_material = None
    zpu_country = None
    zpu_match = _ZPU_WINDOW_RE.search(text)
    if zpu_match:
        window = zpu_match.group(1)
        zpu_material = next((w for w in _ZPU_MATERIAL_WORDS if w in window), None)
        zpu_country = next((w for w in _ZPU_COUNTRY_WORDS if w in window), None)
    if zpu_material is None:
        missing.append("материал ЗПУ")
    if zpu_country is None:
        missing.append("страна ЗПУ")

    exec_flags = _exec_flags(text)  # пустой tuple — легитимное значение, не "missing"

    cylinder_type = _cylinder_type(text)
    cylinder_assembly = _cylinder_assembly(text)
    if cylinder_type is None:
        missing.append("тип баллона/трубы")
    if cylinder_assembly is None:
        missing.append("разобран/в сборе")

    brand = _find_brand(text, manufacturer, name)
    if brand is None:
        missing.append("бренд")

    folded_brand = _fold(brand) if brand else None
    partial = (folded_brand, model) if (brand and model) else None
    key = None
    if brand and model and fire_class:
        key = (
            folded_brand, model, fire_class, zpu_material, zpu_country,
            exec_flags, zakachny, cylinder_type, cylinder_assembly,
        )

    # "Мягкие" числовые размерные признаки (диаметр/огнетушащая способность
    # и т.п.) — общее правило конфликта для ВСЕХ видов, считается ОДИН раз
    # в product_type_keys.type_key() и докладывается в extra ПОСЛЕ этого
    # вызова (ПРАВИЛО №6) — здесь своей копии не заводим.
    return TypeKeyResult(kind="огнетушитель", key=key, partial=partial, missing=missing, extra={})
