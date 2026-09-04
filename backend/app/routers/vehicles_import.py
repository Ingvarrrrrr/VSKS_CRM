"""
vehicles_import router — Plan 29-12, Phase 29 «Имущество → Автотранспорт».

UI Excel upload + region→org mapping dialog.

Endpoints:
  POST /api/vehicles-import/preview           — parse xlsx, return preview + unmapped regions
  GET  /api/vehicles-import/preview/{sid}     — re-fetch preview by session_id
  POST /api/vehicles-import/commit            — apply region_mapping and INSERT vehicles
  GET  /api/vehicles-import/regions/unmapped  — list existing assigned_text without org

Decisions covered: D-06, D-09
"""
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_action, require_tab
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_pass import VehiclePass
from app.services.vehicle_enum_labels import (
    FUEL_TYPE_LABELS,
    TYPE_LABELS,
    label_to_code,
    resolve_vehicle_state,
)
from app.services.vehicle_fields import get_hidden_field_keys
from app.services.vehicle_import_template import build_vehicle_import_template
from app.services.vehicle_org_matching import (
    build_inn_index,
    build_name_index,
    resolve_org_for_text,
)
from app.services.vehicle_sheet_dictionaries import (
    FIELD_LABELS as _DICT_FIELD_LABELS,
    FIELD_OPTIONS as _DICT_FIELD_OPTIONS,
    NO_DATA_LABEL as _NO_DATA_LABEL,
    PASS_STATUS_OPTIONS as _PASS_STATUS_OPTIONS,
    is_no_data_text,
    match_dictionary_value,
    match_value_in_options,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vehicles-import", tags=["vehicles-import"])

# ─────────────────────────── In-memory session store ────────────────────────

_IMPORT_SESSIONS: Dict[str, dict] = {}
_SESSION_TTL = timedelta(minutes=30)


def _cleanup_old_sessions() -> None:
    """Remove sessions older than TTL and delete their tmp files."""
    cutoff = datetime.now(timezone.utc) - _SESSION_TTL
    expired = [sid for sid, s in _IMPORT_SESSIONS.items() if s["created_at"] < cutoff]
    for sid in expired:
        tmp = _IMPORT_SESSIONS[sid].get("tmp_path")
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        del _IMPORT_SESSIONS[sid]


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


def _coerce_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("1", "да", "yes", "true", "+", "есть", "имеется", "имеются", "исправно", "имеются в наличии"):
        return True
    if s in ("0", "нет", "no", "false", "-", "отсутствует", "отсуствует", "неисправно"):  # "отсуствует" — опечатка исходника
        return False
    return None


def _coerce_repair_required(val: Any) -> Optional[bool]:
    """Требуется ремонт: реальные данные — не "да/нет", а текст описания
    неисправности ("Необходим кузовной ремонт" и т.п.). Presence-эвристика:
    известное да/нет-слово имеет приоритет, иначе непустой текст = True."""
    if val is None:
        return None
    known = _coerce_bool(val)
    if known is not None:
        return known
    return bool(str(val).strip())


def _coerce_pts_kind(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s.startswith("бумаж"):
        return "paper"
    if s.startswith("электрон"):
        return "electronic"
    return None


# Обратное сопоставление подпись→код для полей типа/топлива (Автоблок:
# «шаблон импорта транспорта»). Раньше эти поля попадали в общий "else"-текстовый
# путь и сохранялись как есть — если бы пользователь выбрал русскую подпись из
# выпадающего списка шаблона ("Легковой"), в БД лёг бы сырой текст вместо кода
# ("car_light"), которого ждут фильтры/экспорт (_EXPORT_TYPE_LABEL и т.п. в
# vehicles.py). label_to_code регистронезависим и не блокирует нестандартный
# ввод — если подпись не распознана, возвращает исходный текст как есть.
#
# "state" сюда НЕ входит — у него отдельная, более строгая коэрсия
# (см. _coerce_state_value / resolve_vehicle_state в vehicle_enum_labels.py):
# в отличие от type/fuel_type, для state сырой нераспознанный текст никогда
# не должен попадать в колонку (Lesson 2026-08-31: "В надлежайщем состоя" —
# обрезанный по VARCHAR(20) сырой текст с опечаткой исходника, не совпадающий
# ни с одним кодом; карточка ТС показывала «Неизвестно», фильтр не находил).
_ENUM_LABEL_FIELDS = {
    "type": TYPE_LABELS,
    "fuel_type": FUEL_TYPE_LABELS,
}


def _coerce_enum_label(field: str, val: Any) -> Optional[str]:
    labels = _ENUM_LABEL_FIELDS[field]
    coerced = label_to_code(labels, val)
    max_len = _MAX_LEN.get(field)
    if coerced and max_len:
        coerced = coerced[:max_len]
    return coerced


def _coerce_state_value(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """Состояние ТС: НИКОГДА не пишет сырой текст в state (в отличие от
    _coerce_enum_label выше) — только один из 6 кодов STATE_LABELS либо None.
    Возвращает (код, заметка_для_tech_condition_info | None); заметка
    непустая, если текст не распознан целиком, либо содержит доп. сведения
    в скобках (место, а не состояние) — см. resolve_vehicle_state()."""
    return resolve_vehicle_state(val)


def _coerce_date(val: Any) -> Optional[str]:
    """Return ISO date string or None."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


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


def _split_brand_model(val: str) -> tuple[Optional[str], Optional[str]]:
    """«CFMOTO CFORCE 600 EPS» → ('CFMOTO', 'CFORCE 600 EPS') — по первому пробелу (§6)."""
    s = val.strip()
    if not s:
        return None, None
    parts = s.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _parse_xlsx_to_rows(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse xlsx bytes into list of row-dicts and list of warnings.

    Returns (rows, warnings). rows: list of dicts with Vehicle field names
    (плюс вложенный "props" dict для props-хранимых полей, см. _PROPS_KEYS).
    """
    try:
        from openpyxl import load_workbook as _lw
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail={"msg": "openpyxl не установлен на сервере", "code": "openpyxl_missing"},
        )

    wb = _lw(BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    # Find header row (first non-empty row)
    header_raw: Optional[tuple] = None
    header_row_idx = 0
    for idx, row in enumerate(rows_iter, start=1):
        if any(c is not None for c in row):
            header_raw = row
            header_row_idx = idx
            break

    if header_raw is None:
        return [], ["Файл не содержит данных"]

    # Build col_index → field_name mapping (позиционное разрешение неоднозначных
    # заголовков + occupied-tracking дублей, см. _resolve_header_columns).
    col_field, _unresolved_headers = _resolve_header_columns(header_raw)

    # Исходный текст заголовка по индексу колонки — для предупреждений о нераспознанных
    # значениях (coordinator review 2026-08-31): пользователь должен видеть, В КАКОЙ
    # колонке потерялось значение, а не только номер строки.
    col_header_label: Dict[int, str] = {
        ci: str(cell).strip() for ci, cell in enumerate(header_raw) if cell is not None
    }

    parsed_rows: list[dict] = []
    warnings: list[str] = []
    row_n = header_row_idx

    for raw_row in rows_iter:
        row_n += 1
        if all(c is None for c in raw_row):
            continue  # skip fully empty rows

        row_data: dict[str, Any] = {"_row_n": row_n}
        props_data: dict[str, Any] = {}
        passes_data: dict[str, dict[str, Any]] = {}
        state_note: Optional[str] = None
        dict_notes: list[str] = []

        for ci, field in col_field.items():
            val = raw_row[ci] if ci < len(raw_row) else None

            if val is not None and is_no_data_text(val):
                # «Нет данных» — осознанный ответ пользователя о том, что поле
                # не заполнено (см. vehicle_sheet_dictionaries.NO_DATA_LABEL,
                # прямое распоряжение владельца 2026-09: пустых ячеек в файле
                # быть не должно, вместо пустоты — «Нет данных»). Раньше это
                # распознавалось только для полей со справочником
                # (_DICT_STRING_FIELDS/_DICT_BOOL_FIELDS/pts_category/state) —
                # текстовые/числовые/датовые/булевы колонки без справочника
                # получали сырую строку "Нет данных" в поле (текст) либо
                # ошибочно интерпретировались (repair_required через
                # bool(str(val).strip()) считал "Нет данных" за True; сборный
                # "Марка и модель ТС" резал бы её на "Нет"/"данных"). Проверка
                # здесь, ДО диспетчеризации по типу поля, закрывает все ветки
                # разом: колонка трактуется как полностью пустая — ничего не
                # пишем, warning не поднимаем, props.note не трогаем.
                continue

            if isinstance(field, str) and field.startswith(_PASS_STATUS_MARK):
                # 2026-09: пропуск с произвольным названием → таблица vehicle_passes,
                # не колонка Vehicle (см. блок констант выше _resolve_header_columns).
                name = field[len(_PASS_STATUS_MARK):]
                matched = match_value_in_options(_PASS_STATUS_OPTIONS, val)
                if matched == _NO_DATA_LABEL:
                    pass
                elif matched is not None:
                    passes_data.setdefault(name, {})["status"] = matched
                elif val is not None and str(val).strip():
                    raw_text_v = str(val).strip()
                    warnings.append(
                        f"Строка {row_n}: «Пропуск: {name}» — значение «{raw_text_v}» не входит в "
                        f"список допустимых (Да/Нет/Не требуется/Не выпускался), статус не сохранён"
                    )
                continue

            if isinstance(field, str) and field.startswith(_PASS_UNTIL_MARK):
                name = field[len(_PASS_UNTIL_MARK):]
                coerced_date = _coerce_date(val)
                if coerced_date is not None:
                    passes_data.setdefault(name, {})["until"] = coerced_date
                elif val is not None and str(val).strip():
                    warnings.append(
                        f"Строка {row_n}: «Пропуск: {name} — до» — значение «{str(val).strip()}» "
                        f"не распознано как дата"
                    )
                continue

            if field == _BRAND_MODEL_SPLIT_FIELD:
                if val is not None and str(val).strip():
                    brand, model = _split_brand_model(str(val))
                    # Не перезаписываем, если отдельные колонки "Марка"/"Модель" уже есть
                    row_data.setdefault("brand", brand)
                    row_data.setdefault("model", model)
                continue

            if field == _REPAIR_REQUIRED_FIELD:
                row_data[field] = _coerce_repair_required(val)
                continue

            if field == "pts_kind":
                row_data[field] = _coerce_pts_kind(val)
                continue

            if field == "state":
                state_code, note = _coerce_state_value(val)
                row_data["state"] = state_code
                if (
                    state_code is None
                    and val is not None
                    and str(val).strip()
                    and not is_no_data_text(val)
                ):
                    # «Нет данных» (см. is_no_data_text) сюда не попадает — это
                    # осознанный ответ «пусто», а не нераспознанный текст,
                    # предупреждение/флаг для него не нужны (resolve_vehicle_state
                    # уже вернул note=None для этого случая, см. выше).
                    #
                    # Помечаем строку: значение было (не пустая ячейка), но не
                    # распозналось. Отличаем от случая "ячейка вообще пустая"
                    # (там row_data["state"] тоже None, но флага нет) — см.
                    # commit_import: только помеченные строки требуют
                    # пост-INSERT UPDATE state=NULL, иначе ORM Column
                    # default="working" молча подставит "Рабочее" вместо
                    # честной пустоты (Lesson 2026-08-31: default в
                    # SQLAlchemy срабатывает на explicit None точно так же,
                    # как на отсутствие атрибута — простое fields[f]=None
                    # его не подавляет, нужен отдельный UPDATE после flush).
                    row_data["_state_unrecognized"] = True
                    warnings.append(
                        f"Строка {row_n}: состояние «{str(val).strip()}» не распознано, "
                        f"поле «Состояние» оставлено пустым (исходный текст сохранён в "
                        f"«Сведения о техническом состоянии»)"
                    )
                if note:
                    state_note = note
                continue

            if field in _ENUM_LABEL_FIELDS:
                row_data[field] = _coerce_enum_label(field, val)
                continue

            target_dict = props_data if field in _PROPS_KEYS else row_data

            if field in _DICT_STRING_FIELDS:
                # Автоблок (актуализация 2026-08-31): поле ограничено набором
                # значений из правил проверки данных листа владельца (см.
                # vehicle_sheet_dictionaries.py). Несопоставленное значение НЕ
                # пишется в колонку — исходный текст уходит в предупреждение и
                # в props.note, чтобы не потерялся молча.
                #
                # Актуализация (2026-09, распоряжение владельца): «Нет данных» —
                # ОСОЗНАННЫЙ ответ пользователя, а не несопоставленный текст.
                # match_dictionary_value сопоставит его один-в-один (входит в
                # набор наравне с остальными вариантами), но значение "Нет
                # данных" в колонку не пишем, предупреждение не поднимаем и
                # props.note не засоряем — просто оставляем поле пустым.
                matched = match_dictionary_value(field, val)
                if matched is not None and matched != _NO_DATA_LABEL:
                    target_dict[field] = matched
                elif matched is None and val is not None and str(val).strip():
                    raw_text = str(val).strip()
                    label = col_header_label.get(ci, _DICT_FIELD_LABELS.get(field, field))
                    warnings.append(
                        f"Строка {row_n}: «{label}» — значение «{raw_text}» не входит в "
                        f"список допустимых, поле оставлено пустым (исходный текст "
                        f"сохранён в «Примечание»)"
                    )
                    dict_notes.append(f"{label} из файла: {raw_text}")
                continue

            if field in _DICT_BOOL_FIELDS:
                # Тот же справочник допустимых значений (Да/Нет/Нет данных), но
                # хранится bool-колонкой — сопоставляем через тот же
                # match_dictionary_value, а не через грубый _coerce_bool, чтобы
                # «Нет данных» отличался от текста, который вообще не входит в
                # список допустимых (тому положено предупреждение, этому — нет).
                matched = match_dictionary_value(field, val)
                if matched == _NO_DATA_LABEL:
                    target_dict[field] = None
                elif matched is not None:
                    target_dict[field] = (matched == "Да")
                else:
                    coerced_bool = _coerce_bool(val)
                    target_dict[field] = coerced_bool
                    if coerced_bool is None and val is not None and str(val).strip():
                        raw_text = str(val).strip()
                        label = col_header_label.get(ci, _DICT_FIELD_LABELS.get(field, field))
                        warnings.append(
                            f"Строка {row_n}: «{label}» — значение «{raw_text}» не входит в "
                            f"список допустимых (Да/Нет), поле оставлено пустым (исходный "
                            f"текст сохранён в «Примечание»)"
                        )
                        dict_notes.append(f"{label} из файла: {raw_text}")
                continue

            if field == "pts_category":
                # Категория ТС по ПТС — свободный текст (значения A/B/BE/.../Tm
                # в шаблоне лишь подсказка, showErrorMessage=False), поэтому у
                # него нет отдельной функции-коэрсера вроде label_to_code —
                # «Нет данных» перехватываем прямо здесь: не пишем в колонку,
                # без warning'а (см. распоряжение владельца 2026-09, тот же
                # принцип, что и для остальных полей со списком).
                if val is not None and is_no_data_text(val):
                    target_dict[field] = None
                else:
                    text_val = str(val).strip() if val is not None else None
                    max_len = _MAX_LEN.get(field)
                    if text_val and max_len:
                        text_val = text_val[:max_len]
                    target_dict[field] = text_val
                continue

            if field in _BOOL_COLS:
                target_dict[field] = _coerce_bool(val)
            elif field in _DATE_COLS:
                coerced_date = _coerce_date(val)
                if coerced_date is None and val is not None and str(val).strip():
                    label = col_header_label.get(ci, field)
                    warnings.append(
                        f"Строка {row_n}: «{label}» — значение «{str(val).strip()}» "
                        f"не распознано как дата, поле оставлено пустым"
                    )
                target_dict[field] = coerced_date
            elif field in _FLOAT_COLS:
                try:
                    target_dict[field] = float(val) if val is not None else None
                except (TypeError, ValueError):
                    target_dict[field] = None
            elif field in _INT_COLS:
                try:
                    target_dict[field] = int(float(val)) if val is not None else None
                except (TypeError, ValueError):
                    target_dict[field] = None
            else:
                text_val = str(val).strip() if val is not None else None
                max_len = _MAX_LEN.get(field)
                if text_val and max_len:
                    text_val = text_val[:max_len]
                target_dict[field] = text_val

        # Домержить заметку о состоянии (нераспознанный текст либо доп.
        # сведения в скобках вроде "(г.Ростов-на-Дону)" — место, а не
        # состояние) в tech_condition_info, НЕ перезаписывая то, что там уже
        # лежит из одноимённой колонки файла («Сведения о техническом
        # состоянии» — своя колонка, обрабатывается в общей ветке выше и
        # могла успеть записаться в row_data до или после колонки
        # «Состояние» в зависимости от порядка столбцов, поэтому мерж всегда
        # делаем постфактум, после полного прохода по колонкам строки).
        if state_note:
            existing_tci = (row_data.get("tech_condition_info") or "").strip()
            if state_note not in existing_tci:
                row_data["tech_condition_info"] = (
                    f"{existing_tci}; {state_note}" if existing_tci else state_note
                )
                max_len = _MAX_LEN.get("tech_condition_info")
                if max_len:
                    row_data["tech_condition_info"] = row_data["tech_condition_info"][:max_len]

        # Домержить исходные тексты несопоставленных значений справочника
        # (см. _DICT_STRING_FIELDS/_DICT_BOOL_FIELDS выше) в props.note — та же
        # логика "не перезаписывать уже занесённое", что и для state_note выше,
        # но целится в props (JSONB), а не в колонку tech_condition_info.
        if dict_notes:
            existing_note = (props_data.get("note") or "").strip()
            new_parts = [n for n in dict_notes if n not in existing_note]
            if new_parts:
                props_data["note"] = "; ".join(([existing_note] if existing_note else []) + new_parts)

        if props_data:
            row_data["props"] = props_data

        if passes_data:
            row_data["passes"] = passes_data

        # Пункт 6 задания (2026-09): дата документа основания права эксплуатации
        # не может быть раньше даты документа основания права собственности.
        # Импорт — не блокирует строку (владелец потребовал явно: "строка не
        # теряется"), только предупреждение в тот же канал warnings, что и
        # остальные проблемы разбора; обе даты уже сохраняются как есть.
        _own_date = row_data.get("ownership_doc_date")
        _assign_date = row_data.get("assignment_doc_date")
        if _own_date and _assign_date and _assign_date < _own_date:
            warnings.append(
                f"Строка {row_n}: дата документа основания права эксплуатации "
                f"({_assign_date}) раньше даты документа основания права "
                f"собственности ({_own_date}) — проверьте, обе даты сохранены как есть"
            )

        # plate is mandatory
        plate = row_data.get("plate")
        if not plate:
            warnings.append(f"Строка {row_n}: госномер отсутствует, пропущена")
            row_data["_skip"] = True

        parsed_rows.append(row_data)

    wb.close()
    return parsed_rows, warnings


# ─────────────────────────── Org lookup cache ────────────────────────────────
#
# Сопоставление организации-собственника/эксплуатанта — ИНН приоритетнее
# названия (app.services.vehicle_org_matching, не дублируем логику здесь).

async def _apply_row_passes(db: AsyncSession, vehicle_id: int, row_passes: Dict[str, dict]) -> None:
    """Записать пропуска строки импорта в vehicle_passes (2026-09).

    Upsert по (vehicle_id, name): существующий пропуск с тем же именем
    обновляется (status/expires_at — только те поля, что реально пришли в
    строке файла, остальное не трогаем), новый — создаётся. Данные и статус,
    и "до" могут прийти из РАЗНЫХ колонок файла — row_passes[name] мержит их
    заранее в _parse_xlsx_to_rows.
    """
    for name, pdata in row_passes.items():
        status = pdata.get("status")
        until_str = pdata.get("until")
        until_date = None
        if isinstance(until_str, str) and until_str:
            try:
                until_date = datetime.strptime(until_str, "%Y-%m-%d").date()
            except ValueError:
                until_date = None

        existing_pass = (await db.execute(
            select(VehiclePass).where(VehiclePass.vehicle_id == vehicle_id, VehiclePass.name == name)
        )).scalar_one_or_none()

        if existing_pass is None:
            db.add(VehiclePass(vehicle_id=vehicle_id, name=name, status=status, expires_at=until_date))
        else:
            if status is not None:
                existing_pass.status = status
            if until_date is not None:
                existing_pass.expires_at = until_date


async def _build_org_indexes(db: AsyncSession) -> tuple[Dict[str, int], Dict[str, int]]:
    """Возвращает (inn_index, name_index) по всем организациям в БД."""
    result = await db.execute(select(Organization.id, Organization.name, Organization.inn))
    org_rows = [(row.id, row.name, row.inn) for row in result.all()]
    return build_inn_index(org_rows), build_name_index(org_rows)


def _classify_rows_by_org(
    valid_rows: list[dict],
    text_key: str,
    inn_key: str,
    inn_index: Dict[str, int],
    name_index: Dict[str, int],
) -> tuple[Dict[str, dict], list[dict]]:
    """Группирует строки по значению text_key и определяет org_id (ИНН → название).

    Возвращает (matched, unmapped):
      matched  — {raw_text: {"raw_text", "org_id", "org_name" (== raw_text отображаемо), "method"}}
      unmapped — [{"raw_text", "occurrences"}] — то, что не сопоставилось ни по
                 ИНН, ни по названию; строка ОБЯЗАНА попасть сюда, а не
                 получить организацию по умолчанию молча.
    """
    counter: Dict[str, int] = {}
    matched: Dict[str, dict] = {}
    for row in valid_rows:
        txt = row.get(text_key) or ""
        if not txt:
            continue
        counter[txt] = counter.get(txt, 0) + 1
        if txt not in matched:
            org_id, method = resolve_org_for_text(txt, row.get(inn_key), inn_index, name_index)
            if org_id is not None:
                matched[txt] = {"raw_text": txt, "org_id": org_id, "org_name": txt, "method": method}

    unmapped = [
        {"raw_text": txt, "occurrences": cnt}
        for txt, cnt in counter.items()
        if txt not in matched
    ]
    return matched, unmapped


def _build_preview_payload(
    parsed_rows: list[dict],
    inn_index: Dict[str, int],
    name_index: Dict[str, int],
) -> dict:
    """Общая сборка ответа preview — переиспользуется POST /preview и GET /preview/{sid},
    чтобы не разъезжаться логикой (было продублировано до правки)."""
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]
    invalid_rows = [r for r in parsed_rows if r.get("_skip")]

    matched_owners, unmapped_owners = _classify_rows_by_org(
        valid_rows, "owner_text", "owner_inn", inn_index, name_index
    )
    matched_orgs, unmapped_regions = _classify_rows_by_org(
        valid_rows, "assigned_text", "assigned_inn", inn_index, name_index
    )

    preview_items = []
    for row in valid_rows[:10]:
        owner_txt = row.get("owner_text") or ""
        assigned_txt = row.get("assigned_text") or ""
        owner_match = matched_owners.get(owner_txt)
        assigned_match = matched_orgs.get(assigned_txt)
        preview_items.append({
            "row_n": row["_row_n"],
            "plate": row.get("plate"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "owner_text": row.get("owner_text"),
            "owner_org_id": owner_match["org_id"] if owner_match else None,
            "owner_match_method": owner_match["method"] if owner_match else None,
            "assigned_text": row.get("assigned_text"),
            "assigned_org_id": assigned_match["org_id"] if assigned_match else None,
            "assigned_match_method": assigned_match["method"] if assigned_match else None,
            "type": row.get("type"),
            "state": row.get("state"),
            "fuel_type": row.get("fuel_type"),
        })

    def _stats(matched: Dict[str, dict]) -> dict:
        return {
            "matched_by_inn": sum(1 for m in matched.values() if m["method"] == "inn"),
            "matched_by_name": sum(1 for m in matched.values() if m["method"] == "name"),
        }

    return {
        "rows_total": len(parsed_rows),
        "rows_valid": len(valid_rows),
        "rows_invalid": len(invalid_rows),
        "unmapped_regions": unmapped_regions,
        "matched_orgs": list(matched_orgs.values()),
        "unmapped_owners": unmapped_owners,
        "matched_owners": list(matched_owners.values()),
        "owner_stats": _stats(matched_owners),
        "assigned_stats": _stats(matched_orgs),
        "preview_items": preview_items,
    }


# ─────────────────────────── POST /preview ───────────────────────────────────

@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Parse uploaded xlsx, return preview + unmapped region list."""
    _cleanup_old_sessions()

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail={"msg": "Ожидается файл .xlsx", "code": "bad_extension"},
        )

    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=422,
            detail={"msg": "Файл пустой", "code": "empty_file"},
        )

    # Save to temp file (needed for commit step)
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    try:
        tmp_file.write(raw_bytes)
        tmp_file.flush()
        tmp_path = tmp_file.name
    finally:
        tmp_file.close()

    parsed_rows, warnings = _parse_xlsx_to_rows(raw_bytes)
    inn_index, name_index = await _build_org_indexes(db)

    session_id = str(uuid.uuid4())
    _IMPORT_SESSIONS[session_id] = {
        "tmp_path": tmp_path,
        "created_at": datetime.now(timezone.utc),
        "parsed_rows": parsed_rows,
        "user_id": current_user.id,
    }

    payload = _build_preview_payload(parsed_rows, inn_index, name_index)
    payload["session_id"] = session_id
    payload["warnings"] = warnings
    return payload


# ─────────────────────────── GET /preview/{session_id} ───────────────────────

@router.get("/preview/{session_id}")
async def get_preview(
    session_id: str,
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Re-fetch preview data for an existing session."""
    _cleanup_old_sessions()
    session = _IMPORT_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"msg": "Сессия не найдена или истекла (30 мин)", "code": "session_not_found"},
        )
    if session["user_id"] != current_user.id and current_user.role not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"msg": "Сессия принадлежит другому пользователю", "code": "session_forbidden"},
        )

    inn_index, name_index = await _build_org_indexes(db)
    parsed_rows = session["parsed_rows"]

    payload = _build_preview_payload(parsed_rows, inn_index, name_index)
    payload["session_id"] = session_id
    return payload


# ─────────────────────────── POST /commit ────────────────────────────────────

class CommitBody(BaseModel):
    session_id: str
    region_mapping: Dict[str, int] = {}          # assigned_text → org_id
    owner_mapping: Dict[str, int] = {}           # owner_text → org_id
    default_owner_org_id: Optional[int] = None   # fallback owner org
    conflict_strategy: str = "skip"              # "skip" | "update"


@router.post("/commit")
async def commit_import(
    body: CommitBody,
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Apply region_mapping and insert/update vehicles from session."""
    _cleanup_old_sessions()

    session = _IMPORT_SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"msg": "Сессия не найдена или истекла (30 мин)", "code": "session_not_found"},
        )
    if session["user_id"] != current_user.id and current_user.role not in ("superadmin", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"msg": "Сессия принадлежит другому пользователю", "code": "session_forbidden"},
        )

    if body.conflict_strategy not in ("skip", "update"):
        raise HTTPException(
            status_code=422,
            detail={"msg": "conflict_strategy должна быть 'skip' или 'update'", "code": "bad_strategy"},
        )

    inn_index, name_index = await _build_org_indexes(db)
    parsed_rows = session["parsed_rows"]
    valid_rows = [r for r in parsed_rows if not r.get("_skip")]

    # Merge region_mapping with auto-detected org matches
    combined_region_map: Dict[str, int] = dict(body.region_mapping)
    combined_owner_map: Dict[str, int] = dict(body.owner_mapping)

    inserted = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    # Строки с row["_state_unrecognized"] (см. _parse_xlsx_to_rows) требуют
    # ПОСТ-INSERT коррекции state=NULL: Vehicle.state объявлен с client-side
    # Column(default="working") — SQLAlchemy применяет такой default, если
    # резолвленное значение колонки на момент flush есть None, ВНЕ
    # зависимости от того, было ли оно явно присвоено или атрибут вовсе не
    # трогали (see Lesson 2026-08-31: простое fields["state"]=None не
    # помогает, INSERT всё равно уйдёт со state='working'). default
    # срабатывает только на INSERT, не на UPDATE — поэтому для новых записей
    # object добавляется в pending_null_state и получает "state = None"
    # ПОСЛЕ первого flush (когда INSERT уже прошёл с дефолтом), что уходит
    # отдельным UPDATE. Для уже существующих (conflict_strategy="update")
    # объект persistent и default не участвует — присваиваем сразу.
    pending_null_state: list[Vehicle] = []
    # 2026-09: (vehicle, row["passes"]) для строк, где найдены колонки "Пропуск: ...".
    # Обрабатываются ПОСЛЕ основного цикла (см. _apply_row_passes ниже) — для новых
    # машин vehicle.id появляется только после db.flush().
    pending_passes: list[tuple[Vehicle, dict]] = []

    _VEHICLE_FIELDS = {
        "brand", "model", "color", "vin", "plate", "type", "state",
        "fuel_type", "fuel_norm_summer", "fuel_norm_winter", "next_to_km",
        "has_tracker", "akb_ok", "has_radio", "mirrors_ok",
        "has_keys", "has_first_aid_kit", "has_spare_wheel", "has_extinguisher",
        "registered_at", "insurance_until",
        # Автоблок: полный реестр полей ТС (AUTOBLOCK_FIELDS_SPEC.md §1) —
        # только "column"-хранимые; props-хранимые (_PROPS_KEYS) собираются
        # отдельно в row["props"] и мержатся в vehicles.props ниже.
        "year_of_manufacture", "last_to_mileage_km", "last_to_date",
        "pts_number", "sts_number", "tech_inspection_until", "purchase_info",
        "assignment_basis", "assignment_doc_number", "assignment_doc_date",
        "engine_power_hp", "engine_volume_l",
        "body_type", "pts_category",
        "insurance_company", "insurance_policy_number",
        "ownership_basis", "ownership_doc_number", "ownership_doc_date", "owner_since",
        "location_city", "location_address", "home_base_city", "responsible_name",
        "pts_kind", "sts_issued_at",
        "tech_inspection_status", "tech_inspection_last_date",
        # 2026-09: pass_* убраны — единственный источник правды теперь
        # vehicle_passes (см. row["passes"] / _apply_row_passes ниже).
        "has_spare_tires", "tires_condition", "has_mirrors",
        "first_aid_kit_until", "extinguisher_check_date", "tracker_paid_until",
        "has_tachograph", "tachograph_check_date",
        "repair_required", "tech_condition_info",
        "current_odometer_km",
        # 2026-09: брендирование — признак + резина по сезонным комплектам
        "has_branding",
        "tires_summer_radius", "tires_summer_profile", "tires_summer_condition",
        "tires_winter_radius", "tires_winter_profile", "tires_winter_condition",
    }

    # Автоблок: полный набор date-полей (для конвертации ISO-строки → date).
    # Тот же реестр-производный набор, что и _DATE_COLS модуля — единый источник
    # правды, чтобы не разъезжаться руками (см. _load_date_columns_from_registry).
    _ALL_DATE_FIELDS = _DATE_COLS

    for row in valid_rows:
        plate = row.get("plate")
        row_n = row.get("_row_n", "?")

        try:
            # Resolve owner_org_id: приоритет — ручной выбор пользователя из
            # диалога (owner_mapping, для строк, которые не сопоставились
            # автоматически), затем автоопределение по ИНН/названию. НИКОГДА
            # не подставляем организацию текущего пользователя молча — если
            # ничего не подошло и default_owner_org_id не задан явно, строка
            # уходит в errors (владелец должен доопределить её в диалоге).
            owner_text = row.get("owner_text") or ""
            auto_owner_id, _owner_method = resolve_org_for_text(
                owner_text, row.get("owner_inn"), inn_index, name_index
            )
            owner_org_id: Optional[int] = (
                combined_owner_map.get(owner_text)
                or auto_owner_id
                or body.default_owner_org_id
            )
            if owner_org_id is None:
                errors.append({
                    "row": row_n, "plate": plate,
                    "msg": f"Организация-собственник не определена для «{owner_text or '(пусто)'}» — сопоставьте вручную",
                })
                continue

            # Resolve assigned_org_id — та же логика (ИНН приоритетнее названия),
            # но None допустим (assigned_org_id nullable, остаётся текстовый fallback).
            assigned_text = row.get("assigned_text") or ""
            auto_assigned_id, _assigned_method = resolve_org_for_text(
                assigned_text, row.get("assigned_inn"), inn_index, name_index
            )
            assigned_org_id: Optional[int] = (
                combined_region_map.get(assigned_text)
                or auto_assigned_id
            )

            # Build field dict for Vehicle
            fields: dict[str, Any] = {}
            for f in _VEHICLE_FIELDS:
                val = row.get(f)
                if val is not None:
                    fields[f] = val

            fields["owner_org_id"] = owner_org_id
            fields["assigned_org_id"] = assigned_org_id
            fields["assigned_text"] = assigned_text if assigned_text else None

            # Convert date strings to date objects
            for dcol in _ALL_DATE_FIELDS:
                v = fields.get(dcol)
                if isinstance(v, str) and v:
                    try:
                        from datetime import datetime as _dt
                        fields[dcol] = _dt.strptime(v, "%Y-%m-%d").date()
                    except ValueError:
                        fields.pop(dcol, None)

            # props-хранимые поля (Автоблок §2: tires_type/branding/paint_condition/
            # defect_description/note) — собраны парсером в row["props"], сюда не входят
            # через _VEHICLE_FIELDS (это не колонки Vehicle).
            row_props: dict = row.get("props") or {}

            # Check existing
            existing_result = await db.execute(
                select(Vehicle).where(Vehicle.plate == plate)
            )
            existing: Optional[Vehicle] = existing_result.scalar_one_or_none()

            row_passes: dict = row.get("passes") or {}

            if existing is None:
                if row_props:
                    fields["props"] = row_props
                vehicle = Vehicle(**fields)
                db.add(vehicle)
                inserted += 1
                if row.get("_state_unrecognized"):
                    pending_null_state.append(vehicle)
                if row_passes:
                    pending_passes.append((vehicle, row_passes))
            elif body.conflict_strategy == "update":
                for k, v in fields.items():
                    setattr(existing, k, v)
                if row_props:
                    from sqlalchemy.orm.attributes import flag_modified
                    existing.props = {**(existing.props or {}), **row_props}
                    flag_modified(existing, "props")
                if row.get("_state_unrecognized"):
                    # existing — persistent объект, default тут не участвует
                    # (default применяется только на INSERT) — прямое
                    # присваивание сразу даст корректный UPDATE ... SET state=NULL.
                    existing.state = None
                updated += 1
                if row_passes:
                    pending_passes.append((existing, row_passes))
            else:
                skipped += 1

        except Exception as exc:
            logger.exception("vehicles_import commit row %s error", row_n)
            errors.append({"row": row_n, "plate": plate, "msg": str(exc)})

    if pending_null_state or pending_passes:
        # Первый flush проводит INSERT'ы (Column default="working" неизбежно
        # сработает для этих объектов, плюс новым Vehicle нужен id для FK
        # vehicle_passes.vehicle_id); затем перезаписываем state=None на уже
        # persistent объектах — это уходит отдельным UPDATE, default на него
        # не влияет (см. комментарий у объявления pending_null_state выше).
        await db.flush()
        for vehicle in pending_null_state:
            vehicle.state = None
        for vehicle, row_passes in pending_passes:
            await _apply_row_passes(db, vehicle.id, row_passes)

    await db.commit()

    # Cleanup
    tmp_path = session.get("tmp_path")
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    _IMPORT_SESSIONS.pop(body.session_id, None)

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(valid_rows),
    }


# ─────────────────────────── GET /regions/unmapped ───────────────────────────

@router.get("/regions/unmapped")
async def get_unmapped_regions(
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """List unique assigned_text values without a resolved assigned_org_id."""
    result = await db.execute(
        select(Vehicle.assigned_text)
        .where(
            Vehicle.assigned_text.isnot(None),
            Vehicle.assigned_text != "",
            Vehicle.assigned_org_id.is_(None),
        )
        .distinct()
        .order_by(Vehicle.assigned_text)
    )
    rows = result.scalars().all()
    return {"unmapped_regions": [{"raw_text": r} for r in rows], "count": len(rows)}


# ─────────────────────── GET /api/vehicles/import-template ──────────────────
#
# Отдельный router с prefix="/api/vehicles" (а не "/api/vehicles-import" как у
# основного router этого файла) — так просил владелец задания: путь должен
# жить рядом с остальными /api/vehicles/* эндпоинтами. Регистрируется в
# app/__init__.py ДО vehicles.router — иначе его перехватил бы catch-all
# GET /api/vehicles/{vehicle_id} (там нет `:int`-констрейнта на путь).

vehicles_template_router = APIRouter(prefix="/api/vehicles", tags=["vehicles-import"])


@vehicles_template_router.get("/import-template")
async def download_vehicle_import_template(
    current_user: User = Depends(require_action("vehicle.import")),
    db: AsyncSession = Depends(get_db),
):
    """Скачать шаблон Excel для импорта реестра транспорта (лист «Транспорт» +
    «Инструкция» + «Справочники»). Состав колонок — реестр services/vehicle_fields.py
    за вычетом полей, скрытых для организации текущего пользователя."""
    from fastapi.responses import StreamingResponse

    hidden_keys = await get_hidden_field_keys(db, current_user.org_id)
    try:
        buf = build_vehicle_import_template(hidden_keys)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{_url_quote('Шаблон_импорта_транспорта.xlsx', safe='-_.~')}"
            )
        },
    )
