"""
Единый справочник допустимых значений для строковых enum-подобных полей ТС.

Источник: НЕ выдумка кода, а правила проверки данных (x14:dataValidation,
ссылки на лист «drop») листа «26.05.2026» файла владельца
`20260810_Голичкову актуализировать.xlsx` — проверено разбором
xl/worksheets/sheet1.xml (x14:dataValidation → xm:f drop!$X$n:$X$m) и живым
чтением листа «drop» через openpyxl. Наборы 1:1 совпадают со списком,
согласованным с владельцем, за вычетом двух технических нюансов исходника:
  - лист «drop», колонка A (кузов) содержит дубль строки "Микроавтобус"
    (строки 13 и 31) — схлопнут, ниже 49 уникальных значений, не 50 строк;
  - лист «drop», колонка Q (пропуска), значение "Нет" хранится с хвостовым
    пробелом ("Нет ") — здесь записано в нормализованном виде.

Единственный источник правды наборов допустимых значений. Используется:
  - app/routers/vehicles_import.py          — match_dictionary_value() при
    разборе присланного файла: не сопоставившееся значение в колонку НЕ
    пишется (см. вызывающий код — warnings + props.note);
  - app/services/vehicle_import_template.py — блокирующий DataValidation
    (showErrorMessage=True) + лист «Справочники» шаблона импорта;
  - app/routers/vehicle_fields.py            — "options" в ответе
    GET /api/vehicle-fields, единственный источник для выпадающих списков
    карточки ТС на фронте (frontend не хранит вторую копию списков).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# Явный вариант «нет данных, ответ осознанный» — добавлен ПОВЕРХ наборов
# владельца по его прямому распоряжению (2026-09), ни один из существующих
# вариантов ниже не переименован и не убран. При импорте (см.
# app/routers/vehicles_import.py) это значение трактуется как «ячейка не
# заполнена»: в колонку не пишется, предупреждение не поднимается.
NO_DATA_LABEL = "Нет данных"

# ─────────────────── Сортировка русских подписей по алфавиту ────────────────
#
# Владелец (2026-09): «Тип ТС» и «Кузов» шли вразнобой в выпадающих списках —
# отсортировать по алфавиту. Python не гарантирует корректный порядок кириллицы
# через встроенный sorted()/str.lower() на любой платформе (зависит от системной
# locale, которая на сервере/в контейнере не обязательно ru_RU), поэтому здесь —
# явная таблица позиций букв русского алфавита, а не str.casefold()+sorted().
# "Ё" стоит на своём словарном месте (сразу после "Е"), а не в конце (как было
# бы при сравнении по code point — U+0451 "ё" физически ЗА пределами блока А-Я).
_RU_ALPHABET = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
_RU_ORDER: Dict[str, int] = {ch: i for i, ch in enumerate(_RU_ALPHABET)}


def ru_sort_key(text: str):
    """Ключ сортировки для русских подписей выпадающих списков (регистро-
    независимо, с корректным местом «Ё»). Символы вне русского алфавита
    (цифры, скобки, пробелы, латиница) сортируются по code point ПОСЛЕ всех
    русских букв — этого достаточно для подписей вида "Лодка (мотор)"
    (короткий префикс "Лодка" сравнивается как меньший, стандартное поведение
    сравнения списков в Python)."""
    return [_RU_ORDER.get(ch.upper(), 1000 + ord(ch)) for ch in str(text)]


# ── Кузов по ПТС (drop!$A$2:$A$56, реально заполнено A2:A51) ────────────────
# Порядок ниже — как было в исходнике владельца (для истории/трассируемости
# набора значений к листу «drop»). Публичный BODY_TYPE_OPTIONS (см. ниже) —
# та же 49-ка, но по алфавиту, с NO_DATA_LABEL принудительно последним пунктом
# (владелец, 2026-09: «Тип ТС» и «Кузов» шли вразнобой — отсортировать; «Нет
# данных» — не равноправный вариант, а осознанный ответ «данных нет», ему
# место в конце списка, а не там, где его поставил бы алфавит).
_BODY_TYPE_OPTIONS_SOURCE_ORDER: List[str] = [
    "Седан", "Хэтчбек", "Универсал", "Лифтбек", "Купе", "Кабриолет", "Родстер",
    "Тарга", "Лимузин", "Минивэн", "Микроавтобус", "Фургон", "Пикап",
    "Бортовой", "Тентованный", "Рефрижератор", "Автовоз", "Эвакуатор",
    "Цистерна", "Самосвал", "Бетономешалка", "Мусоровоз", "Пожарный",
    "Скорая помощь", "Полицейский", "Инкассаторский", "Городской автобус",
    "Междугородний автобус", "Школьный автобус", "Троллейбус", "Трамвай",
    "Седельный тягач", "Шасси", "Изотермический", "Промтоварный",
    "Контейнеровоз", "Лесовоз", "Трубовоз", "Тяжеловоз", "Автокран",
    "Бурильная установка", "Погрузчик", "Мотоцикл", "Мопед", "Скутер",
    "Квадроцикл", "Багги", "Снегоход", "Гидроцикл",
]

BODY_TYPE_OPTIONS: List[str] = sorted(_BODY_TYPE_OPTIONS_SOURCE_ORDER, key=ru_sort_key) + [
    NO_DATA_LABEL,
]

# drop!$D$2:$D$9 (реально D2:D3) → AW «Авторезина»
TIRES_TYPE_OPTIONS: List[str] = ["Зимняя", "Летняя", NO_DATA_LABEL]

# drop!$H$2:$H$6 → AY «Состояние резины»
TIRES_CONDITION_OPTIONS: List[str] = ["Новая", "Хорошая", "Удовлетворительная", "Требует замены", NO_DATA_LABEL]

# drop!$N$2:$N$7 → BJ «Состояние лакокрасочного покрытия»
# Переименовано владельцем (2026-09): "Идеальное, есть сколы" → "Хорошее - есть сколы"
# (см. _VALUE_ALIASES ниже — старое написание распознаётся при импорте уже
# заполненных файлов и сопоставляется с новым каноническим вариантом).
PAINT_CONDITION_OPTIONS: List[str] = [
    "Идеальное", "Хорошее - есть сколы", "Среднее", "Требуется покраска", NO_DATA_LABEL,
]

# drop!$Q$2:$Q$6 → AM/AO/AQ/AS/AU «Пропуск ЗО/ХО/ДНР/ЛНР/Москва»
PASS_STATUS_OPTIONS: List[str] = ["Да", "Нет", "Не требуется", "Не выпускался", NO_DATA_LABEL]

# drop!$F$2:$F$8 (реально F2:F3) → AX + drop!$F$2:$F$3 → AC/AZ/BG/BK/BM/BO
YES_NO_OPTIONS: List[str] = ["Да", "Нет", NO_DATA_LABEL]

# field_key (имя атрибута Vehicle либо ключ внутри props) → допустимые значения.
FIELD_OPTIONS: Dict[str, List[str]] = {
    "tires_type": TIRES_TYPE_OPTIONS,                  # AW, props.tires_type
    "has_spare_tires": YES_NO_OPTIONS,                 # AX (bool-колонка)
    "tires_condition": TIRES_CONDITION_OPTIONS,        # AY — устаревшее общее поле (2026-09,
                                                        # см. tires_summer_condition/tires_winter_condition)
    "tires_summer_condition": TIRES_CONDITION_OPTIONS, # 2026-09: состояние летнего комплекта
    "tires_winter_condition": TIRES_CONDITION_OPTIONS, # 2026-09: состояние зимнего комплекта
    "paint_condition": PAINT_CONDITION_OPTIONS,        # BJ, props.paint_condition
    "pass_zo": PASS_STATUS_OPTIONS,                    # AM — устаревшая колонка, вне реестра/импорта
    "pass_ho": PASS_STATUS_OPTIONS,                    # AO — устаревшая колонка, вне реестра/импорта
    "pass_dnr": PASS_STATUS_OPTIONS,                   # AQ — устаревшая колонка, вне реестра/импорта
    "pass_lnr": PASS_STATUS_OPTIONS,                   # AS — устаревшая колонка, вне реестра/импорта
    "pass_moscow": PASS_STATUS_OPTIONS,                # AU — устаревшая колонка, вне реестра/импорта
    "body_type": BODY_TYPE_OPTIONS,                    # E
    "tech_inspection_status": YES_NO_OPTIONS,          # AC (bool-колонка)
    "has_radio": YES_NO_OPTIONS,                       # AZ (bool-колонка)
    "has_spare_wheel": YES_NO_OPTIONS,                 # BG (bool-колонка)
    "has_tracker": YES_NO_OPTIONS,                     # BK (bool-колонка)
    "has_tachograph": YES_NO_OPTIONS,                  # BM (bool-колонка)
    "has_mirrors": YES_NO_OPTIONS,                     # BO (bool-колонка)
    "has_branding": YES_NO_OPTIONS,                    # 2026-09: признак наличия брендирования
}

# Исторические варианты написания, которые нужно продолжать распознавать при
# импорте уже заполненных файлов, сопоставляя их с ТЕКУЩИМ каноническим
# значением справочника (в отличие от "не сопоставилось вовсе" — это
# сознательное переименование, не опечатка пользователя). Ключ — нормализованный
# (casefold) старый текст, значение — новый канонический вариант из options.
_VALUE_ALIASES: Dict[str, Dict[str, str]] = {
    "paint_condition": {
        "идеальное, есть сколы": "Хорошее - есть сколы",  # переименовано владельцем 2026-09
    },
}

# Русские подписи — для текста предупреждений/note (совпадают с заголовками
# исходного листа и/или app/services/vehicle_fields.py FIELD_GROUPS[*]["label"]).
FIELD_LABELS: Dict[str, str] = {
    "tires_type": "Авторезина",
    "has_spare_tires": "Наличие сменной резины",
    "tires_condition": "Состояние резины",
    "paint_condition": "Состояние лакокрасочного покрытия",
    "pass_zo": "Пропуск ЗО",
    "pass_ho": "Пропуск ХО",
    "pass_dnr": "Пропуск ДНР",
    "pass_lnr": "Пропуск ЛНР",
    "pass_moscow": "Пропуск Москва",
    "body_type": "Кузов",
    "tech_inspection_status": "Обязательный техосмотр",
    "has_radio": "Наличие радиостанции",
    "has_spare_wheel": "Наличие запасного колеса",
    "has_tracker": "Трекер",
    "has_tachograph": "Тахограф",
    "has_mirrors": "Наличие и исправность зеркал",
    "has_branding": "Брендирование (Да/Нет)",
    "tires_summer_condition": "Летняя резина — состояние",
    "tires_winter_condition": "Зимняя резина — состояние",
}

_WS_RE = re.compile(r"\s+")
# Частые окончания прилагательных ж./ср. рода — используются ТОЛЬКО чтобы
# распознать "Удовлетворительное" ~ "Удовлетворительная" (разные роды одного
# корня). Каждое ровно 2 символа — порядок перебора не важен.
_ADJ_SUFFIXES = ("ые", "ых", "ая", "яя", "ое", "ее", "ый", "ий", "ой")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", str(text).strip())


def is_no_data_text(raw_value: object) -> bool:
    """True — сырое значение ячейки есть явный осознанный ответ «Нет данных»
    (регистронезависимо, с нормализацией пробелов). Используется НЕ только для
    полей этого справочника (FIELD_OPTIONS), но и для полей с закрытыми
    наборами из app/services/vehicle_enum_labels.py (тип ТС, состояние, вид
    топлива, вид ПТС, категория по ПТС) — единая точка сравнения, чтобы текст
    «Нет данных» не размножался по модулям."""
    if raw_value is None:
        return False
    return _normalize(str(raw_value)).casefold() == NO_DATA_LABEL.casefold()


def _stem(text: str) -> str:
    """Регистронезависимый "корень" строки — отбрасывает одно известное
    окончание прилагательного с конца, если после отбрасывания остаётся
    содержательный остаток (>2 символов). Иначе строка не меняется."""
    s = _normalize(text).casefold()
    for suf in _ADJ_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 2:
            return s[: -len(suf)]
    return s


def has_dictionary(field_key: str) -> bool:
    return field_key in FIELD_OPTIONS


def get_options(field_key: str) -> List[str]:
    return list(FIELD_OPTIONS.get(field_key, []))


def match_value_in_options(options: List[str], raw_value: object) -> Optional[str]:
    """То же сопоставление, что и match_dictionary_value(), но напрямую по
    переданному списку допустимых значений (для полей без постоянного ключа в
    FIELD_OPTIONS — например произвольные названия пропусков из
    app/models/vehicle_pass.py, у которых фиксирован только справочник
    СТАТУСОВ, а не сам набор полей)."""
    if not options or raw_value is None:
        return None
    text = _normalize(str(raw_value))
    if not text:
        return None
    text_cf = text.casefold()
    for opt in options:
        if opt.casefold() == text_cf:
            return opt
    stem = _stem(text)
    candidates = [opt for opt in options if _stem(opt) == stem]
    if len(candidates) == 1:
        return candidates[0]
    return None


def match_dictionary_value(field_key: str, raw_value: object) -> Optional[str]:
    """Сопоставляет сырое значение ячейки с каноническим вариантом набора
    field_key. Возвращает канонический вариант либо None, если:
      - у поля нет справочника, значение пустое;
      - значение не совпало точно (без учёта регистра/лишних пробелов) ни с
        одним вариантом (в т.ч. через _VALUE_ALIASES — старое написание,
        сознательно переименованное владельцем, см. _VALUE_ALIASES выше);
      - "по корню" (см. _stem) подошло сразу к НЕСКОЛЬКИМ вариантам —
        неоднозначность не угадывается, значение считается несопоставленным.
    """
    options = FIELD_OPTIONS.get(field_key)
    if not options or raw_value is None:
        return None
    aliases = _VALUE_ALIASES.get(field_key)
    if aliases:
        text_cf = _normalize(str(raw_value)).casefold()
        aliased = aliases.get(text_cf)
        if aliased is not None:
            return aliased
    return match_value_in_options(options, raw_value)
