"""Column-mapping spec for vehicles Excel import — extracted from
app/routers/vehicles_import.py (Правило №5, разрезание 2026-09-08).

Заголовок xlsx (нормализованный) → имя поля Vehicle (или ключ props, см.
_PROPS_KEYS). Источник правды по составу и алиасам заголовков — здесь;
app/services/vehicle_import_template.py (генератор шаблона для скачивания)
и _parse_xlsx_to_rows (app/services/fleet_import_parser.py, использует
_resolve_header_columns отсюда) обязаны сходиться на одном и том же
словаре, не заводить параллельных копий (Правило №6).

_COL_MAP — один литерал ~200 строк, осознанное исключение из лимита ~500
строк на файл (тот же паттерн, что и _COL_SPEC в
app/services/import_template_spec.py, см. коммит 0b7c772): резать словарь на
части было бы менее читаемо, чем держать целиком.
"""
import logging
import re
from typing import Any, Dict, Optional

from app.services.vehicle_sheet_dictionaries import FIELD_OPTIONS as _DICT_FIELD_OPTIONS


# ─────────────────────────── Column mapping (inline, DRY-able later) ─────────
#
# Автоблок (AUTOBLOCK_FIELDS_SPEC.md §6): лист «26.05.2026» (реестр Голичкова,
# 71 колонка) содержит опечатки в заголовках («в соответи», «Исправнось»,
# «возникнования») — приняты как есть, плюс добавлены исправленные варианты.
# Ключи нормализуются: lower() + схлопывание любых пробелов до одного.
#
# Пять заголовков «Дата истечения пропуска» и один «Дата поверки» (без
# уточнения) неоднозначны по имени — разрешаются ПОЗИЦИОННО в
# _resolve_header_columns (ближайшая слева колонка `Пропуск X` / `Огнетушитель`).
#
# Дубликаты (значение уже занято более ранней колонкой в той же строке
# заголовков) автоматически игнорируются через occupied-tracking в
# _resolve_header_columns — так закрываются все "три дубля" из §6:
# «Кузов в соответствии с ПТС» (дубль «Кузов»), второе «Состояние
# лакокрасочного покрытия», «Наличие и исправность зеркал».

# Специальный маркер поля: колонка «Марка и модель ТС» разбирается по первому
# пробелу на brand/model (§6).
_BRAND_MODEL_SPLIT_FIELD = "__brand_model__"

# Поля, чьё реальное хранилище — vehicles.props (JSONB), а не колонка.
# Ключ словаря = ключ внутри props (совпадает с services/vehicle_fields.py).
_PROPS_KEYS = {"tires_type", "branding", "paint_condition", "defect_description", "note"}

# Maps XLSX column headers (lowercased, whitespace-collapsed) → Vehicle field name
# (или ключ props, если он в _PROPS_KEYS).
_COL_MAP: Dict[str, str] = {
    "гос. номер": "plate",
    "гос.номер": "plate",
    "госномер": "plate",
    "гос номер": "plate",
    "регистрационный знак": "plate",
    "гос. рег. знак": "plate",
    "марка": "brand",
    "модель": "model",
    "марка и модель тс": _BRAND_MODEL_SPLIT_FIELD,
    "цвет": "color",
    "vin": "vin",
    "тип": "type",
    "состояние": "state",
    "топливо": "fuel_type",
    "вид топлива": "fuel_type",
    "норма лето": "fuel_norm_summer",
    "норма зима": "fuel_norm_winter",
    "следующее то": "next_to_km",
    "у кого в эксплуатации": "assigned_text",
    "у кого в эксплуатации (здесь пишется организация, а не город)": "assigned_text",
    "кому принадлежит": "owner_text",
    "собственник": "owner_text",
    "инн собственника": "owner_inn",
    "инн эксплуатант": "assigned_inn",
    "инн эксплуатанта": "assigned_inn",
    "дата регистрации": "registered_at",
    "страховка до": "insurance_until",
    "трекер": "has_tracker",
    "аккумулятор": "akb_ok",
    "рация": "has_radio",
    "наличие радиостанции": "has_radio",
    "зеркала": "mirrors_ok",
    "наличие зеркал": "has_mirrors",
    "исправнось зеркал": "mirrors_ok",       # опечатка исходника
    "исправность зеркал": "mirrors_ok",      # исправленный вариант
    "наличие и исправность зеркал": "has_mirrors",  # дубль-комбо; occupied-skip если has_mirrors уже занято
    "ключи": "has_keys",
    "наличие набора ключей": "has_keys",
    "аптечка": "has_first_aid_kit",
    "наличие аптечки": "has_first_aid_kit",
    "запаска": "has_spare_wheel",
    "наличие запасного колеса": "has_spare_wheel",
    "огнетушитель": "has_extinguisher",
    # ── Автоблок: реестр Голичкова, лист «26.05.2026» (§1, §2, §6) ───────────
    "кузов": "body_type",
    "кузов в соответи": "body_type",                              # опечатка исходника, дубль → occupied-skip
    "кузов в соответствии с птс": "body_type",                    # исправленный вариант
    "категория тс в соответсвии с птс": "pts_category",           # опечатка исходника
    "категория тс в соответствии с птс": "pts_category",          # исправленный вариант
    "категория тс по птс": "pts_category",
    "год вып.": "year_of_manufacture",
    "год выпуска": "year_of_manufacture",
    "номер страхового договора": "insurance_policy_number",
    "страховая компания": "insurance_company",
    "срок действия страховки (до каког числа включительно)": "insurance_until",   # опечатка исходника
    "срок действия страховки (до какого числа включительно)": "insurance_until",  # исправленный вариант
    "пробег на данный момент км": "current_odometer_km",
    "основание возникновения собственности": "ownership_basis",
    "№ документа основания возникнования собственности": "ownership_doc_number",   # опечатка исходника
    "№ документа основания возникновения собственности": "ownership_doc_number",   # исправленный вариант
    "дата документа основания возникнования собственности": "ownership_doc_date",  # опечатка исходника
    "дата документа основания возникновения собственности": "ownership_doc_date",  # исправленный вариант
    "место нахождения город": "location_city",
    "место нахождения адрес": "location_address",
    # 2026-09: "Место нахождения" переименовано в "Текущее место нахождения" (владелец
    # различает постоянную приписку ТС и его текущее физическое местоположение) —
    # старые алиасы выше НЕ удалены, чтобы уже заполненные файлы владельца продолжали
    # читаться; новые добавлены для файлов, скачанных после переименования подписи.
    "текущее место нахождения город": "location_city",
    "текущее место нахождения, город": "location_city",
    "текущее место нахождения адрес": "location_address",
    "текущее место нахождения, адрес": "location_address",
    # Место постоянной приписки ТС — новое поле (где машина закреплена, в отличие от
    # текущего физического местонахождения выше).
    "место постоянной приписки тс": "home_base_city",
    "место постоянной приписки": "home_base_city",
    "постоянная приписка": "home_base_city",
    "постоянная приписка тс": "home_base_city",
    "основание возникновения права эксплуатации": "assignment_basis",
    "кто субсидировал": "purchase_info",
    "№ документа основания возникнования права эксплуатации": "assignment_doc_number",   # опечатка
    "№ документа основания возникновения права эксплуатации": "assignment_doc_number",   # исправлено
    "дата документа основания возникнования права эксплуатации": "assignment_doc_date",  # опечатка
    "дата документа основания возникновения права эксплуатации": "assignment_doc_date",  # исправлено
    "дата последнего планового то": "last_to_date",
    "пробег на последнем плановом то": "last_to_mileage_km",
    "обязательный техосмотр": "tech_inspection_status",
    "дата последнего обязательного техосмотра": "tech_inspection_last_date",
    "ответственный (фамилия имя отчество)": "responsible_name",
    "птс": "pts_number",
    "вид птс (бумажный/электронный)": "pts_kind",
    "дата когда организация владелец стала собственником": "owner_since",   # исходный (без запятой)
    "дата, когда организация владелец стала собственником": "owner_since",  # грамматически верный вариант (с запятой перед "когда")
    "стс номер": "sts_number",
    "стс дата выдачи": "sts_issued_at",
    "состояние лакокрасочного покрытия": "paint_condition",  # props; 2-е вхождение → occupied-skip
    # 2026-09: "Пропуск ЗО/ХО/ДНР/ЛНР/Москва" и "Дата истечения пропуска Х" НЕ
    # резолвятся здесь больше в field-имя Vehicle — заменены на маркеры
    # "__pass_status__:<Имя>"/"__pass_until__:<Имя>" (см. _LEGACY_PASS_STATUS_HEADERS/
    # _LEGACY_PASS_UNTIL_HEADERS ниже и _resolve_header_columns) — старые заголовки
    # по-прежнему распознаются (файлы владельца продолжают парситься), но данные
    # теперь уходят в таблицу vehicle_passes, а не в колонки vehicles.pass_*.
    "авторезина установленная на машине": "tires_type",   # props; исходный (без запятой)
    "авторезина, установленная на машине": "tires_type",  # props; грамматически верный вариант (с запятой)
    "авторезина установленная на автомобиле": "tires_type",   # 2026-09: новая формулировка подписи реестра
    "авторезина, установленная на автомобиле": "tires_type",  # 2026-09: новая формулировка подписи реестра
    "наличие сменной резины": "has_spare_tires",
    "состояние резины": "tires_condition",  # устаревшее общее поле — оставлено для старых файлов
    "брендирование": "branding",  # props; устаревший алиас — старые файлы (свободный текст состояния)
    "состояние брендирования": "branding",  # props; 2026-09: новая подпись того же текстового поля
    "брендирование (да/нет)": "has_branding",  # 2026-09: новый типизированный признак наличия
    # 2026-09: резина — сезонные комплекты (см. app/models/vehicle.py)
    "летняя резина — радиус": "tires_summer_radius",
    "летняя резина - радиус": "tires_summer_radius",
    "летняя резина — профиль": "tires_summer_profile",
    "летняя резина - профиль": "tires_summer_profile",
    "летняя резина — состояние": "tires_summer_condition",
    "летняя резина - состояние": "tires_summer_condition",
    "зимняя резина — радиус": "tires_winter_radius",
    "зимняя резина - радиус": "tires_winter_radius",
    "зимняя резина — профиль": "tires_winter_profile",
    "зимняя резина - профиль": "tires_winter_profile",
    "зимняя резина — состояние": "tires_winter_condition",
    "зимняя резина - состояние": "tires_winter_condition",
    "срок истечения срока использования": "first_aid_kit_until",
    "дата поверки тахографа": "tachograph_check_date",
    "дата оплаты трекера": "tracker_paid_until",
    "тахограф": "has_tachograph",
    "требуется ремонт/не требуется ремонт": "repair_required",
    "неисправность": "defect_description",  # props
    "примечание": "note",  # props
    "сведения о техническом состоянии": "tech_condition_info",

    # ── Алиасы под точный текст подписей реестра vehicle_fields.py (Автоблок:
    # «шаблон импорта транспорта») — генератор шаблона (services/vehicle_import_template.py)
    # пишет заголовки строго из FIELD_GROUPS[*]["label"], и каждый обязан тут резолвиться.
    # Только ДОБАВЛЕНО: ни один существующий ключ выше не переписан и не удалён —
    # старые файлы продолжают парситься как прежде.
    "тип тс": "type",
    "мощность двигателя, л.с.": "engine_power_hp",
    "объём двигателя, л": "engine_volume_l",
    "норма расхода топлива, лето": "fuel_norm_summer",
    "норма расхода топлива, зима": "fuel_norm_winter",
    # "Организация-собственник" резолвится в owner_text (тот же псевдо-ключ, что и
    # "кому принадлежит"/"собственник" выше) — сопоставление с организацией по имени
    # происходит на шаге commit_import, owner_org_id не заполняется из файла напрямую.
    "организация-собственник": "owner_text",
    "№ документа основания собственности": "ownership_doc_number",
    "дата документа основания собственности": "ownership_doc_date",
    "дата, когда организация стала собственником": "owner_since",
    "у кого в эксплуатации (текст)": "assigned_text",
    "№ документа основания права эксплуатации": "assignment_doc_number",
    "дата документа основания права эксплуатации": "assignment_doc_date",
    "место нахождения — город": "location_city",
    "место нахождения — адрес": "location_address",
    "ответственный (фио)": "responsible_name",
    "номер птс": "pts_number",
    "вид птс": "pts_kind",
    "номер стс": "sts_number",
    "стс — дата выдачи": "sts_issued_at",
    "страховка действительна до": "insurance_until",
    "текущий пробег, км": "current_odometer_km",
    "дата последнего то": "last_to_date",
    "пробег на последнем то": "last_to_mileage_km",
    "километраж следующего то": "next_to_km",
    "техосмотр действителен до": "tech_inspection_until",
    # "Дата истечения пропуска X" с суффиксом — см. _LEGACY_PASS_UNTIL_HEADERS ниже
    # (2026-09: резолвится в __pass_until__:<Имя>, а не в колонку vehicles.pass_*_until).
    "аккумулятор исправен": "akb_ok",
    "аптечка — срок истечения использования": "first_aid_kit_until",
    "огнетушитель — дата поверки": "extinguisher_check_date",
    "трекер — дата оплаты": "tracker_paid_until",
    "тахограф — дата поверки": "tachograph_check_date",
    "требуется ремонт": "repair_required",
}

# Заголовки, разрешаемые ПОЗИЦИОННО (не через прямой словарь) — §6.
_AMBIGUOUS_PASS_UNTIL_LABEL = "дата истечения пропуска"
_AMBIGUOUS_CHECK_DATE_LABEL = "дата поверки"  # без уточнения → к ближайшему слева «Огнетушитель»

# ─────────────────────── Пропуска (2026-09): произвольный набор ─────────────
#
# Заменяет старые 10 колонок vehicles.pass_* (Автоблок §1) — владелец потребовал
# возможность заводить СВОИ названия пропусков на каждую машину (не enum из 5
# фиксированных зон). Данные уходят в отдельную таблицу vehicle_passes
# (app/models/vehicle_pass.py), НЕ в колонки Vehicle — поэтому поля-маркеры
# "__pass_status__:<Имя>" / "__pass_until__:<Имя>" не входят ни в _VEHICLE_FIELDS,
# ни в _PROPS_KEYS: они обрабатываются отдельной веткой в _parse_xlsx_to_rows,
# результат складывается в row["passes"], см. _apply_row_passes() в commit_import.
#
# Два источника распознавания заголовков:
#   1) СТАРЫЙ формат без названия-суффикса в скобках/двоеточии — ровно те же
#      пять заголовков, что были раньше ("Пропуск ЗО" и т.п.) — чтобы уже
#      заполненные файлы владельца продолжали разбираться один-в-один
#      (см. _LEGACY_PASS_STATUS_HEADERS/_LEGACY_PASS_UNTIL_HEADERS).
#   2) НОВЫЙ формат "Пропуск: <Название>" / "Пропуск: <Название> — до" — то, что
#      выводит обновлённый шаблон импорта (app/services/vehicle_import_template.py)
#      и что позволяет организациям дописывать ЛЮБЫЕ свои названия пропусков
#      прямо в файле (см. _PASS_STATUS_HDR_RE/_PASS_UNTIL_HDR_RE ниже —
#      разрешаются регуляркой в _resolve_header_columns, а не фиксированным словарём).
_PASS_STATUS_MARK = "__pass_status__:"
_PASS_UNTIL_MARK = "__pass_until__:"

_LEGACY_PASS_STATUS_HEADERS: Dict[str, str] = {
    "пропуск зо": "ЗО", "пропуск хо": "ХО", "пропуск днр": "ДНР",
    "пропуск лнр": "ЛНР", "пропуск москва": "Москва",
}
_LEGACY_PASS_UNTIL_HEADERS: Dict[str, str] = {
    "дата истечения пропуска зо": "ЗО", "дата истечения пропуска хо": "ХО",
    "дата истечения пропуска днр": "ДНР", "дата истечения пропуска лнр": "ЛНР",
    "дата истечения пропуска москва": "Москва",
}

# Регулярки — против ИСХОДНОГО (регистр сохранён) текста заголовка, не против
# нормализованного _normalize_header(), чтобы название пропуска в маркере
# сохраняло написание пользователя ("ЗО", а не "зо").
_PASS_UNTIL_HDR_RE = re.compile(r"^пропуск:\s*(.+?)\s*—\s*до\s*$", re.IGNORECASE)
_PASS_STATUS_HDR_RE = re.compile(r"^пропуск:\s*(.+)$", re.IGNORECASE)

_BOOL_COLS = {
    "has_tracker", "akb_ok", "has_radio", "mirrors_ok",
    "has_keys", "has_first_aid_kit", "has_spare_wheel", "has_extinguisher",
    # Автоблок
    "has_spare_tires", "has_mirrors", "has_tachograph",
    "has_branding",  # 2026-09
}
# repair_required коэрсится отдельно (_coerce_repair_required) — presence-based эвристика
_REPAIR_REQUIRED_FIELD = "repair_required"

# ─────────────────── Справочники допустимых значений (правила проверки листа
# владельца, см. app/services/vehicle_sheet_dictionaries.py) ─────────────────
#
# Часть полей справочника хранится как bool-колонка (_BOOL_COLS, коэрсится
# _coerce_bool), часть — как свободный текст/props (без справочника раньше
# принимался ЛЮБОЙ текст — марки шин, диагнозы ЛКП и т.п. утекали в колонку).
# Разделяем по способу хранения: bool-поля продолжают идти через _coerce_bool
# (уже отбрасывает нераспознанное в None), но теперь дополнительно поднимают
# предупреждение и сохраняют исходный текст в note, если текст был, но не
# распознан. Строковые/props-поля сопоставляются через match_dictionary_value —
# несопоставленное НЕ пишется в колонку вовсе, только в предупреждение + note.
_DICT_BOOL_FIELDS = {f for f in _DICT_FIELD_OPTIONS if f in _BOOL_COLS}
_DICT_STRING_FIELDS = {f for f in _DICT_FIELD_OPTIONS if f not in _BOOL_COLS}

def _load_date_columns_from_registry() -> set:
    """Источник правды по датам — реестр app/services/vehicle_fields.py (type="date").

    Lesson (coordinator review 2026-08-31): раньше _DATE_COLS поддерживался руками
    и разошёлся с моделью Vehicle — last_to_date/assignment_doc_date/tech_inspection_until
    были Date-колонками в модели и уже маппились из _COL_MAP, но отсутствовали здесь,
    из-за чего нераспознанный текст ("3 000км до ТО") не проходил через _coerce_date
    и уезжал в поле сырой строкой. Теперь множество собирается программно, чтобы то
    же самое не повторилось при добавлении следующего date-поля.
    """
    try:
        from app.services.vehicle_fields import get_all_fields
        return {f["key"] for f in get_all_fields() if f.get("type") == "date" and f.get("storage") == "column"}
    except Exception:
        # Не должно случиться в норме — реестр всегда доступен; safety-net на случай
        # проблем импорта не должен ронять весь модуль импорта.
        logging.getLogger(__name__).exception("Не удалось загрузить date-поля из реестра vehicle_fields")
        return {"registered_at", "insurance_until"}


_DATE_COLS = _load_date_columns_from_registry()
# engine_power_hp/engine_volume_l добавлены вместе с колонками шаблона импорта
# (Автоблок: «шаблон импорта транспорта») — раньше эти заголовки не резолвились
# вообще ни одним алиасом _COL_MAP, поэтому и не требовали коэрсии.
_FLOAT_COLS = {"fuel_norm_summer", "fuel_norm_winter", "engine_volume_l"}
_INT_COLS = {
    "next_to_km", "year_of_manufacture", "current_odometer_km", "last_to_mileage_km",
    "engine_power_hp",
}

# Ограничения длины VARCHAR-колонок — защита от "value too long for type
# character varying(N)" при коммите разнородных реальных данных (см. Lesson:
# реальные значения "Состояние" превышают 20 симв.). Раньше был захардкожен
# руками и рисковал разъехаться с моделью (тот же класс бага, что уже был у
# _DATE_COLS) — coordinator review 2026-08-31 попросил свести к одному
# программному источнику вместе с валидацией в routers/vehicles.py.
def _load_string_column_limits() -> Dict[str, int]:
    try:
        from app.services.vehicle_fields import get_string_column_limits
        return get_string_column_limits()
    except Exception:
        logging.getLogger(__name__).exception("Не удалось загрузить лимиты длины из реестра vehicle_fields")
        return {"plate": 20, "vin": 17}


_MAX_LEN: Dict[str, int] = _load_string_column_limits()



def _normalize_header(cell: Any) -> str:
    """lower() + схлопывание любых пробельных последовательностей до одного."""
    return re.sub(r"\s+", " ", str(cell).strip()).strip().lower()


def _resolve_header_columns(header_raw: tuple) -> tuple[Dict[int, str], list[str]]:
    """Разрешает заголовки листа в {col_index: field_or_props_key} (§6).

    Возвращает (col_field, unresolved_headers). unresolved_headers — исходный
    (не нормализованный) текст заголовков, которые не удалось сопоставить ни
    с одним полем (ожидаемо: «№ п/п» — не несёт данных; плюс три дубля,
    автоматически поглощённые occupied-tracking'ом).

    «ИНН собственника» / «ИНН эксплуатант» РАЗРЕШАЮТСЯ (owner_inn/assigned_inn,
    см. _COL_MAP ниже) — используются в app.services.vehicle_org_matching для
    приоритетного сопоставления организации по ИНН (owner/assigned_text —
    fallback по названию). Сами по себе в колонки Vehicle не пишутся (не входят
    в _VEHICLE_FIELDS), это чисто ключи сопоставления на этапе preview/commit.

    Ambiguous заголовки («Дата истечения пропуска» x5, «Дата поверки» без
    уточнения) разрешаются позиционно — по ближайшей слева колонке
    `Пропуск X` / `Огнетушитель`. Настоящие дубли (значение, для которого
    поле уже занято более ранней колонкой) автоматически пропускаются.
    """
    col_field: Dict[int, str] = {}
    unresolved: list[str] = []
    occupied: set[str] = set()

    last_pass_name: Optional[str] = None  # canonical название пропуска — для позиционной "Дата истечения пропуска"
    last_was_extinguisher = False

    for ci, cell in enumerate(header_raw):
        if cell is None:
            continue
        raw_text = str(cell).strip()
        if not raw_text:
            continue
        key = _normalize_header(cell)
        raw_norm = re.sub(r"\s+", " ", raw_text).strip()  # регистр сохранён, пробелы схлопнуты

        field: Optional[str] = None

        if key == _AMBIGUOUS_PASS_UNTIL_LABEL:
            if last_pass_name:
                field = f"{_PASS_UNTIL_MARK}{last_pass_name}"
            last_pass_name = None
            last_was_extinguisher = False
        elif key == _AMBIGUOUS_CHECK_DATE_LABEL:
            if last_was_extinguisher:
                field = "extinguisher_check_date"
            last_was_extinguisher = False
        elif key in _LEGACY_PASS_UNTIL_HEADERS:
            field = f"{_PASS_UNTIL_MARK}{_LEGACY_PASS_UNTIL_HEADERS[key]}"
            last_pass_name = None
            last_was_extinguisher = False
        elif key in _LEGACY_PASS_STATUS_HEADERS:
            name = _LEGACY_PASS_STATUS_HEADERS[key]
            field = f"{_PASS_STATUS_MARK}{name}"
            last_pass_name = name
            last_was_extinguisher = False
        elif (m := _PASS_UNTIL_HDR_RE.match(raw_norm)) is not None:
            name = m.group(1).strip()
            field = f"{_PASS_UNTIL_MARK}{name}" if name else None
            last_pass_name = None
            last_was_extinguisher = False
        elif (m := _PASS_STATUS_HDR_RE.match(raw_norm)) is not None:
            name = m.group(1).strip()
            field = f"{_PASS_STATUS_MARK}{name}" if name else None
            last_pass_name = name if name else None
            last_was_extinguisher = False
        elif key in _COL_MAP:
            field = _COL_MAP[key]
            last_pass_name = None
            last_was_extinguisher = (field == "has_extinguisher")
        else:
            last_pass_name = None
            last_was_extinguisher = False

        if field is None:
            unresolved.append(raw_text)
            continue

        if field in _PROPS_KEYS:
            occ_key = f"props:{field}"
        else:
            occ_key = field
        if occ_key in occupied:
            unresolved.append(raw_text)
            continue

        occupied.add(occ_key)
        col_field[ci] = field

    return col_field, unresolved


