"""Предупреждение строки «Импорта факта» (build_preview) — задача 3 (владелец,
07.10.2026, прод id=74 «ЛНР», РЕЕ-2026-03421): оплата проставлена, а статус
строки ниже «Поставлено»/«Оплачено» — это тот же сигнал «оплачено, но не
поставлено», который на дашборде показывает плашка paid_over_delivered.py,
только на уровне строки импорта, до того, как закупка вообще создана.

Гонять по одному узлу за вызов pytest в контейнере (project_pytest_asyncio_
loop_flake, Lessons.md VSKS_CRM).
"""
import io
import uuid

import pytest
from fastapi import UploadFile
from openpyxl import Workbook

from app.services.historical_fact_import.preview import build_preview
from tests.test_feo_import_tree import _cleanup_subsidy, _make_subsidy

_PLAN_HEADERS = ["Уровень 2", "Плановая позиция", "Плановое количество", "Плановая цена за единицу"]
_PLAN_ROW = ["Направление — тест предупреждения", "Позиция — тест предупреждения", "2", "500"]
_FACT_HEADERS = [
    "Правильный статус", "Факт: Количество", "Факт: Цена", "Факт: Сумма",
    "Оплачено", "Аванс (да/нет)", "Законтрактовано", "Поставщик", "№ закупки",
]


def _mk_xlsx_upload(headers, rows) -> UploadFile:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return UploadFile(file=bio, filename=f"import-{uuid.uuid4().hex[:6]}.xlsx")


@pytest.mark.asyncio
async def test_paid_amount_at_contracted_status_warns_not_delivered(db_session, superadmin_user):
    """Статус «Заключён договор» (ниже «Поставлено») + «Оплачено»=500,
    Аванс=нет — предупреждение о расхождении (прод-кейс: work_in_progress +
    оплата по отметке, договора нет)."""
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row = (
        [subsidy.name] + _PLAN_ROW
        + ["Заключён договор", "", "", "", "500", "нет", "1000", "ООО Тест", "РЕЕ-1"]
    )
    upload = _mk_xlsx_upload(headers, [row])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        rows_with_status = [r for r in preview["rows"] if r["status_raw"]]
        assert len(rows_with_status) == 1, preview["rows"]
        warnings = rows_with_status[0]["warnings"]
        matching = [w for w in warnings if "оплачено, но не поставлено" in w]
        assert matching, warnings
        assert "«Заключён договор»" in matching[0]
        assert "проверьте статус" in matching[0]

        # Доп. задача (владелец, 07.10.2026): тот же сигнал обязан быть виден
        # на шаге итогов мастера (totals.paid_not_delivered), не только у
        # самой строки — FactImportStepConfirm.vue читает эти totals.
        pnd = preview["totals"]["paid_not_delivered"]
        assert pnd["count"] == 1, pnd
        assert pnd["amount"] == pytest.approx(500.0, abs=0.01)
        assert pnd["rows"][0]["row"] == rows_with_status[0]["row"]
        assert pnd["rows"][0]["status_label"] == "Заключён договор"
        assert pnd["rows"][0]["paid"] == pytest.approx(500.0, abs=0.01)
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_advance_payment_does_not_duplicate_warning(db_session, superadmin_user):
    """Аванс (Аванс=да, статус «Оплачено» -> принудительно 'ordered') уже
    объяснён отдельным предупреждением «аванс: оплачено до поставки» — новое
    предупреждение «оплачено, но не поставлено» не дублируется поверх него."""
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row = (
        [subsidy.name] + _PLAN_ROW
        + ["Оплачено", "", "", "", "500", "да", "1000", "ООО Тест", "РЕЕ-2"]
    )
    upload = _mk_xlsx_upload(headers, [row])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        rows_with_status = [r for r in preview["rows"] if r["status_raw"]]
        assert len(rows_with_status) == 1, preview["rows"]
        warnings = rows_with_status[0]["warnings"]
        assert any("аванс: оплачено до поставки" in w for w in warnings)
        assert not any("оплачено, но не поставлено" in w for w in warnings)
        # Аванс не должен попадать в totals.paid_not_delivered — тот же предикат.
        assert preview["totals"]["paid_not_delivered"]["count"] == 0
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_delivered_status_with_payment_has_no_warning(db_session, superadmin_user):
    """Статус «Поставлено» (delivered) с оплатой — ожидаемо, без предупреждения
    о расхождении статуса и оплаты."""
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row = (
        [subsidy.name] + _PLAN_ROW
        + ["Поставлено", "2", "500", "1000", "500", "нет", "1000", "ООО Тест", "РЕЕ-3"]
    )
    upload = _mk_xlsx_upload(headers, [row])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        rows_with_status = [r for r in preview["rows"] if r["status_raw"]]
        assert len(rows_with_status) == 1, preview["rows"]
        warnings = rows_with_status[0]["warnings"]
        assert not any("оплачено, но не поставлено" in w for w in warnings)
        assert preview["totals"]["paid_not_delivered"]["count"] == 0
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_totals_paid_not_delivered_aggregates_several_rows(db_session, superadmin_user):
    """Доп. задача (владелец, 07.10.2026): «при импорте об этом должно идти
    уведомление» — на шаге итогов мастера (FactImportStepConfirm.vue читает
    totals.paid_not_delivered). Две независимые строки с расхождением статус/
    оплата — count=2, amount = Σ оплат, rows[] с номером строки Excel/именем/
    подписью статуса/оплатой — то же, что видит пользователь у самой строки."""
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row1 = (
        [subsidy.name, "Направление А", "Позиция А", "2", "500"]
        + ["Заключён договор", "", "", "", "300", "нет", "1000", "ООО Тест", "РЕЕ-10"]
    )
    row2 = (
        [subsidy.name, "Направление Б", "Позиция Б", "2", "500"]
        + ["Заказано", "", "", "", "700", "нет", "1000", "ООО Тест", "РЕЕ-11"]
    )
    upload = _mk_xlsx_upload(headers, [row1, row2])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        pnd = preview["totals"]["paid_not_delivered"]
        assert pnd["count"] == 2, pnd
        assert pnd["amount"] == pytest.approx(1000.0, abs=0.01)
        by_row = {r["row"]: r for r in pnd["rows"]}
        statuses = {r["status_label"] for r in by_row.values()}
        assert statuses == {"Заключён договор", "Заказано"}
        paid_by_status = {r["status_label"]: r["paid"] for r in by_row.values()}
        assert paid_by_status["Заключён договор"] == pytest.approx(300.0, abs=0.01)
        assert paid_by_status["Заказано"] == pytest.approx(700.0, abs=0.01)
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
