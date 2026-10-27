"""Ключ вида товара для автосведения карточек без артикула производителя
(владелец, 27.10.2026, пожарная безопасность — первый вид, остальные позже).

Когда у товара нет артикула производителя, сравнивать карточки разных
магазинов можно по набору признаков, своему для каждого вида товара ("ключ
вида товара"): совпали ВСЕ признаки ключа + бренд -> один товар
(автоматически, "уверенно"); совпали бренд+модель/код, а один из остальных
признаков ключа расходится или не извлёкся -> "проверить" (человек решает).

ЭТОТ файл — только общее: TypeKeyResult, разбор текста (_blob/_fold),
поиск бренда (_find_brand/FIRE_SAFETY_BRANDS), диспетчер по виду (type_key)
и сравнение ключей (keys_match/keys_conflict). Разбор КАЖДОГО вида товара —
в своём файле (ПРАВИЛО №5 — один файл не должен разрастаться на все 4 вида):
  - product_type_keys_ognetushitel.py — огнетушитель
  - product_type_keys_znak.py — знак безопасности
  - product_type_keys_rukav.py — пожарный рукав
  - product_type_keys_shkaf.py — пожарный шкаф
Новый вид товара — новый такой файл + одна строка в _KIND_HANDLERS внизу
этого модуля, остальное не трогаем.

Текст для разбора — ТОЛЬКО name + characteristics (name/value) +
category_path, в нижнем регистре, гомоглифы латиница/кириллица и ё/Ё->е
схлопнуты через app.services.brand_code_fold.fold_brand_or_code (ПРАВИЛО
№6 — своей таблицы гомоглифов тут не завожено); цифры fold_brand_or_code НЕ
трогает (0/3/4 исключены из таблицы) — это важно: "ОП-2" не должен слиться с
"ОП-20" (владелец, см. докстринг brand_code_fold.py).

Вид товара определяется ПЕРВЫМ словом названия (после очистки ведущих
кавычек) — наблюдение на двух реальных выгрузках (k_spasatel, Магазин 01):
настоящие огнетушители/знаки/рукава/шкафы ВСЕГДА называются магазином,
начиная со слова своего вида ("Огнетушитель...", "Знак...", "Рукав...",
"Шкаф..."); сопутствующие товары (колесо для огнетушителя, комплект ЗПУ,
подставка для шкафа, стеллаж для рукавов) называются по-другому и этим же
правилом отсекаются, не требуя отдельного стоп-листа аксессуаров.

Бренд: если Product.manufacturer пуст или признан мусором
(app.services.catalog_gala.manufacturer_quality.is_bogus_manufacturer,
ПРАВИЛО №6 — вторую проверку "это не бренд" здесь не заводим), ищем бренд
пожарного рынка прямо в тексте (FIRE_SAFETY_BRANDS ниже) — в выгрузках
Спасателя и Магазина 01 это единственный способ узнать бренд огнетушителя/
рукава (manufacturer у обоих магазинов для этих позиций — null).

Бренд ОБЯЗАТЕЛЕН для автосведения огнетушителя/рукава/шкафа (без него максимум
"проверить" и то не всегда — см. type_key) — ТАК ХОЧЕТ владелец (иначе разные
производители одной модели ОП-4 слипнутся). У знака безопасности бренд —
ровно противоположно — НЕ требуется и никогда не блокирует: тот же код+размер+
материал от разных производителей — это один и тот же стандартный предмет
(ГОСТ 12.4.026), не два разных товара.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.brand_code_fold import fold_brand_or_code
from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer

# ---------------------------------------------------------------------------
# Бренды пожарного рынка (владелец, 27.10.2026, список-основа + дополнен по
# частотному разбору двух реальных выгрузок — k_spasatel_rescue_nomenclature.
# json и fire_equipment_nomenclature.json, см. отчёт eval_type_keys.py).
# Единственное место такого списка (ПРАВИЛО №6) — дополнять ТОЛЬКО здесь.
# Порядок значения не имеет: _find_brand ищет ВСЕ совпадения и берёт самое
# левое по позиции в тексте (при равенстве — самое длинное), не первое по
# списку.
FIRE_SAFETY_BRANDS = [
    # Список владельца, 27.10.2026.
    "Ярпожинвест", "Меланти", "Огнебор", "Огнеборец", "Пожтехника", "МИГ",
    "РИФ", "Инга", "Бонус-Вита", "Пульс", "HighProp", "Ингаз", "Зарница",
    "Пожхим", "Гефест", "Апогей", "Технорукав", "Пожтехкабель", "Сибирь",
    "ЯТЭК", "Каланча", "Пожарные системы",
    # Найдены частотным разбором названий огнетушителей в обоих файлах
    # (владелец просил дополнить по данным, 27.10.2026):
    "Пожнанотех", "Ратоборец", "Русинтэк", "Bontel", "ИНЕЙ", "НПО ПУЛЬС",
    # Бренды/заводы/серии пожарных рукавов, найдены в fire_equipment/
    # k_spasatel (Классик — серия рукавов РПК(В)/РПК(Д), а не завод-
    # изготовитель "Русарсенал", но у обоих магазинов это единственное общее
    # идентифицирующее слово в названии — используется как бренд-ключ):
    "Армтекс", "Берег", "ЗПО №3", "Edilgrappa", "Классик",
]
# Самое длинное совпадение первым внутри _find_brand не нужно сортировать
# здесь — сортировка по длине происходит в самой функции.


@dataclass
class TypeKeyResult:
    """Результат разбора карточки на ключ вида товара.
    kind — распознанный вид ("огнетушитель"/"знак"/"рукав"/"шкаф").
    key — полный набор признаков (включая бренд), None если хоть один
        ОБЯЗАТЕЛЬНЫЙ для вида признак не извлёкся.
    partial — "бренд+модель/код" (у знака — просто код, без бренда), для
        уровня "проверить"; None если и этого не хватает.
    missing — имена признаков, которые НЕ извлеклись (для отчёта человеку).
    extra — дополнительные "мягкие" признаки, которые НЕ входят в key, но
        РАСХОЖДЕНИЕ по ним (когда есть у обеих сторон) запрещает сведение
        даже при совпавшем key/partial — см. keys_conflict()."""
    kind: str
    key: Optional[tuple]
    partial: Optional[tuple]
    missing: list
    extra: dict = field(default_factory=dict)


def fold(text) -> str:
    """Folded текст (гомоглифы/регистр/пробелы схлопнуты, см. докстринг
    модуля) — используют все product_type_keys_*.py вместо своей свёртки."""
    return fold_brand_or_code(text)


def iter_characteristics(characteristics):
    """characteristics — список dict{name,value,...} ИЛИ объектов с атрибутами
    name/value (ORM) — оба варианта встречаются у вызывающего кода."""
    for c in characteristics or []:
        if isinstance(c, dict):
            yield c.get("name"), c.get("value")
        else:
            yield getattr(c, "name", None), getattr(c, "value", None)


def blob(name, characteristics, category_path) -> str:
    """Весь текст для разбора, folded (см. докстринг модуля) — name +
    характеристики (имя+значение) + category_path, ничего больше (НЕ
    description — там реклама магазина, слишком шумно для регулярок)."""
    parts = [name or ""]
    for key, value in iter_characteristics(characteristics):
        if key:
            parts.append(str(key))
        if value:
            parts.append(str(value))
    for part in category_path or []:
        if part:
            parts.append(str(part))
    return fold(" ".join(parts))


_LEADING_JUNK_RE = re.compile(r'^["\'«»\s]+')


def _leading_word(folded_name: str) -> str:
    """Первое слово folded-названия (кавычки/пробелы в начале отброшены) —
    определяет вид товара, см. докстринг модуля."""
    text = _LEADING_JUNK_RE.sub("", folded_name or "")
    match = re.match(r"[a-zа-я]+", text)
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------
# Общее ПРАВИЛО КОНФЛИКТА числового размерного признака — ДЛЯ ВСЕХ видов
# товара (владелец, 27.10.2026, правка после отчёта: «Огнетушитель ОУ-3
# (133)ВСЕ РИФ» и «ОУ-3-BCE (d-114) РИФ» совпали по ключу, но это разные
# баллоны — 133 мм и 114 мм). ЕДИНСТВЕННОЕ место этой проверки (ПРАВИЛО
# №6) — считается ОДИН раз в type_key() ниже, для любого вида, и кладётся в
# TypeKeyResult.extra (мягкий признак — см. keys_conflict): диаметр корпуса
# не указан у ОДНОЙ стороны — это НЕ конфликт, только расхождение У ОБЕИХ.
# Отдельные product_type_keys_*.py свою копию этой проверки не заводят.
_SIZE_DIAMETER_LABELED_RE = re.compile(r"(?:d[-=]\s*|ø\s*-?\s*|диаметр\D{0,6})(\d{2,4})")
# Голое число в скобках без подписи ("ОУ-3 (133)ВСЕ") — у Спасателя так
# записан диаметр корпуса огнетушителя без слова "диаметр"/"d-" (владелец,
# 27.10.2026). Используется ТОЛЬКО если лейбл выше не нашёлся — лейбл
# надёжнее голого числа.
_SIZE_DIAMETER_BARE_PAREN_RE = re.compile(r"\((\d{2,3})\)")
# Габариты ВхШхГ ("540х650х230", "200х200") — те же 2-4 цифры, что и у
# размера знака/шкафа, здесь считаются ОДИН раз для всех видов.
_SIZE_DIMENSIONS_RE = re.compile(r"(\d{2,4})\s*[xх×]\s*(\d{2,4})(?:\s*[xх×]\s*(\d{2,4}))?")
_SIZE_MASS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*кг\b")
_SIZE_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*л\b")
_SIZE_LENGTH_RE = re.compile(r"(\d{1,3})\s*(?:±\s*\d+\s*)?м\b")
# Огнетушащая способность "(2А, 55В, С, Е)" — тоже числовой размерный
# признак общего правила (раньше жил только в product_type_keys_
# ognetushitel.py — перенесён сюда, чтобы не дублировать механизм, см.
# ПРАВИЛО №6).
_SIZE_CAPABILITY_RE = re.compile(r"\(([\dа-я]+(?:\s*,\s*[\dа-я]+){1,5})\)")


def _soft_size_features(folded_blob: str) -> dict:
    """Числовые размерные признаки для общего правила конфликта (см. выше) —
    возвращает ТОЛЬКО то, что нашлось; отсутствующий признак просто не
    попадает в словарь (это и даёт "не конфликт, если не указан у одной из
    сторон" — keys_conflict сверяет только ключи, присутствующие у ОБЕИХ)."""
    features = {}

    match = _SIZE_DIAMETER_LABELED_RE.search(folded_blob)
    if not match:
        match = _SIZE_DIAMETER_BARE_PAREN_RE.search(folded_blob)
    if match:
        features["диаметр"] = match.group(1)

    match = _SIZE_DIMENSIONS_RE.search(folded_blob)
    if match:
        features["габариты"] = tuple(g for g in match.groups() if g)

    match = _SIZE_MASS_RE.search(folded_blob)
    if match:
        features["масса"] = match.group(1).replace(",", ".")

    match = _SIZE_VOLUME_RE.search(folded_blob)
    if match:
        features["объём"] = match.group(1).replace(",", ".")

    match = _SIZE_LENGTH_RE.search(folded_blob)
    if match:
        features["длина"] = match.group(1)

    match = _SIZE_CAPABILITY_RE.search(folded_blob)
    if match:
        features["огнетушащая способность"] = re.sub(r"\s+", "", match.group(1))

    return features


_BRAND_FOLD_CACHE = {brand: fold(brand) for brand in FIRE_SAFETY_BRANDS}


def find_brand(folded_blob: str, manufacturer, name) -> Optional[str]:
    """Бренд из Product.manufacturer, если он не мусор (см. докстринг
    модуля); иначе — поиск по FIRE_SAFETY_BRANDS в тексте (самое левое
    совпадение, при равенстве позиции — самое длинное имя бренда)."""
    if manufacturer and not is_bogus_manufacturer(manufacturer, name):
        return str(manufacturer).strip()
    best = None  # (position, -length, original_brand_name)
    for brand_name, folded_brand in _BRAND_FOLD_CACHE.items():
        pos = folded_blob.find(folded_brand)
        if pos < 0:
            continue
        candidate = (pos, -len(folded_brand), brand_name)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else None


# ---------------------------------------------------------------------------
# Диспетчер — по одной строке на вид товара (см. докстринг модуля наверху).
# Импорт внизу файла, не наверху: product_type_keys_*.py импортируют из
# ЭТОГО модуля (fold/blob/find_brand/TypeKeyResult), которые должны уже
# существовать к моменту их импорта.
# ---------------------------------------------------------------------------
from app.services.product_type_keys_ognetushitel import ognetushitel_key  # noqa: E402
from app.services.product_type_keys_znak import znak_key  # noqa: E402
from app.services.product_type_keys_rukav import rukav_key  # noqa: E402
from app.services.product_type_keys_shkaf import shkaf_key  # noqa: E402

_KIND_HANDLERS = (
    ("огнетуш", ognetushitel_key),
    ("знак", znak_key),
    ("рукав", rukav_key),
    ("шкаф", shkaf_key),
)


def type_key(name, characteristics=None, manufacturer=None, category_path=None) -> Optional[TypeKeyResult]:
    """Главная функция модуля. Возвращает TypeKeyResult для распознанного
    вида товара (огнетушитель/знак/рукав/шкаф) или None, если первое слово
    названия не относится ни к одному из них (см. докстринг модуля —
    почему именно первое слово)."""
    folded_name = fold(name)
    leading = _leading_word(folded_name)
    for stem, handler in _KIND_HANDLERS:
        if leading.startswith(stem):
            result = handler(name, characteristics, manufacturer, category_path)
            if result is not None:
                # Общее правило конфликта числового размера — ДЛЯ ВСЕХ
                # видов (см. _soft_size_features выше), не перезаписывает
                # мягкие признаки, которые вид уже сам положил в extra
                # (например, "бренд" у знака).
                for feat_name, value in _soft_size_features(blob(name, characteristics, category_path)).items():
                    result.extra.setdefault(feat_name, value)
            return result
    return None


def keys_conflict(a: TypeKeyResult, b: TypeKeyResult) -> bool:
    """True, если "мягкие" признаки (TypeKeyResult.extra) есть у ОБЕИХ
    сторон и расходятся — в этом случае сведение запрещено, даже если
    key/partial совпали (пример — огнетушащая способность у огнетушителя,
    или явно разные бренды у знака)."""
    for extra_name, value_a in (a.extra or {}).items():
        value_b = (b.extra or {}).get(extra_name)
        if value_b is not None and value_a != value_b:
            return True
    return False


def keys_match(a: Optional[TypeKeyResult], b: Optional[TypeKeyResult]) -> Optional[str]:
    """'уверенно' — совпал полный key; 'проверить' — совпал только partial
    (бренд+модель/код); None — разные виды, не распознано, или "мягкий"
    признак (keys_conflict) запрещает сведение. ЕДИНСТВЕННОЕ место этой
    логики (ПРАВИЛО №6) — eval_type_keys.py и будущий автосведение-код
    вызывают ТОЛЬКО эту функцию, вторую версию сравнения не заводят."""
    if a is None or b is None or a.kind != b.kind:
        return None
    if keys_conflict(a, b):
        return None
    if a.key is not None and b.key is not None and a.key == b.key:
        return "уверенно"
    if a.partial is not None and b.partial is not None and a.partial == b.partial:
        return "проверить"
    return None


# Имена полей key-тuple'а по виду, ТОЛЬКО для человекочитаемых отчётов
# (product_similar.py «проверить»-diff, владелец, 27.10.2026) — порядок
# ДОЛЖЕН совпадать с порядком, в котором соответствующий product_type_keys_
# *.py собирает свой key tuple; НЕ участвует в сравнении ключей (то — только
# keys_match/keys_match_unique выше, ПРАВИЛО №6).
KIND_KEY_FIELDS = {
    "огнетушитель": (
        "бренд", "модель", "класс пожара", "материал ЗПУ", "страна ЗПУ",
        "исполнение", "закачной", "тип баллона", "разобран/в сборе",
    ),
    "знак": ("код знака", "размер", "материал"),
    "рукав": ("бренд", "диаметр", "длина", "тип", "головки", "ствол"),
    "шкаф": ("бренд", "модель", "способ установки", "дверца", "цвет"),
}


def diff_reason(a: TypeKeyResult, b: TypeKeyResult) -> str:
    """Человекочитаемая причина, почему ДВА результата ОДНОГО kind не
    совпадают полным ключом (владелец, 27.10.2026, для группы «проверить» в
    product_similar.py) — конкретное поле ключа разошлось, мягкий признак
    (extra) конфликтует, или что-то не извлеклось. ЕДИНСТВЕННОЕ место этого
    текста (ПРАВИЛО №6) — вторую формулировку причины не заводить."""
    if a.kind != b.kind:
        return "разные виды товара"
    if keys_conflict(a, b):
        for extra_name, value_a in (a.extra or {}).items():
            value_b = (b.extra or {}).get(extra_name)
            if value_b is not None and value_a != value_b:
                return f"{extra_name} {value_a} ≠ {value_b}"
    fields = KIND_KEY_FIELDS.get(a.kind, ())
    if a.key is not None and b.key is not None:
        for field_name, value_a, value_b in zip(fields, a.key, b.key):
            if value_a != value_b:
                return f"{field_name}: {value_a!r} ≠ {value_b!r}"
    missing = sorted(set(a.missing) | set(b.missing))
    if missing:
        return "не извлеклось: " + ", ".join(missing)
    return "расходится состав ключа"


def keys_match_unique(
    a: Optional[TypeKeyResult],
    b: Optional[TypeKeyResult],
    peers_a,
    peers_b,
) -> Optional[str]:
    """Как keys_match(), но «уверенно» разрешено ТОЛЬКО когда пара 1-к-1:
    у a.key РОВНО ОДИН носитель среди peers_a (все TypeKeyResult карточек
    СВОЕГО магазина, включая саму a — любых видов, функция сама отфильтрует
    по kind+key), и то же для b.key среди peers_b. Иначе — понижение до
    "проверить" (владелец, 27.10.2026, правка после обзора 40 пар: 2-3
    карточки одного магазина под одним ключом не могут автоматически
    слиться с одной карточкой другого магазина — неоднозначно, нужен
    человек, даже если ключ совпал побуквенно).

    ЕДИНСТВЕННОЕ место проверки однозначности (ПРАВИЛО №6) — и
    eval_type_keys.py, и будущая загрузка каталога (при сверке кандидата
    с уже загруженными карточками — «своих» и карточками ДРУГОГО магазина)
    обязаны звать ИМЕННО эту функцию, не считать повторов самостоятельно."""
    verdict = keys_match(a, b)
    if verdict != "уверенно":
        return verdict
    count_a = sum(1 for r in peers_a if r is not None and r.kind == a.kind and r.key == a.key)
    count_b = sum(1 for r in peers_b if r is not None and r.kind == b.kind and r.key == b.key)
    if count_a > 1 or count_b > 1:
        return "проверить"
    return "уверенно"
