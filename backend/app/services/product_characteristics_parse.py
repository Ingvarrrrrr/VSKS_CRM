"""Разбор текста, вставленного пользователем из карточки товара на сайте
поставщика, в список характеристик [{"name","value","unit"}] (владелец,
задача «заполнить характеристики копированием с сайта», 26.10.2026).

Доп. формат «Метка - значение» (дефис/тире, 27.10.2026, задача «нет данных —
заполняются из описания», товар 3002 с прода): добавлен ТОЛЬКО этот модуль
(ПРАВИЛО №6) — fallback из description в генераторе ТЗ 44-ФЗ
(app/services/product_tz_44fz_multiline.py) переиспользует _split_line
ОТСЮДА построчно, второго места с таким же разбором нет.

ЕДИНСТВЕННОЕ место этого разбора (ПРАВИЛО №6) — вызывается из
app/routers/products_characteristics.py (POST /characteristics/parse),
второй такой парсер не писать.

Переиспользование app/services/product_tz_44fz_multiline.py: там есть
похожая по смыслу функция `_parse_description_fallback` (и её внутренности
`_parse_pairs`/`_is_valid_label`/`_FALLBACK_LINE_RE`), но ВСЕ они с
ведущим подчёркиванием — приватные символы модуля, предназначенные только
для внутреннего использования app/services/product_tz_44fz.py (единственный
импортёр, см. grep). Этот модуль сейчас активно правит соседняя сессия
(файл в списке «не трогать» в задании) — тянуть оттуда приватные имена
означало бы: (а) нарушить соглашение о приватности формальным импортом
"_private_name" из чужого модуля, (б) создать скрытую связь с файлом, который
прямо сейчас меняется параллельно. Их алгоритм к тому же настроен на другую
задачу — очистку ТЗ 44-ФЗ от брендов/допусков с эвристикой "похоже на
заголовок группы", а не на разбор ЧЕТЫРЁХ явных форматов вставки (двоеточие/
таб/точки-разделитель/чередование), которые нужны здесь. Поэтому формат
разбора реализован самостоятельно, независимым и более простым набором
регулярок (см. ниже) — дублирования алгоритма тз-44фз здесь нет.
"""
import re
from typing import Optional

MAX_TEXT_LENGTH = 50_000

_TAB_LINE_RE = re.compile(r"^(.+?)\t+(.+)$")
_COLON_LINE_RE = re.compile(r"^([^:\n]{1,200}):\s*(.+)$")
# "Метка - значение" / "Метка — значение" / "Метка – значение" — дефис/тире,
# ОКРУЖЁННЫЙ пробелами с обеих сторон (иначе это дефис внутри слова
# "литий-ионный" или диапазон "108-112" без пробелов — не разделитель).
# Метка короткая (<=60) и с заглавной буквы — защита от абзацев текста, где
# " - " может встретиться случайно как часть обычного предложения.
_DASH_LINE_RE = re.compile(r"^(.{1,60}?)\s+[-—–]\s+(\S.*)$")
# "Метка ..... значение" / "Метка    значение" — метка и значение разделены
# либо повтором точек (2+), либо пробегом из 2+ пробелов.
_DOTS_OR_SPACES_LINE_RE = re.compile(r"^(.{1,200}?)(?:\.{2,}|\s{2,})\s*(\S.*)$")


def _is_dash_label(label: str) -> bool:
    """Метка формата "Метка - значение" — короткая строка с заглавной
    буквы (не длинный абзац, где " - " случайное совпадение)."""
    s = (label or "").strip()
    return bool(s) and len(s) <= 60 and s[0].isupper()

# "2786 г" / "1.5 л" / "220 В" — число (точка/запятая как разделитель
# дробной части) + единица измерения через пробел.
_NUMBER_UNIT_RE = re.compile(
    r"^(-?\d+(?:[.,]\d+)?)\s+([^\d\s][^\n]*)$"
)

# Единый словарь коротких единиц измерения для колонки unit в характеристиках
# товара (Product.characteristics) и ТЗ 44-ФЗ (ПРАВИЛО №6).
_CANONICAL_UNIT_MAP: dict[str, str] = {
    # масса
    "кг": "кг", "килограмм": "кг", "килограмма": "кг", "килограммов": "кг",
    "г": "г", "гр": "г", "грамм": "г", "грамма": "г", "граммов": "г",
    "мг": "мг", "миллиграмм": "мг",
    "т": "т", "тонна": "т", "тонны": "т", "тонн": "т",
    "тонна; метрическая тонна (1000 кг)": "т",
    # длина
    "мм": "мм", "миллиметр": "мм", "миллиметра": "мм", "миллиметров": "мм",
    "см": "см", "сантиметр": "см", "сантиметра": "см", "сантиметров": "см",
    "дм": "дм", "дециметр": "дм",
    "м": "м", "метр": "м", "метра": "м", "метров": "м",
    "погонный метр": "пог. м", "пог. м": "пог. м", "п.м": "пог. м",
    "км": "км", "километр": "км", "километра": "км", "километров": "км",
    "километр; тысяча метров": "км",
    # площадь / объём
    "м2": "м²", "м²": "м²", "кв.м": "м²", "кв. м": "м²", "кв м": "м²",
    "м.кв": "м²", "квадратный метр": "м²", "см2": "см²", "см²": "см²",
    "м3": "м³", "м³": "м³", "куб.м": "м³", "куб. м": "м³", "куб м": "м³",
    "м.куб": "м³", "кубический метр": "м³", "см3": "см³", "см³": "см³",
    "л": "л", "литр": "л", "литра": "л", "литров": "л",
    "литр; кубический дециметр": "л",
    "мл": "мл", "миллилитр": "мл", "миллилитра": "мл", "миллилитров": "мл",
    "кубический сантиметр; миллилитр": "мл",
    # время
    "с": "с", "сек": "с", "секунд": "с", "секунда": "с", "секунды": "с",
    "мс": "мс", "миллисекунд": "мс",
    "мин": "мин", "минут": "мин", "минута": "мин", "минуты": "мин",
    "ч": "ч", "час": "ч", "часа": "ч", "часов": "ч",
    "сут": "сут", "сутки": "сут", "суток": "сут",
    "мес": "мес", "месяц": "мес", "месяца": "мес", "месяцев": "мес",
    "год": "лет", "года": "лет", "лет": "лет",
    # давление / температура / прочее
    "па": "Па", "кпа": "кПа", "мпа": "МПа", "бар": "бар", "атм": "атм",
    "°c": "°C", "°с": "°C", "ºc": "°C", "ºс": "°C", "град": "°C", "градусов": "°C",
    "в": "В", "вольт": "В", "кв": "кВ",
    "а": "А", "ампер": "А", "ма": "мА",
    "вт": "Вт", "ватт": "Вт", "квт": "кВт", "киловатт": "кВт",
    "ва": "ВА", "ква": "кВА",
    "ач": "А·ч", "а·ч": "А·ч", "а/ч": "А·ч", "мач": "мА·ч", "ма·ч": "мА·ч",
    "гц": "Гц", "герц": "Гц", "кгц": "кГц", "мгц": "МГц", "ггц": "ГГц",
    "дб": "дБ", "децибел": "дБ",
    "дж": "Дж", "джоуль": "Дж", "кдж": "кДж",
    "н": "Н", "ньютон": "Н", "кн": "кН", "нм": "Н·м", "н·м": "Н·м",
    "лм": "лм", "люмен": "лм", "лк": "лк",
    "об/мин": "об/мин", "уд/мин": "уд/мин", "л/мин": "л/мин", "л/с": "л/с", "м³/ч": "м³/ч", "м3/ч": "м³/ч",
    "шт": "шт", "штука": "шт", "штук": "шт", "штуки": "шт",
    "уп": "уп", "упак": "уп", "упаковка": "уп",
    "компл": "компл", "комплект": "компл",
    "%": "%",
}

_KNOWN_UNITS_SORTED = sorted(_CANONICAL_UNIT_MAP.keys(), key=len, reverse=True)
_KNOWN_UNITS_ALT = "|".join(re.escape(u) for u in _KNOWN_UNITS_SORTED)

# Квалификатор перед числом ("не более 3,2кг.", "не больше 20м2.", "от 6 секунд.", "до 20 м²")
_LEADING_QUALIFIER_RE = re.compile(
    r"^(?:не\s+более|не\s+больше|не\s+менее|не\s+меньше|не\s+ниже|не\s+выше|"
    r"от|до|около|приблизительно|примерно|более|менее|свыше|макс\.?|мин\.?|~|≤|≥|<|>)\s+",
    re.IGNORECASE,
)

# Температурный или числовой диапазон "от -40 до +50°С." / "-40...+50 °C" / "от 10 до 20 м"
_RANGE_WITH_UNIT_RE = re.compile(
    rf"^(?:от\s+)?([+-]?\d+(?:[.,]\d+)?)\s*(?:до|\.\.\.|…|[—–-])\s*([+-]?\d+(?:[.,]\d+)?)"
    rf"\s*({_KNOWN_UNITS_ALT})\.?$",
    re.IGNORECASE,
)

# Составные габариты с дробными или целыми числами ("31.5 x 11.5 x 11 см", "450х150х150 мм")
_COMPOSITE_DIM_UNIT_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?(?:\s*[xXхХ×*]\s*\d+(?:[.,]\d+)?)+)\s*(мм|см|дм|м)\.?$",
    re.IGNORECASE,
)

# Число со слитной или раздельной известной единицей и необязательной точкой в конце ("2кг.", "1,4МПа.", "6 секунд.")
_QUAL_NUM_KNOWN_UNIT_RE = re.compile(
    rf"^([+-]?\d+(?:[.,]\d+)?)\s*({_KNOWN_UNITS_ALT})\.?$",
    re.IGNORECASE,
)

# Квалификаторы в скобках внутри имени характеристики: "(не более)", "(до)", "(не менее)"
_NAME_PAREN_QUALIFIER_RE = re.compile(
    r"\s*\(\s*(?:не\s+более|не\s+больше|не\s+менее|не\s+меньше|до|от|макс\.?|мин\.?)\s*\)",
    re.IGNORECASE,
)
_NAME_COMMA_QUALIFIER_RE = re.compile(
    r"(?:,\s*|\s+)(?:не\s+более|не\s+больше|не\s+менее|не\s+меньше)\.?$",
    re.IGNORECASE,
)
# Единица измерения в конце имени через запятую или в скобках: ", м²", ", лет", "(кг)"
_NAME_TRAILING_UNIT_RE = re.compile(
    rf"(?:,\s*({_KNOWN_UNITS_ALT})\.?|\(\s*({_KNOWN_UNITS_ALT})\.?\s*\))\s*$",
    re.IGNORECASE,
)

# Разбор составных текстовых габаритов вида "высота-38см, диаметр-11см."
_COMPOUND_AXIS_PART_RE = re.compile(
    r"(высота|длина|ширина|глубина|диаметр|толщина)\s*[-—:]+\s*(\d+(?:[.,]\d+)?)\s*(мм|см|дм|м)\.?",
    re.IGNORECASE,
)

# Мусорные/служебные названия характеристик, которые не должны храниться в карточке товара
_JUNK_CHAR_NAMES_EXACT = frozenset({
    "магазин-источник", "категория каталога", "раздел", "подраздел",
    "#prop_title#", "prop_title", "-", "—", "?",
    "при активации режима пожаротушения",
    "сроки, заявленные производителем",
})
_JUNK_CHAR_NAME_PREFIXES = (
    "артикул ", "код товара", "код по прайс",
)
_STORE_INTERNAL_MODEL_RE = re.compile(r"^00-\d{5,}$")


def normalize_characteristic_unit(raw_unit: Optional[str]) -> Optional[str]:
    """Приводит написание единицы измерения характеристики к стандартному короткому виду."""
    if not raw_unit:
        return None
    u = str(raw_unit).strip().rstrip(".").strip()
    if not u:
        return None
    canon = _CANONICAL_UNIT_MAP.get(u.lower())
    return canon if canon is not None else u


def clean_characteristic_name(name: str, unit: Optional[str] = None) -> tuple[str, Optional[str]]:
    """Очищает имя характеристики от '(не более)', '(до)', ', м²', '(кг)' и
    извлекает единицу измерения из имени в колонку unit (если unit ещё не задан)."""
    s = (name or "").strip().rstrip(":").strip()
    extracted_unit = normalize_characteristic_unit(unit)
    if not s:
        return "", extracted_unit

    # 1. Снимаем единицу измерения в конце имени (", м²", ", лет", "(кг)")
    m_unit = _NAME_TRAILING_UNIT_RE.search(s)
    if m_unit:
        u_raw = m_unit.group(1) or m_unit.group(2)
        if not extracted_unit and u_raw:
            extracted_unit = normalize_characteristic_unit(u_raw)
        s = s[: m_unit.start()].strip().rstrip(",").strip()

    # 2. Снимаем "(не более)", "(не менее)", "(до)", "(от)" внутри или в конце имени
    s = _NAME_PAREN_QUALIFIER_RE.sub("", s).strip()
    s = _NAME_COMMA_QUALIFIER_RE.sub("", s).strip()

    # 3. Если после снятия квалификатора на конце осталась ещё одна единица (", кг")
    m_unit2 = _NAME_TRAILING_UNIT_RE.search(s)
    if m_unit2:
        u_raw = m_unit2.group(1) or m_unit2.group(2)
        if not extracted_unit and u_raw:
            extracted_unit = normalize_characteristic_unit(u_raw)
        s = s[: m_unit2.start()].strip().rstrip(",").strip()

    s = re.sub(r"\s{2,}", " ", s).strip().rstrip(",").strip()
    return s, extracted_unit


def _split_line(line: str) -> Optional[tuple]:
    """Пробует разбить ОДНУ строку на (метка, значение) одним из ЧЕТЫРЁХ
    форматов «в строке», в порядке однозначности: таб → двоеточие → дефис/
    тире (короткая метка с заглавной) → точки/пробелы-разделитель. Дефис
    проверяется ДО общего разделителя "2+ пробела", иначе "Метка  - значение"
    (два пробела перед дефисом) перехватывается менее точным правилом и
    отрезает дефис в значение. Возвращает None, если ни один не подошёл."""
    m = _TAB_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value:
            return label, value
    m = _COLON_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value:
            return label, value
    m = _DASH_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip(), m.group(2).strip()
        if label and value and _is_dash_label(label):
            return label, value
    m = _DOTS_OR_SPACES_LINE_RE.match(line)
    if m:
        label, value = m.group(1).strip().rstrip(".").strip(), m.group(2).strip()
        if label and value:
            return label, value
    return None


def _separate_unit(value: str) -> tuple:
    """"2786 г" → ("2786", "г"), "не больше 3,2кг." → ("3,2", "кг"),
    "от 6 секунд." → ("6", "с"), "31.5 x 11.5 x 11 см" → ("31.5x11.5x11", "см"),
    "от -40 до +50°С." → ("-40...+50", "°C"). Если значение не «число + единица» —
    возвращает (value, None) без изменений."""
    v = (value or "").strip()
    if not v:
        return value, None

    # 1. Диапазон с единицей ("от -40 до +50°С.", "от 10 до 20 м")
    m_range = _RANGE_WITH_UNIT_RE.match(v)
    if m_range:
        a, b, u_raw = m_range.group(1), m_range.group(2), m_range.group(3)
        unit_canon = normalize_characteristic_unit(u_raw)
        sep = "..." if (unit_canon == "°C" or a.startswith(("+", "-")) or b.startswith(("+", "-"))) else "-"
        return f"{a}{sep}{b}", unit_canon

    # 2. Составные габариты ("31.5 x 11.5 x 11 см")
    m_comp = _COMPOSITE_DIM_UNIT_RE.match(v)
    if m_comp:
        dims_clean = re.sub(r"\s*[xXхХ×*]\s*", "x", m_comp.group(1).strip())
        return dims_clean, normalize_characteristic_unit(m_comp.group(2))

    # 3. Снятие ведущего квалификатора ("от ", "до ", "не более ", "не больше ", "не менее ")
    m_qual = _LEADING_QUALIFIER_RE.match(v)
    candidate = v[m_qual.end():].strip() if m_qual else v

    # Число со слитной или раздельной известной единицей ("2кг.", "3,2кг.", "6 секунд.", "1,4МПа.")
    m_known = _QUAL_NUM_KNOWN_UNIT_RE.match(candidate)
    if m_known:
        return m_known.group(1).strip(), normalize_characteristic_unit(m_known.group(2))

    if m_qual and re.match(r"^[+-]?\d+(?:[.,]\d+)?\.?$", candidate):
        return candidate.rstrip("."), None

    # 4. Общий шаблон "<число> <короткая единица>"
    m = _NUMBER_UNIT_RE.match(candidate.rstrip("."))
    if not m:
        if re.match(r"^-?\d+(?:[.,]\d+)?\.$", v):
            return v[:-1], None
        return value, None
    number, rest = m.group(1).strip(), m.group(2).strip()
    if re.search(r"[x×()]", rest, re.IGNORECASE):
        return value, None
    if " " in rest or len(rest) > 20:
        return value, None
    return number, normalize_characteristic_unit(rest)


def clean_characteristics_list(items: Optional[list]) -> list[dict]:
    """ЕДИНАЯ функция очистки списка характеристик карточки товара (ПРАВИЛО №6):
      - выносит единицы и убирает '(не более)'/'(до)' из name;
      - очищает value от квалификаторов ('от', 'не более', 'не больше') и точек,
        выделяя единицу измерения строго в колонку unit;
      - разбивает составные строки вида 'высота-38см, диаметр-11см.' на отдельные
        строки характеристик;
      - приводит единицы измерения к стандартным коротким обозначениям ('кг', 'г', 'с', 'м²');
      - отбрасывает служебный мусор ('Магазин-источник', 'Артикул Сима-ленд', 'Раздел' и т.д.)."""
    if not items:
        return []

    expanded: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        raw_name = str(raw.get("name") or "").strip()
        raw_val = str(raw.get("value") or "").strip()
        raw_unit = raw.get("unit")
        in_desc = raw.get("in_description")
        if not raw_name or not raw_val:
            continue

        # Разбивка составных габаритов вида "высота-38см, диаметр-11см."
        if re.search(r"габарит|размер", raw_name, re.IGNORECASE):
            axis_matches = list(_COMPOUND_AXIS_PART_RE.finditer(raw_val))
            if axis_matches:
                for am in axis_matches:
                    axis_title = am.group(1).strip().capitalize()
                    axis_val = am.group(2).strip()
                    axis_unit = normalize_characteristic_unit(am.group(3))
                    expanded.append({
                        "name": axis_title,
                        "value": axis_val,
                        "unit": axis_unit,
                        "in_description": in_desc,
                    })
                continue

        expanded.append(raw)

    out: list[dict] = []
    seen_keys: set[str] = set()
    for item in expanded:
        raw_name = str(item.get("name") or "").strip()
        raw_val = str(item.get("value") or "").strip()
        raw_unit = str(item.get("unit") or "").strip() or None
        if not raw_name or not raw_val:
            continue

        name, unit = clean_characteristic_name(raw_name, raw_unit)
        if not name:
            continue
        low_name = name.lower()
        if low_name in _JUNK_CHAR_NAMES_EXACT or any(low_name.startswith(p) for p in _JUNK_CHAR_NAME_PREFIXES):
            continue
        if low_name == "модель производителя" and _STORE_INTERNAL_MODEL_RE.match(raw_val):
            continue
        if raw_val.lower() in ("#prop_value#", "prop_value", "&nbsp;", "-", "—"):
            continue

        val_part, unit_part = _separate_unit(raw_val)
        value = str(val_part or "").strip()
        if unit_part and not unit:
            unit = unit_part
        elif unit:
            unit = normalize_characteristic_unit(unit)

        # Убираем хвостовую точку у коротких текстовых значений (например "мобильный (переносной), закачный.")
        if not unit and value.endswith(".") and not value.endswith(".."):
            value = value[:-1].strip()

        if not value:
            continue

        dedup_key = low_name
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        entry: dict = {"name": name, "value": value, "unit": unit}
        if "in_description" in item:
            entry["in_description"] = item.get("in_description")
        out.append(entry)

    return out


def parse_pasted_characteristics(text: str) -> list:
    """Разбирает вставленный текст в список характеристик. Пустой/пробельный
    текст → []. Поддерживает «Метка: значение», «Метка\\tзначение», «Метка -
    значение» (дефис/тире), «Метка ..... значение» (построчно) и, если
    построчный разбор не дал результата хотя бы на половине строк,
    чередующиеся строки метка/значение."""
    if not text or not text.strip():
        return []

    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not raw_lines:
        return []

    pairs: list = []
    unresolved = 0
    for line in raw_lines:
        parsed = _split_line(line)
        if parsed:
            pairs.append(parsed)
        else:
            unresolved += 1

    # Построчный разбор не справился (меньше половины строк дали пару) —
    # пробуем чередующиеся строки метка/значение (нечётные/чётные).
    if not pairs or unresolved > len(raw_lines) / 2:
        if len(raw_lines) >= 2 and len(raw_lines) % 2 == 0:
            alt_pairs = []
            ok = True
            for i in range(0, len(raw_lines), 2):
                label, value = raw_lines[i].strip(), raw_lines[i + 1].strip()
                if not label or not value:
                    ok = False
                    break
                alt_pairs.append((label, value))
            if ok and alt_pairs:
                pairs = alt_pairs

    items = []
    seen = set()
    for label, value in pairs:
        label = label.strip()
        value = value.strip()
        if not label or not value:
            continue
        name_clean, unit_from_name = clean_characteristic_name(label)
        if not name_clean:
            continue
        key = (name_clean.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        value_part, unit_part = _separate_unit(value)
        items.append({
            "name": name_clean,
            "value": value_part,
            "unit": unit_part or unit_from_name,
        })
    return items
