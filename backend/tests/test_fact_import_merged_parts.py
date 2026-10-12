"""Импорт факта привязывает строку файла к ЧАСТИ объединённой плановой
позиции (владелец, 12.10.2026, план merged-item-parts.md): позиция, собранная
загрузкой плана «Объединить в одну» (FeoPlannedItem.parts — состав), не
должна слипать несколько строк факта в одну закупку с одним числом — каждая
строка получает СВОЮ часть по точному совпадению суммы плана.

Переиспользует воркбук/фикстуру test_fact_import_commit.py (ПРАВИЛО №6 — не
вторая копия `_build_ho_workbook`/`_row`/`subsidy_with_plan`); здесь только
FeoPlannedItem.parts заполняется ВРУЧНУЮ (то, что в реальности делает
feo_import_duplicates.py при загрузке плана, см. test_feo_import_merged_parts.py
для самой загрузки) — тестируется шаг импорта факта отдельно."""
import json

import pytest
from sqlalchemy import select

from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

from tests.test_fact_import_commit import _build_ho_workbook, _row, subsidy_with_plan  # noqa: F401


async def _grant(db_session):
    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()


async def test_preview_assigns_distinct_parts_by_exact_amount(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """4 строки файла («Gaz…» 317 400/20 000/10 000/5 000) против позиции с
    4 частями на ТЕ ЖЕ суммы — КАЖДАЯ строка получает СВОЮ часть, без
    повторов (одна часть — одной строке)."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_gaz = FeoPlannedItem(
        feo_category_id=cat.id, name="Gaz A22R35 Х920АЕ 180", amount=352400, is_active=True,
        parts=[
            {"key": "20", "row": 20, "qty": 1.0, "unit": None, "unit_price": 317400.0, "amount": 317400.0},
            {"key": "21", "row": 21, "qty": 1.0, "unit": None, "unit_price": 20000.0, "amount": 20000.0},
            {"key": "22", "row": 22, "qty": 1.0, "unit": None, "unit_price": 10000.0, "amount": 10000.0},
            {"key": "23", "row": 23, "qty": 1.0, "unit": None, "unit_price": 5000.0, "amount": 5000.0},
        ],
    )
    db_session.add(item_gaz)
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Аренда оборудования", 317400, 317400, 317400, status_raw="Оплачено", paid=317400,
             supplier="ООО Альфа", item_name="Gaz A22R35 Х920АЕ 180"),
        _row("Аренда оборудования", 20000, 20000, 20000, status_raw="Оплачено", paid=20000,
             supplier="ООО Бета", item_name="Gaz A22R35 Х920АЕ 180"),
        _row("Аренда оборудования", 10000, 10000, 10000, status_raw="Оплачено", paid=10000,
             supplier="ООО Гамма", item_name="Gaz A22R35 Х920АЕ 180"),
        _row("Аренда оборудования", 5000, 5000, 5000, status_raw="Оплачено", paid=5000,
             supplier="ООО Дельта", item_name="Gaz A22R35 Х920АЕ 180"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 4
    part_keys = [r["match"]["plan_part_key"] for r in rows]
    assert None not in part_keys, rows
    assert sorted(part_keys) == ["20", "21", "22", "23"], "каждая строка — своя часть, без повторов"
    assert not any("Выберите часть" in w for r in rows for w in r["warnings"])


async def test_preview_two_rows_get_their_own_part_by_amount(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """Контрольный пример владельца (файл ХО_ЛНР_ДНР_МАКЛЮК_Отправил.xlsx,
    лист ДНРР): «Проезд, проживание, питание» — строка 151 (план 407 184,10)
    и строка 152 (план 292 815,90) ОБЯЗАНЫ получить РАЗНЫЕ части по точной
    сумме, а не слипнуться в одну закупку."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_trip = FeoPlannedItem(
        feo_category_id=cat.id, name="Проезд, проживание, питание", amount=700000, is_active=True,
        parts=[
            {"key": "151", "row": 151, "qty": None, "unit": None, "unit_price": None, "amount": 407184.10},
            {"key": "152", "row": 152, "qty": None, "unit": None, "unit_price": None, "amount": 292815.90},
        ],
    )
    db_session.add(item_trip)
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Аренда оборудования", 407184.10, 407184.10, 407184.10, status_raw="Оплачено", paid=407184.10,
             item_name="Проезд, проживание, питание"),
        _row("Аренда оборудования", 292815.90, 292815.90, 292815.90, status_raw="Оплачено", paid=292815.90,
             item_name="Проезд, проживание, питание"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    by_amount = {r["plan"]["amount"]: r["match"]["plan_part_key"] for r in rows}
    assert by_amount[407184.10] == "151"
    assert by_amount[292815.90] == "152"


async def test_commit_writes_feo_plan_part_key_on_purchase_item(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """commit.py должен записать feo_plan_part_key на PurchaseItem, не
    только показать его в предпросмотре."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_gaz = FeoPlannedItem(
        feo_category_id=cat.id, name="Gaz A22R35 Х920АЕ 180", amount=337400, is_active=True,
        parts=[
            {"key": "20", "row": 20, "qty": 1.0, "unit": None, "unit_price": 317400.0, "amount": 317400.0},
            {"key": "21", "row": 21, "qty": 1.0, "unit": None, "unit_price": 20000.0, "amount": 20000.0},
        ],
    )
    db_session.add(item_gaz)
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Аренда оборудования", 317400, 317400, 317400, status_raw="Оплачено", paid=317400,
             supplier="ООО Альфа", item_name="Gaz A22R35 Х920АЕ 180"),
        _row("Аренда оборудования", 20000, 20000, 20000, status_raw="Оплачено", paid=20000,
             supplier="ООО Бета", item_name="Gaz A22R35 Х920АЕ 180"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/commit",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["purchases_created"] == 2

    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == subsidy.id, Purchase.import_run_id == data["run_id"])
    )).scalars().all()
    items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id.in_([p.id for p in purchases]))
    )).scalars().all()
    assert len(items) == 2
    keys_by_amount = {float(it.total_price): it.feo_plan_part_key for it in items}
    assert keys_by_amount[317400.0] == "20"
    assert keys_by_amount[20000.0] == "21"


async def test_manual_override_plan_part_key_wins(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """Явный выбор человека (decisions.row_overrides[row].plan_part_key)
    побеждает автоподбор по сумме — нужен, когда суммы не совпадают точно
    (владелец мог ошибиться при наборе плана, либо файл фактов не совпадает
    1:1 с планом)."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_gaz = FeoPlannedItem(
        feo_category_id=cat.id, name="Gaz A22R35 Х920АЕ 180", amount=337400, is_active=True,
        parts=[
            {"key": "20", "row": 20, "qty": 1.0, "unit": None, "unit_price": 317400.0, "amount": 317400.0},
            {"key": "21", "row": 21, "qty": 1.0, "unit": None, "unit_price": 20000.0, "amount": 20000.0},
        ],
    )
    db_session.add(item_gaz)
    await db_session.commit()

    # Сумма строки файла (19 999) НЕ совпадает точно ни с одной частью —
    # без override часть не определится.
    content = _build_ho_workbook([
        _row("Аренда оборудования", 19999, 19999, 19999, status_raw="Оплачено", paid=19999,
             item_name="Gaz A22R35 Х920АЕ 180"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    row = resp.json()["rows"][0]
    assert row["match"]["plan_part_key"] is None
    assert any("Выберите часть" in w for w in row["warnings"]), row["warnings"]

    decisions = {"row_overrides": {str(row["row"]): {"plan_part_key": "21"}}}
    resp2 = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"decisions": json.dumps(decisions)},
        headers=auth_headers,
    )
    row2 = resp2.json()["rows"][0]
    assert row2["match"]["plan_part_key"] == "21"
    assert not any("Выберите часть" in w for w in row2["warnings"])


async def test_part_excess_warning(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """«Факт больше плана части» — ДОПОЛНИТЕЛЬНО к общей проверке по всей
    позиции (не трогаем её): часть на 20 000 получила факт 25 000 — владелец
    должен увидеть именно это, даже если план ВСЕЙ позиции (337 400) не
    превышен."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_gaz = FeoPlannedItem(
        feo_category_id=cat.id, name="Gaz A22R35 Х920АЕ 180", amount=337400, is_active=True,
        parts=[
            {"key": "20", "row": 20, "qty": 1.0, "unit": None, "unit_price": 317400.0, "amount": 317400.0},
            {"key": "21", "row": 21, "qty": 1.0, "unit": None, "unit_price": 20000.0, "amount": 20000.0},
        ],
    )
    db_session.add(item_gaz)
    await db_session.commit()

    content = _build_ho_workbook([
        _row("Аренда оборудования", 20000, 25000, 25000, status_raw="Оплачено", paid=25000,
             item_name="Gaz A22R35 Х920АЕ 180"),
    ])
    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": ("test.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    row = resp.json()["rows"][0]
    assert row["match"]["plan_part_key"] == "21"
    assert any("Факт больше плана части" in w for w in row["warnings"]), row["warnings"]


async def test_plan_positions_endpoint_returns_parts(
    client, auth_headers, test_user, db_session, subsidy_with_plan,
):
    """GET /feo-categories/plan-positions — parts присутствует (не только у
    объединённых: обычная позиция отдаёт [])."""
    await _grant(db_session)
    subsidy, cat, item_paid, item_wip = subsidy_with_plan
    item_gaz = FeoPlannedItem(
        feo_category_id=cat.id, name="Gaz A22R35 Х920АЕ 180", amount=337400, is_active=True,
        parts=[{"key": "20", "row": 20, "qty": 1.0, "unit": None, "unit_price": 317400.0, "amount": 317400.0}],
    )
    db_session.add(item_gaz)
    await db_session.commit()

    resp = await client.get(
        f"/api/feo-categories/plan-positions?subsidy_id={subsidy.id}", headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    gaz_row = next(r for r in rows if r["id"] == item_gaz.id and r["kind"] == "planned_item")
    assert gaz_row["parts"][0]["key"] == "20"
    assert gaz_row["parts"][0]["amount"] == 317400.0
    assert gaz_row["parts"][0]["purchases"] == []

    paid_row = next(r for r in rows if r["id"] == item_paid.id and r["kind"] == "planned_item")
    assert paid_row["parts"] == []
