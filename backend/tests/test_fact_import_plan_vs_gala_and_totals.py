"""Задачи B и C (владелец, файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx, лист ДНРР,
11.10.2026), build_preview-уровень.

B) Строка 89 «Бочка металлическая с насосом для хранения топлива»: в файле
план — 4 × 5 500 = 22 000; в GALA (FeoPlannedItem) план — 1 × 22 000 = 22 000.
Суммы совпали случайно, количество и цена — нет. Два сигнала:
  1. «План в файле отличается от плана в GALA…» (новое предупреждение).
  2. Текст превышения ТЗ словами владельца («Факт больше плана GALA: …»),
     БЕЗ «ТЗ позиции…уменьшите ТЗ» (app.services.tz_excess_approval.message —
     этот текст написан для карточки заявки/закупки, владелец его не понял).

C) totals.paid_status_without_paid — строки со статусом «Оплачено», у
которых колонка «Оплачено» пуста (владелец принимал «Факт: Сумма» таких
строк за «Оплачено» на шаге итогов мастера).

Гонять по одному узлу за вызов pytest в контейнере (project_pytest_asyncio_
loop_flake, Lessons.md VSKS_CRM).
"""
import pytest

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.historical_fact_import.preview import build_preview
from tests.test_feo_import_tree import _cleanup_subsidy, _make_subsidy
from tests.test_fact_import_paid_over_delivered_warning import (
    _FACT_HEADERS, _PLAN_HEADERS, _mk_xlsx_upload,
)


async def _make_gala_planned_item(db_session, subsidy_id, name, quantity, unit_price, amount):
    cat = FeoCategory(subsidy_id=subsidy_id, level=3, name=name)
    db_session.add(cat)
    await db_session.flush()
    item = FeoPlannedItem(
        feo_category_id=cat.id, name=name, quantity=quantity, unit_price=unit_price,
        amount=amount, is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    return item


@pytest.mark.asyncio
async def test_file_plan_differs_from_gala_plan_and_tz_excess_uses_owner_words(db_session, superadmin_user):
    """Боевая строка 89: план файла (4 × 5 500) ≠ план GALA (1 × 22 000),
    хотя итоговая сумма сошлась. Матчится по имени на единственную
    плановую позицию GALA — оба предупреждения должны появиться, старый
    текст «ТЗ позиции…уменьшите ТЗ» — не появиться."""
    subsidy = await _make_subsidy(db_session)
    name = "Бочка металлическая с насосом для хранения топлива"
    await _make_gala_planned_item(db_session, subsidy.id, name, quantity=1, unit_price=22000, amount=22000)

    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row = (
        [subsidy.name, "Топливо и ГСМ", name, "4", "5500"]
        + ["Оплачено", "", "5500", "22000", "22000", "нет", "", "ООО Топливо", "РЕЕ-89"]
    )
    upload = _mk_xlsx_upload(headers, [row])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        rows_with_status = [r for r in preview["rows"] if r["status_raw"]]
        assert len(rows_with_status) == 1, preview["rows"]
        row_out = rows_with_status[0]
        assert row_out["match"]["state"] == "found", row_out

        plan_diff_msg = (
            "План в файле отличается от плана в GALA: в GALA 1 × 22 000,00 ₽ = 22 000,00 ₽, "
            "в файле 4 × 5 500,00 ₽ = 22 000,00 ₽. Факт сравнивается с планом GALA — если в "
            "файле план верный, загрузите план (ФЭО) заново."
        )
        assert plan_diff_msg in row_out["warnings"], row_out["warnings"]

        excess_msg = "Факт больше плана GALA: количество — в плане 1, в строке 4 (больше на 3); сумма в пределах плана"
        assert excess_msg in row_out["warnings"], row_out["warnings"]

        assert not any("ТЗ позиции" in w for w in row_out["warnings"]), row_out["warnings"]
        assert not any("уменьшите ТЗ" in w for w in row_out["warnings"]), row_out["warnings"]
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_totals_paid_status_without_paid_aggregates_rows(db_session, superadmin_user):
    """Задача C: строки со статусом «Оплачено» и пустой колонкой «Оплачено»
    (владелец: «я посчитал их оплатой по Excel, а в GALA они не попадают в
    «Оплачено»») — видны в totals.paid_status_without_paid на шаге итогов,
    не только предупреждением у самой строки."""
    subsidy = await _make_subsidy(db_session)
    headers = ["Субсидия"] + _PLAN_HEADERS + _FACT_HEADERS
    row1 = (
        [subsidy.name, "Направление А", "Позиция А", "2", "500"]
        + ["Оплачено", "", "", "8000", "", "нет", "", "ООО Тест", "РЕЕ-141"]
    )
    row2 = (
        [subsidy.name, "Направление Б", "Позиция Б", "2", "500"]
        + ["Оплачено", "", "", "23192", "", "нет", "", "ООО Тест", "РЕЕ-142"]
    )
    upload = _mk_xlsx_upload(headers, [row1, row2])
    content = await upload.read()
    try:
        preview = await build_preview(
            db_session, subsidy.id, content, upload.filename or "", None, None, None,
        )
        rows_with_status = [r for r in preview["rows"] if r["status_raw"]]
        assert len(rows_with_status) == 2, preview["rows"]
        for r in rows_with_status:
            assert any("сумма оплаты пуста" in w for w in r["warnings"]), r["warnings"]

        totals_block = preview["totals"]["paid_status_without_paid"]
        assert totals_block["count"] == 2, totals_block
        assert totals_block["fact_amount"] == pytest.approx(31192.0, abs=0.01), totals_block
        by_row = {r["row"]: r for r in totals_block["rows"]}
        rows_nums = sorted(by_row.keys())
        assert [by_row[n]["fact"] for n in rows_nums] == [8000.0, 23192.0]
        assert totals_block["rows_text"]
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
