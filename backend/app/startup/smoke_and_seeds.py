"""Smoke-render проверки шаблонов и разовые data-сиды (xlsx → БД),
выполняемые при каждом старте приложения. Перенесено 1:1 из
app/__init__.py.lifespan при разрезании файла на модули (Правило №5).
Каждый блок — отдельная функция с исходным комментарием-заголовком;
run() вызывает их в исходном порядке.
"""
import logging
import os

from app.database import async_session


async def _phase29_08_smoke_render_trip_templates():
    # Phase 29-08: smoke-render trip templates (Lesson 2026-05-18 — catches Jinja TemplateSyntaxError at boot)
    # ZERO {% tr %} in templates (Lesson 2026-05-15). Non-fatal: log error, do NOT crash.
    try:
        from docxtpl import DocxTemplate as _DocxTpl29
        _fake_trip_ctx = {
            # 29-08 base keys
            'vehicle_plate': 'A001AA77', 'driver_full_name': 'Тест Тестов',
            'date': '01.01.2026', 'odometer_start': '1000', 'odometer_finish': '1100',
            'org_name': 'ВСКС', 'route_from': 'Москва', 'route_to': 'Тула',
            'vehicle_brand_model': 'Test Auto', 'fuel_type': 'AI-92',
            'driver_license_series': '77 ОТ', 'driver_license_number': '123456',
            'driver_license_categories': 'B', 'driver_license_issued_at': '01.01.2020',
            'driver_license_expires_at': '01.01.2030', 'delta_km': '100',
            'fuel_remaining_start': '30', 'fuel_remaining_finish': '25', 'fuel_issued_l': '10',
            'initiator_full_name': 'Иванов', 'initiator_position': 'Менеджер',
            'trip_number': 'VSKS-00001', 'trip_date': '01.01.2026',
            'cargo_name': '', 'cargo_weight_t': '', 'loading_point': '', 'unloading_point': '',
            'cargo_count': '', 'route': 'Москва → Тула', 'vehicle_color': 'белый', 'mileage': '100',
            'fuel_brand': 'AI-92', 'fuel_start': '30', 'fuel_finish': '25', 'customer_text': '',
            'plate': 'A001AA77',
            # 29-20 extended keys
            'vehicle_brand': 'Test', 'vehicle_model': 'Auto', 'vehicle_type_label': 'Легковой автомобиль',
            'vehicle_load_capacity': '', 'date_dmy': '01.01.2026', 'odometer_diff': '100',
            'fuel_added': '10', 'fuel_norm': '', 'fuel_season': 'зимняя', 'fuel_used_calc': '',
            'org_address': 'Москва', 'customer_org_name': 'ВСКС', 'customer_org_address': 'Москва',
            'purpose': '', 'task_description': '',
        }
        _tpl_dir29 = os.path.join(os.path.dirname(__file__), '..', '..', 'templates')
        for _tpl_name29 in ['trip_light.docx', 'trip_truck.docx', 'trip_special.docx']:
            try:
                _tpl_path29 = os.path.join(_tpl_dir29, _tpl_name29)
                if os.path.exists(_tpl_path29):
                    _DocxTpl29(_tpl_path29).render(_fake_trip_ctx)
                    logging.getLogger(__name__).info(f"Phase 29 trip template smoke-render OK: {_tpl_name29}")
                else:
                    logging.getLogger(__name__).warning(f"Phase 29 trip template not found (skip smoke): {_tpl_name29}")
            except Exception as _e29:
                logging.getLogger(__name__).error(
                    f"Phase 29 trip template smoke-render FAILED {_tpl_name29}: {_e29}"
                )
    except Exception as _e29_outer:
        logging.getLogger(__name__).warning(f"Phase 29 smoke-render block failed (non-fatal): {_e29_outer}")


async def _phase29_11_seed_vehicles_from_xlsx():
    # Phase 29-11: seed vehicles from xlsx Голичкова (idempotent — ON CONFLICT plate DO NOTHING)
    try:
        from app.services.vehicles_seed import seed_vehicles_from_xlsx as _seed_vehicles
        async with async_session() as _db29:
            _vresult = await _seed_vehicles(_db29)
        logging.getLogger(__name__).info(f"Phase 29 vehicles_seed: {_vresult}")
    except Exception as _e29_seed:
        logging.getLogger(__name__).warning(f"Phase 29 vehicles_seed skipped (non-fatal): {_e29_seed}")


async def _phase30_1_seed_fleet_data():
    # Phase 30.1: seed водителей, норм расхода, тестовых штрафов из xlsx ВСКС
    try:
        from app.services.fleet_seed import (
            seed_drivers_from_xlsx as _seed_drivers,
            seed_fuel_norms_from_xlsx as _seed_fuel_norms,
            seed_test_fines as _seed_test_fines,
        )
        async with async_session() as _db301:
            _r_drivers = await _seed_drivers(_db301)
            logging.getLogger(__name__).info(f"Phase 30.1 drivers_seed: {_r_drivers}")
            _r_fuel = await _seed_fuel_norms(_db301)
            logging.getLogger(__name__).info(f"Phase 30.1 fuel_norms_seed: {_r_fuel}")
            _r_fines = await _seed_test_fines(_db301)
            logging.getLogger(__name__).info(f"Phase 30.1 test_fines_seed: {_r_fines}")
    except Exception as _e301_seed:
        logging.getLogger(__name__).warning(
            f"Phase 30.1 fleet seed skipped (non-fatal): {_e301_seed}"
        )


async def run():
    """Вызывает smoke-render проверки и data-сиды в исходном порядке (см. app/__init__.py.lifespan до разрезания)."""
    await _phase29_08_smoke_render_trip_templates()
    await _phase29_11_seed_vehicles_from_xlsx()
    await _phase30_1_seed_fleet_data()
