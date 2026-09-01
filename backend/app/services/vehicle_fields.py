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
            {"key": "plate", "label": "Гос. рег. знак", "type": "string", "storage": "column", "required": True},
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
            {"key": "owner_inn", "label": "ИНН собственника", "type": "readonly", "storage": "computed"},
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
            {"key": "operator_inn", "label": "ИНН эксплуатанта", "type": "readonly", "storage": "computed"},
            {"key": "assignment_basis", "label": "Основание возникновения права эксплуатации", "type": "string", "storage": "column"},
            {"key": "assignment_doc_number", "label": "№ документа основания права эксплуатации", "type": "string", "storage": "column"},
            {"key": "assignment_doc_date", "label": "Дата документа основания права эксплуатации", "type": "date", "storage": "column"},
            {"key": "location_city", "label": "Место нахождения — город", "type": "string", "storage": "column"},
            {"key": "location_address", "label": "Место нахождения — адрес", "type": "string", "storage": "column"},
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
            {"key": "current_odometer_km", "label": "Текущий пробег, км", "type": "int", "storage": "column"},
            {"key": "last_to_date", "label": "Дата последнего ТО", "type": "date", "storage": "column"},
            {"key": "last_to_mileage_km", "label": "Пробег на последнем ТО", "type": "int", "storage": "column"},
            {"key": "next_to_km", "label": "Километраж следующего ТО", "type": "int", "storage": "column"},
            {"key": "tech_inspection_status", "label": "Обязательный техосмотр", "type": "string", "storage": "column"},
            {"key": "tech_inspection_last_date", "label": "Дата последнего обязательного техосмотра", "type": "date", "storage": "column"},
            {"key": "tech_inspection_until", "label": "Техосмотр действителен до", "type": "date", "storage": "column"},
        ],
    },
    {
        "key": "passes", "title": "Пропуска",
        "fields": [
            {"key": "pass_zo", "label": "Пропуск ЗО", "type": "string", "storage": "column"},
            {"key": "pass_zo_until", "label": "Дата истечения пропуска ЗО", "type": "date", "storage": "column"},
            {"key": "pass_ho", "label": "Пропуск ХО", "type": "string", "storage": "column"},
            {"key": "pass_ho_until", "label": "Дата истечения пропуска ХО", "type": "date", "storage": "column"},
            {"key": "pass_dnr", "label": "Пропуск ДНР", "type": "string", "storage": "column"},
            {"key": "pass_dnr_until", "label": "Дата истечения пропуска ДНР", "type": "date", "storage": "column"},
            {"key": "pass_lnr", "label": "Пропуск ЛНР", "type": "string", "storage": "column"},
            {"key": "pass_lnr_until", "label": "Дата истечения пропуска ЛНР", "type": "date", "storage": "column"},
            {"key": "pass_moscow", "label": "Пропуск Москва", "type": "string", "storage": "column"},
            {"key": "pass_moscow_until", "label": "Дата истечения пропуска Москва", "type": "date", "storage": "column"},
        ],
    },
    {
        "key": "equipment", "title": "Оснащение",
        "fields": [
            {"key": "tires_type", "label": "Авторезина, установленная на машине", "type": "string", "storage": "props", "props_key": "tires_type"},
            {"key": "has_spare_tires", "label": "Наличие сменной резины", "type": "bool", "storage": "column"},
            {"key": "tires_condition", "label": "Состояние резины", "type": "string", "storage": "column"},
            {"key": "has_radio", "label": "Наличие радиостанции", "type": "bool", "storage": "column"},
            {"key": "has_mirrors", "label": "Наличие зеркал", "type": "bool", "storage": "column"},
            {"key": "mirrors_ok", "label": "Исправность зеркал", "type": "bool", "storage": "column"},
            {"key": "akb_ok", "label": "Аккумулятор исправен", "type": "bool", "storage": "column"},
            {"key": "branding", "label": "Брендирование", "type": "string", "storage": "props", "props_key": "branding"},
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
    """Собрать группы полей с флагами hidden/lockable/required для ответа GET /api/vehicle-fields."""
    groups = []
    for g in FIELD_GROUPS:
        fields = []
        for f in g["fields"]:
            lockable = is_lockable(f["key"])
            fields.append({
                **f,
                "lockable": lockable,
                "required": bool(f.get("required", False)),
                # locked-поля нельзя скрыть даже если в конфиге завалялась запись
                "hidden": bool(lockable and f["key"] in hidden_keys),
            })
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
