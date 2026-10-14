# -*- coding: utf-8 -*-
"""Страж (14.10.2026, обход всех backend/templates/*.docx): для каждого docx
корневые Jinja-переменные ({{x}}, {{x.y}}, {% if x %}, {% for a in x %}) обязаны
быть известны — либо описаны в TEMPLATE_VARIABLES (template_variables.py,
единственный справочник подставляемых переменных), либо служебные циклов,
либо явно в allowlist ниже с причиной.

Повод: обход 14.10.2026 нашёл {% if doc_kind == '...' %} в четырёх
service_note_*.docx — переменная была в разметке, но никогда не клалась в
контекст (см. test_fabrikant_contexts_single_source.py::
test_doc_kind_derived_from_service_note_doc_type — фикс в
contexts_build.py::build_base_context_part1). Этот тест не даёт повторить
ту же ошибку молча: новая переменная в разметке шаблона без значения в
контексте и без записи в allowlist теперь валит сборку.

Запускать внутри контейнера (python-docx/docxtpl только там, backend/templates
смонтирован по тому же пути) — как и смежный test_template_variables_complete.py.
"""
import os
import re

import pytest

from app.services.documents.template_variables import TEMPLATE_VARIABLES

TEMPLATES_DIR = "/app/templates"

# Служебные переменные ВНУТРИ jinja-циклов (for item in items, for a in
# approvers, for r in receipts, for l in item.menu_lines, for m in
# commission_members) — не самостоятельные ключи контекста.
_LOOP_VARS = {"item", "a", "r", "img", "l", "m", "loop"}

_JINJA_NOISE = {
    "if", "for", "in", "endfor", "endif", "else", "elif", "not", "and", "or",
    "is", "none", "true", "false", "tr", "p", "endtr", "endp",
}


def _extract_roots(template_var_markup: str) -> set[str]:
    """Корневые идентификаторы из одной строки колонки template_var
    TEMPLATE_VARIABLES — поддерживает {{x}}, {{x.y}}, {% if x ... %},
    {% for a in x %}."""
    roots: set[str] = set()
    for m in re.finditer(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)", template_var_markup):
        roots.add(m.group(1))
    for m in re.finditer(r"for\s+[a-zA-Z_]\w*\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)", template_var_markup):
        roots.add(m.group(1))
    for m in re.finditer(r"if\s+([a-zA-Z_][a-zA-Z0-9_]*)", template_var_markup):
        if m.group(1) not in _JINJA_NOISE:
            roots.add(m.group(1))
    return roots


def _known_roots() -> set[str]:
    roots: set[str] = set()
    for tv, *_ in TEMPLATE_VARIABLES:
        if not tv:
            continue
        roots |= _extract_roots(tv)
    return roots | _LOOP_VARS


# Явный allowlist: переменная найдена в разметке шаблона, но НЕ обязана быть
# в TEMPLATE_VARIABLES, с причиной. Каждая запись — осознанное решение, не
# заглушка по умолчанию.
_ALLOWLIST: dict[str, set[str]] = {
    # Контекст trip_*/waybill_form_3 строится ОТДЕЛЬНЫМ модулем
    # (app/services/waybill_docx.py + app/routers/trips*.py), не
    # generate.py/fabrikant_package.py — задание прямо ограничивает сравнение
    # «переменные, которые реально кладутся в контекст (generate.py путь)»;
    # эти шаблоны вне generate.py-пути. Подтверждено: waybill_docx.py кладёт
    # все эти ключи в свой собственный context (grep driver_full_name и пр.).
    "trip_light.docx": {
        "customer_text", "delta_km", "driver_full_name", "driver_license_categories",
        "driver_license_expires_at", "driver_license_issued_at", "driver_license_number",
        "driver_license_series", "fuel_issued_l", "fuel_remaining_finish",
        "fuel_remaining_start", "fuel_type", "initiator_full_name", "initiator_position",
        "odometer_finish", "odometer_start", "org_address", "org_name", "plate",
        "route_from", "route_to", "trip_date", "trip_number", "vehicle_brand_model",
        "vehicle_color",
    },
    "trip_special.docx": {
        "customer_text", "delta_km", "driver_full_name", "driver_license_categories",
        "driver_license_expires_at", "driver_license_issued_at", "driver_license_number",
        "driver_license_series", "fuel_issued_l", "fuel_remaining_finish",
        "fuel_remaining_start", "fuel_type", "initiator_full_name", "initiator_position",
        "odometer_finish", "odometer_start", "org_address", "org_name", "plate",
        "route_from", "route_to", "trip_date", "trip_number", "vehicle_brand_model",
        "vehicle_color",
    },
    "trip_truck.docx": {
        "cargo_name", "cargo_weight_t", "customer_text", "delta_km", "driver_full_name",
        "driver_license_categories", "driver_license_expires_at", "driver_license_issued_at",
        "driver_license_number", "driver_license_series", "fuel_issued_l",
        "fuel_remaining_finish", "fuel_remaining_start", "fuel_type", "initiator_full_name",
        "initiator_position", "loading_point", "odometer_finish", "odometer_start",
        "org_address", "org_name", "plate", "route_from", "route_to", "trip_date",
        "trip_number", "unloading_point", "vehicle_brand_model", "vehicle_color",
    },
    "waybill_form_3.docx": {
        "actual_mileage_km", "cargo_description", "driver_full_name",
        "driver_license_categories", "driver_license_number", "driver_signature_image",
        "driver_signed_at", "driver_tab_number", "fuel_end", "fuel_issued", "fuel_start",
        "odometer_finish", "odometer_start", "org_address", "org_name", "passengers_count",
        "planned_mileage_km", "post_trip_doctor_inspected_at", "post_trip_doctor_name",
        "post_trip_doctor_result", "post_trip_mechanic_inspected_at",
        "post_trip_mechanic_name", "post_trip_mechanic_result", "pre_trip_doctor_inspected_at",
        "pre_trip_doctor_name", "pre_trip_doctor_result", "pre_trip_mechanic_inspected_at",
        "pre_trip_mechanic_name", "pre_trip_mechanic_result", "route_stops",
        "task_description", "vehicle_brand_model", "vehicle_garage_number",
        "vehicle_plate", "vehicle_vin", "waybill_date", "waybill_number",
    },
    # Справочный шаблон «Руководство по разметке» (backend/templates/build/) —
    # это сам пример синтаксиса для авторов шаблонов, "x"/"value"/"условие" —
    # иллюстративные имена из текста руководства, не реальные ключи контекста.
    "ШАБЛОН_ПЕРЕМЕННЫЕ.docx": {"photo", "text", "value", "x", "имя_переменной", "условие"},
}

# Файлы с известными проблемами ВНЕ предмета этого guard-теста (битая разметка
# docx / служебные office-lock-файлы) — пропускаем явно, не молча.
_SKIP_FILES = {
    # Office lock-файл (создаётся при открытом документе), не настоящий .docx.
    "~$роший вариант листа согласования.docx": "office lock-файл, не содержимое",
    # service_note_delivery.docx: дефект разметки починен 14.10.2026
    # (patch_offbuild.py::_fix_service_note_delivery_tr_placement — теги
    # {%tr for%}/{%tr endfor%} лежали СНАРУЖИ <w:tbl>, перенесены внутрь
    # как отдельные строки таблицы). Файл рендерится штатно — убран из
    # allowlist, снова проверяется этим стражем.
}


def _iter_docx_files():
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        if fname.endswith(".docx"):
            yield fname


@pytest.mark.parametrize("fname", list(_iter_docx_files()))
def test_template_variables_are_all_known(fname):
    if fname in _SKIP_FILES:
        pytest.skip(_SKIP_FILES[fname])

    from docxtpl import DocxTemplate

    path = os.path.join(TEMPLATES_DIR, fname)
    tpl = DocxTemplate(path)
    undeclared = tpl.get_undeclared_template_variables()
    roots = {v.split(".")[0] for v in undeclared}

    known = _known_roots() | _ALLOWLIST.get(fname, set())
    missing = sorted(roots - known)
    assert not missing, (
        f"{fname}: переменные без известного источника данных: {missing}. "
        "Добавь ключ в контекст (generate.py путь) + TEMPLATE_VARIABLES, "
        "либо явный allowlist здесь с причиной."
    )
