"""
Реестр полей карточки ТС — единственный источник правды о полях, их типах,
группах и признаке "можно ли скрыть". Автоблок §2.

Используется:
  - app/routers/vehicle_fields.py — GET/PUT каталога с учётом конфигурации организации
  - app/routers/vehicles.py       — экспорт Excel (пропуск скрытых полей)

storage:
  column   — колонка таблицы vehicles (ключ == имя атрибута модели Vehicle)
  props    — ключ в vehicles.props (JSONB); "props_key" — реальный ключ внутри JSONB
  computed — вычисляемое поле (owner_inn / operator_inn), в БД не хранится

Конфигурация скрытия полей переиспользует org_section_config (без новой таблицы),
ключи пишутся с префиксом CONFIG_KEY_PREFIX, см. §3.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

CONFIG_KEY_PREFIX = "vehicle_field:"

# Поля, которые нельзя скрыть — без них карточка ТС не работает (§2).
LOCKED_KEYS: Set[str] = {"plate", "owner_org_id", "state"}

FIELD_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "identity", "title": "Идентификация",
        "fields": [
            # Автоблок (2026-09): гос. номер больше НЕ обязателен — машина может быть
            # куплена, но ещё не поставлена на учёт (владелец). Поле остаётся
            # незакрываемым (LOCKED_KEYS) — не required.
            {"key": "plate", "label": "Гос. рег. знак", "type": "string", "storage": "column"},
            {"key": "brand", "label": "Марка", "type": "string", "storage": "column"},
            {"key": "model", "label": "Модель", "type": "string", "storage": "column"},
            {"key": "year_of_manufacture", "label": "Год выпуска", "type": "int", "storage": "column"},
            {"key": "color", "label": "Цвет", "type": "string", "storage": "column"},
            {"key": "vin", "label": "VIN", "type": "string", "storage": "column"},
            {"key": "type", "label": "Тип ТС", "type": "enum", "storage": "column"},
            {"key": "body_type", "label": "Кузов", "type": "string", "storage": "column"},
            {"key": "pts_category", "label": "Категория ТС по ПТС", "type": "string", "storage": "column"},
            {"key": "engine_power_hp", "label": "Мощность двигателя, л.с.", "type": "int", "storage": "column"},
            {"key": "engine_volume_l", "label": "Объём двигателя, л", "type": "float", "storage": "column"},
            {"key": "fuel_type", "label": "Вид топлива", "type": "enum", "storage": "column"},
            {"key": "fuel_norm_summer", "label": "Норма расхода топлива, лето", "type": "float", "storage": "column"},
            {"key": "fuel_norm_winter", "label": "Норма расхода топлива, зима", "type": "float", "storage": "column"},
        ],
    },
    {
        "key": "ownership", "title": "Собственность",
        "fields": [
            {"key": "owner_org_id", "label": "Организация-собственник", "type": "org", "storage": "column", "required": True},
            {"key": "owner_inn", "label": "ИНН собственника", "type": "readonly", "storage": "computed",
             "source_hint": "Заполняется автоматически из карточки организации-собственника (поле ИНН там же)"},
            {"key": "ownership_basis", "label": "Основание возникновения собственности", "type": "string", "storage": "column"},
            {"key": "ownership_doc_number", "label": "№ документа основания собственности", "type": "string", "storage": "column"},
            {"key": "ownership_doc_date", "label": "Дата документа основания собственности", "type": "date", "storage": "column"},
            {"key": "owner_since", "label": "Дата, когда организация стала собственником", "type": "date", "storage": "column"},
            {"key": "purchase_info", "label": "Кто субсидировал", "type": "string", "storage": "column"},
        ],
    },
    {
        "key": "operation", "title": "Эксплуатация",
        "fields": [
            {"key": "assigned_org_id", "label": "Организация-эксплуатант", "type": "org", "storage": "column"},
            {"key": "assigned_text", "label": "У кого в эксплуатации (текст)", "type": "string", "storage": "column"},
            {"key": "operator_inn", "label": "ИНН эксплуатанта", "type": "readonly", "storage": "computed",
             "source_hint": "Заполняется автоматически из карточки организации-эксплуатанта (поле ИНН там же)"},
            {"key": "assignment_basis", "label": "Основание возникновения права эксплуатации", "type": "string", "storage": "column"},
            {"key": "assignment_doc_number", "label": "№ документа основания права эксплуатации", "type": "string", "storage": "column"},
            {"key": "assignment_doc_date", "label": "Дата документа основания права эксплуатации", "type": "date", "storage": "column"},
            {"key": "location_city", "label": "Текущее место нахождения, город", "type": "string", "storage": "column"},
            {"key": "location_address", "label": "Текущее место нахождения, адрес", "type": "string", "storage": "column"},
            {"key": "home_base_city", "label": "Место постоянной приписки ТС", "type": "string", "storage": "column"},
            {"key": "responsible_name", "label": "Ответственный (ФИО)", "type": "string", "storage": "column"},
        ],
    },
    {
        "key": "docs", "title": "Документы",
        "fields": [
            {"key": "pts_number", "label": "Номер ПТС", "type": "string", "storage": "column"},
            {"key": "pts_kind", "label": "Вид ПТС", "type": "enum", "storage": "column"},
            {"key": "sts_number", "label": "Номер СТС", "type": "string", "storage": "column"},
            {"key": "sts_issued_at", "label": "СТС — дата выдачи", "type": "date", "storage": "column"},
            {"key": "registered_at", "label": "Дата регистрации", "type": "date", "storage": "column"},
            {"key": "insurance_company", "label": "Страховая компания", "type": "string", "storage": "column"},
            {"key": "insurance_policy_number", "label": "Номер страхового договора", "type": "string", "storage": "column"},
            {"key": "insurance_until", "label": "Страховка действительна до", "type": "date", "storage": "column"},
        ],
    },
    {
        "key": "maintenance", "title": "ТО и техосмотр",
        "fields": [
            {"key": "current_odometer_km", "label": "Текущий пробег, км", "type": "int", "storage": "column",
             "source_hint": "Не редактируется напрямую — берётся из самой свежей записи одометра "
                             "(вкладка «Одометр» карточки ТС / POST /api/vehicle-odometer)"},
            {"key": "last_to_date", "label": "Дата последнего ТО", "type": "date", "storage": "column"},
            {"key": "last_to_mileage_km", "label": "Пробег на последнем ТО", "type": "int", "storage": "column"},
            {"key": "next_to_km", "label": "Километраж следующего ТО", "type": "int", "storage": "column"},
            {"key": "tech_inspection_status", "label": "Обязательный техосмотр", "type": "string", "storage": "column"},
            {"key": "tech_inspection_last_date", "label": "Дата последнего обязательного техосмотра", "type": "date", "storage": "column"},
            {"key": "tech_inspection_until", "label": "Техосмотр действителен до", "type": "date", "storage": "column"},
        ],
    },
    {
        # Автоблок (2026-09): 10 фиксированных колонок pass_* убраны из реестра —
        # владелец потребовал произвольный набор пропусков на машину (разные
        # организации заводят разные зоны). Новый источник правды —
        # app/models/vehicle_pass.py (таблица vehicle_passes) + отдельный
        # роутер app/routers/vehicle_passes.py (CRUD + копирование набора между
        # машинами). Сами колонки vehicles.pass_* НЕ удалены из БД (данные
        # перенесены миграцией), но реестр/шаблон импорта/импорт их больше не
        # видят — см. get_related_blocks() ниже для описания нового места.
        "key": "equipment", "title": "Оснащение",
        "fields": [
            {"key": "tires_type", "label": "Авторезина, установленная на автомобиле", "type": "string", "storage": "props", "props_key": "tires_type",
             "source_hint": "Значение — какой из двух комплектов (Летний/Зимний, см. группу «Резина — комплекты») сейчас на машине"},
            {"key": "has_spare_tires", "label": "Наличие сменной резины", "type": "bool", "storage": "column"},
            {"key": "has_radio", "label": "Наличие радиостанции", "type": "bool", "storage": "column"},
            {"key": "has_mirrors", "label": "Наличие зеркал", "type": "bool", "storage": "column"},
            {"key": "mirrors_ok", "label": "Исправность зеркал", "type": "bool", "storage": "column"},
            {"key": "akb_ok", "label": "Аккумулятор исправен", "type": "bool", "storage": "column"},
            # Отдельная подпись от "Состояние брендирования" (props.branding) НАМЕРЕННО:
            # "Брендирование" — уже занятый заголовок старых файлов владельца (алиас
            # в _COL_MAP резолвится в props.branding, менять нельзя — сломает их разбор).
            {"key": "has_branding", "label": "Брендирование (Да/Нет)", "type": "bool", "storage": "column"},
            {"key": "branding", "label": "Состояние брендирования", "type": "string", "storage": "props", "props_key": "branding"},
            {"key": "has_keys", "label": "Наличие набора ключей", "type": "bool", "storage": "column"},
            {"key": "has_first_aid_kit", "label": "Наличие аптечки", "type": "bool", "storage": "column"},
            {"key": "first_aid_kit_until", "label": "Аптечка — срок истечения использования", "type": "date", "storage": "column"},
            {"key": "has_spare_wheel", "label": "Наличие запасного колеса", "type": "bool", "storage": "column"},
            {"key": "has_extinguisher", "label": "Огнетушитель", "type": "bool", "storage": "column"},
            {"key": "extinguisher_check_date", "label": "Огнетушитель — дата поверки", "type": "date", "storage": "column"},
            {"key": "has_tracker", "label": "Трекер", "type": "bool", "storage": "column"},
            {"key": "tracker_paid_until", "label": "Трекер — дата оплаты", "type": "date", "storage": "column"},
            {"key": "has_tachograph", "label": "Тахограф", "type": "bool", "storage": "column"},
            {"key": "tachograph_check_date", "label": "Тахограф — дата поверки", "type": "date", "storage": "column"},
        ],
    },
    {
        # Автоблок (2026-09): "Куда-то пропали данные о сменной резине" — раньше
        # было одно общее tires_condition без разбивки на сезон. Теперь два
        # именованных комплекта; equipment.tires_type выше указывает, какой из
        # них сейчас установлен на машине.
        "key": "tires", "title": "Резина — комплекты",
        "fields": [
            {"key": "tires_summer_radius", "label": "Летняя резина — радиус", "type": "string", "storage": "column"},
            {"key": "tires_summer_profile", "label": "Летняя резина — профиль", "type": "string", "storage": "column"},
            {"key": "tires_summer_condition", "label": "Летняя резина — состояние", "type": "string", "storage": "column"},
            {"key": "tires_winter_radius", "label": "Зимняя резина — радиус", "type": "string", "storage": "column"},
            {"key": "tires_winter_profile", "label": "Зимняя резина — профиль", "type": "string", "storage": "column"},
            {"key": "tires_winter_condition", "label": "Зимняя резина — состояние", "type": "string", "storage": "column"},
        ],
    },
    {
        "key": "condition", "title": "Состояние",
        "fields": [
            {"key": "state", "label": "Состояние", "type": "enum", "storage": "column", "required": True},
            {"key": "paint_condition", "label": "Состояние лакокрасочного покрытия", "type": "string", "storage": "props", "props_key": "paint_condition"},
            {"key": "repair_required", "label": "Требуется ремонт", "type": "bool", "storage": "column"},
            {"key": "defect_description", "label": "Неисправность", "type": "string", "storage": "props", "props_key": "defect_description"},
            {"key": "tech_condition_info", "label": "Сведения о техническом состоянии", "type": "text", "storage": "column"},
            {"key": "note", "label": "Примечание", "type": "string", "storage": "props", "props_key": "note"},
        ],
    },
]


def get_all_fields() -> List[Dict[str, Any]]:
    """Плоский список всех полей реестра (без разбивки по группам)."""
    return [f for g in FIELD_GROUPS for f in g["fields"]]


def get_all_field_keys() -> Set[str]:
    return {f["key"] for f in get_all_fields()}


def is_lockable(key: str) -> bool:
    """True — поле можно скрыть. False — обязательное, скрыть нельзя."""
    return key not in LOCKED_KEYS


def get_field_label(key: str) -> Optional[str]:
    for f in get_all_fields():
        if f["key"] == key:
            return f["label"]
    return None


def build_catalog(hidden_keys: Set[str]) -> List[Dict[str, Any]]:
    """Собрать группы полей с флагами hidden/lockable/required для ответа GET /api/vehicle-fields.

    Автоблок (актуализация 2026-08-31): поля, ограниченные набором значений из
    правил проверки данных листа владельца (app.services.vehicle_sheet_dictionaries),
    получают "options" — список допустимых значений. Единственный источник
    правды для выпадающих списков карточки ТС на фронте — там вторая копия
    списков не хранится, а берётся отсюда.

    Поле "type" («Тип ТС») — отдельный случай: набор значений живёт не в
    vehicle_sheet_dictionaries (это код→подпись пара, TYPE_LABELS из
    app.services.vehicle_enum_labels — колонка Vehicle.type хранит КОД, не
    подпись, в отличие от body_type/paint_condition и т.п., где options —
    сами хранимые строки). "options" для "type" здесь — только отсортированные
    ПОДПИСИ (владелец, 2026-09: «Тип ТС» отсортировать по алфавиту) для показа/
    сверки; сопоставление подпись→код на фронте не завязано на этот список
    (см. frontend/src/utils/vehicleLabels.ts).
    """
    from app.services.vehicle_enum_labels import TYPE_LABELS, as_dd_list
    from app.services.vehicle_sheet_dictionaries import FIELD_OPTIONS as _dict_options

    type_labels_sorted = [label for label, code in as_dd_list(TYPE_LABELS, sort_alpha=True) if code is not None]

    groups = []
    for g in FIELD_GROUPS:
        fields = []
        for f in g["fields"]:
            lockable = is_lockable(f["key"])
            item = {
                **f,
                "lockable": lockable,
                "required": bool(f.get("required", False)),
                # locked-поля нельзя скрыть даже если в конфиге завалялась запись
                "hidden": bool(lockable and f["key"] in hidden_keys),
            }
            options = _dict_options.get(f["key"])
            if options:
                item["options"] = list(options)
            elif f["key"] == "type":
                item["options"] = list(type_labels_sorted)
            fields.append(item)
        groups.append({"key": g["key"], "title": g["title"], "fields": fields})
    return groups


async def get_hidden_field_keys(db, org_id: Optional[int]) -> Set[str]:
    """Множество скрытых ключей полей ТС для организации (§3).

    org_id пуст (например, суперадмин без организации) → ничего не скрыто.
    """
    if not org_id:
        return set()
    from sqlalchemy import select
    from app.models.org_section_config import OrgSectionConfig

    rows = (await db.execute(
        select(OrgSectionConfig.section_key).where(
            OrgSectionConfig.org_id == org_id,
            OrgSectionConfig.is_hidden.is_(True),
            OrgSectionConfig.section_key.like(f"{CONFIG_KEY_PREFIX}%"),
        )
    )).scalars().all()
    prefix_len = len(CONFIG_KEY_PREFIX)
    return {k[prefix_len:] for k in rows}


def get_string_column_limits() -> Dict[str, int]:
    """Лимиты длины VARCHAR/String-колонок модели Vehicle — программно, из
    SQLAlchemy-метаданных (Vehicle.__table__.columns[...].type.length), а НЕ
    переписанные вручную числа.

    Единый источник правды для:
      - app/routers/vehicles.py — валидация PATCH/POST ДО db.commit()
        (coordinator review 2026-08-31: слишком длинное строковое значение
        долетало до asyncpg и падало 500-кой с traceback в теле ответа —
        StringDataRightTruncationError на "value too long for type
        character varying(N)");
      - app/routers/vehicles_import.py — усечение при парсинге Excel (_MAX_LEN).

    Колонки без фиксированной длины (Text, JSONB, не-строковые типы) в
    словарь не попадают. Импорт Vehicle — лениво (внутри функции), чтобы не
    создавать цикл импортов на уровне модуля.
    """
    from app.models.vehicle import Vehicle

    limits: Dict[str, int] = {}
    for col_name, col in Vehicle.__table__.columns.items():
        length = getattr(col.type, "length", None)
        if isinstance(length, int):
            limits[col_name] = length
    return limits


# ─────────────────────────── §4 (2026-09): "откуда берутся данные" ───────────
#
# Владелец: «Как заполнять "История передач" — откуда она берётся? Те поля в
# карточке ТС, которые напрямую не заполняются, должны иметь комментарий, на
# основании чего формируются данные». Часть таких мест — обычные поля реестра
# (получили "source_hint" прямо в FIELD_GROUPS выше: owner_inn, operator_inn,
# current_odometer_km). Остальное — не поля, а целые ВКЛАДКИ/блоки карточки ТС,
# не входящие в FIELD_GROUPS вовсе (это отдельные relationship'ы модели Vehicle,
# каждый со своим CRUD-роутером) — они перечислены здесь и отдаются вместе с
# каталогом полей в GET /api/vehicle-fields (ключ "related_blocks"), чтобы
# фронт мог показать ту же подсказку и для них.
#
# Проверено по коду (app/routers/vehicles.py ~стр.645, app/models/vehicle_fine.py,
# app/routers/trips.py, app/routers/fuel_logs.py, app/routers/vehicle_repairs.py):
#   - next_to_km (реестр, группа "Оснащение и ТО") — ПРОВЕРЕНО и сознательно НЕ
#     включён сюда: несмотря на то, что владелец упомянул "следующее ТО" в одном
#     ряду с автоматическими полями, этот столбец пишется вручную через обычный
#     PATCH /api/vehicles (см. _PATCHABLE_FIELDS в routers/vehicles.py) — авто-
#     расчёта от last_to_mileage_km в коде нет. Помечать его как "формируется
#     автоматически" было бы неверным утверждением.
RELATED_BLOCKS: List[Dict[str, str]] = [
    {
        "key": "transfer_history",
        "title": "История передач",
        "source_hint": (
            "Формируется автоматически: новая запись создаётся при каждом сохранении "
            "карточки, если изменилась организация-собственник, организация-эксплуатант "
            "или текстовое поле «У кого в эксплуатации» (app/routers/vehicles.py, PATCH)."
        ),
    },
    {
        "key": "field_history",
        "title": "История изменений полей",
        "source_hint": (
            "Формируется автоматически: строка добавляется при каждом сохранении "
            "карточки для каждого отслеживаемого поля, если его значение изменилось "
            "(состояние, номер, VIN, топливо, нормы расхода, страховка, пробег до "
            "следующего ТО, организации, марка/модель/цвет, дата регистрации, тип)."
        ),
    },
    {
        "key": "fines",
        "title": "Штрафы",
        "source_hint": (
            "Сами штрафы вносятся вручную (по данным ГИБДД). Водитель по каждому "
            "штрафу подбирается автоматически: система ищет путевой лист этой машины "
            "на дату нарушения и берёт водителя оттуда — если путевой лист не найден, "
            "поле водителя остаётся пустым."
        ),
    },
    {
        "key": "trips",
        "title": "Путевые листы",
        "source_hint": "Ведутся вручную, отдельная вкладка карточки ТС (не часть общей формы).",
    },
    {
        "key": "repairs",
        "title": "Ремонты",
        "source_hint": "Вносятся вручную, отдельная вкладка карточки ТС (не часть общей формы).",
    },
    {
        "key": "fuel_logs",
        "title": "Заправки",
        "source_hint": (
            "Вносятся вручную, отдельная вкладка карточки ТС. Итоговая сумма заправки "
            "рассчитывается автоматически (литры × цена за литр), если сумма не введена "
            "напрямую."
        ),
    },
    {
        "key": "vehicle_passes",
        "title": "Пропуска",
        "source_hint": (
            "Отдельная сущность (не колонки карточки): произвольный набор пропусков на "
            "машину, управляется через /api/vehicle-passes (список, добавление, "
            "изменение, удаление, копирование набора с другой машины)."
        ),
    },
]


def get_related_blocks() -> List[Dict[str, str]]:
    """Список НЕ-полевых блоков карточки ТС с пояснением источника данных (§4)."""
    return list(RELATED_BLOCKS)
