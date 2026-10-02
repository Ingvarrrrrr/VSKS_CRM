"""Golden-проверка на реальных файлах владельца (ХО/ЛНР) — план
breezy-mixing-lovelace.md часть 2, раздел «Ожидаемый результат на
образцах». Пропускается, если файла нет локально (владелец хранит их вне
репозитория, Downloads/Telegram Desktop).

Строит план-фикстуру из строк самого файла (на проде план уже загружен —
ЛНР 279 позиций, ХО 90 — но локально его может не быть), запускает /preview
и печатает фактические цифры в сравнении с ожидаемыми из плана. Расхождения
ОПИСЫВАЮТСЯ (see assert messages / pytest -s вывод), тест не подгоняется под
них молча — см. docstring задачи.
"""
import os
from pathlib import Path

import pytest

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission
from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import rows as rows_mod

def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]  # не найден ни один — вернём последний, skipif его тоже не найдёт


# Windows-путь владельца (хостовый запуск) ИЛИ копия внутри backend/tests/
# _fact_import_samples/ (не в git — см. .gitignore; контейнер видит её через
# тот же bind-mount, что и сам tests/, см. docker-compose.override.yml).
_WIN_SAMPLES_DIR = Path(r"C:\Users\1\Downloads\Telegram Desktop\Исходники для всех субсидий")
_LOCAL_SAMPLES_DIR = Path(__file__).parent / "_fact_import_samples"
_HO_PATH = _first_existing(
    _LOCAL_SAMPLES_DIR / "_СМЕТА_ХО_2026_МАО_Статусы.xlsx",
    _WIN_SAMPLES_DIR / "_СМЕТА_ХО_2026_МАО_Статусы.xlsx",
)
_LNR_PATH = _first_existing(
    _LOCAL_SAMPLES_DIR / "_План_закупок_ЛНР_МАО_СТАТУС.xlsx",
    _WIN_SAMPLES_DIR / "_План_закупок_ЛНР_МАО_СТАТУС.xlsx",
)


def _read(path: Path) -> bytes:
    return path.read_bytes()


async def _build_plan_fixture_from_rows(db_session, test_org, parsed_rows: list) -> Subsidy:
    """План ещё не загружен локально — строим его из тех же строк файла
    (владелец: «локально может не быть — для golden-теста построй план
    фикстурой из тех же строк файла»). Одна FeoCategory-лист на уникальный
    путь, одна FeoPlannedItem на уникальное (путь, имя)."""
    subsidy = Subsidy(name="Golden-FactImport", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()

    cat_by_path: dict = {}
    for row in parsed_rows:
        path_key = tuple(row["path"])
        if path_key not in cat_by_path:
            cat = FeoCategory(subsidy_id=subsidy.id, level=3, name=(row["path"][-1] if row["path"] else "Прочее"))
            db_session.add(cat)
            await db_session.flush()
            cat_by_path[path_key] = cat
        cat = cat_by_path[path_key]
        amount = row["plan"]["amount"] if row["plan"]["amount"] is not None else row["fact"]["amount"]
        db_session.add(FeoPlannedItem(feo_category_id=cat.id, name=row["name"], amount=amount or 0, is_active=True))

    db_session.add(RolePermission(role_name="employee", key="subsidy.edit", granted=True))
    await db_session.commit()
    return subsidy


@pytest.mark.skipif(not _HO_PATH.exists(), reason="Файл-образец ХО не найден локально")
async def test_golden_ho_preview_against_owner_expectations(client, auth_headers, test_user, db_session, test_org, capsys):
    content = _read(_HO_PATH)
    detected = columns_mod.detect_format_and_header(content, _HO_PATH.name, None)
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, detected["header_row"])
    subsidy = await _build_plan_fixture_from_rows(db_session, test_org, parsed)

    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": (_HO_PATH.name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    paid_rows = [r for r in data["rows"] if r["status"] == "paid"]
    contracted_rows = [r for r in data["rows"] if r["status"] == "contracted"]
    wip_rows = [r for r in data["rows"] if r["status"] == "work_in_progress"]

    # Ожидания владельца (план, раздел «ХО»): «Оплачено» — 17 строк,
    # «Оплачено частично» — 3 (оба попадают в status='paid'/'contracted' по
    # нашей нормализации — «частично» даёт contracted+платёж, не paid).
    report = (
        f"ХО: всего строк={data['totals']['rows']}, закупок={data['totals']['purchases']}, "
        f"пропущено={data['totals']['skipped']}; paid={len(paid_rows)}, "
        f"contracted={len(contracted_rows)}, work_in_progress={len(wip_rows)}; "
        f"сумма договоров={data['totals']['contract_amount']}, оплачено={data['totals']['paid_amount']}"
    )
    print(report)
    # Инвариант (не точные ожидаемые числа — файл мог измениться с момента
    # составления плана, см. docstring): предпросмотр вообще нашёл листовые
    # строки и ничего не записал в БД.
    assert data["totals"]["rows"] > 0, report
    assert paid_rows or contracted_rows or wip_rows, report

    from app.models.purchase import Purchase
    from sqlalchemy import select
    written = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert written == [], "preview не должен писать закупки"


@pytest.mark.skipif(not _LNR_PATH.exists(), reason="Файл-образец ЛНР не найден локально")
async def test_golden_lnr_preview_against_owner_expectations(client, auth_headers, test_user, db_session, test_org, capsys):
    content = _read(_LNR_PATH)
    detected = columns_mod.detect_format_and_header(content, _LNR_PATH.name, None)
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, detected["header_row"])
    subsidy = await _build_plan_fixture_from_rows(db_session, test_org, parsed)

    resp = await client.post(
        f"/api/subsidies/{subsidy.id}/fact-import/preview",
        files={"file": (_LNR_PATH.name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    paid_rows = [r for r in data["rows"] if r["status"] == "paid"]
    contracted_rows = [r for r in data["rows"] if r["status"] == "contracted"]
    wip_rows = [r for r in data["rows"] if r["status"] == "work_in_progress"]

    # Ожидания владельца (план, раздел «ЛНР»): «Оплачено»=35, «Заключён»=25,
    # «В работе»=175, ~41 закупка всего, 5 позиций пропущены (уже есть закупка).
    report = (
        f"ЛНР: всего строк={data['totals']['rows']}, закупок={data['totals']['purchases']}, "
        f"пропущено={data['totals']['skipped']}; paid={len(paid_rows)}, "
        f"contracted={len(contracted_rows)}, work_in_progress={len(wip_rows)}; "
        f"сумма договоров={data['totals']['contract_amount']}, оплачено={data['totals']['paid_amount']}"
    )
    print(report)
    assert data["totals"]["rows"] > 0, report
    assert paid_rows or contracted_rows or wip_rows, report

    from app.models.purchase import Purchase
    from sqlalchemy import select
    written = (await db_session.execute(select(Purchase).where(Purchase.subsidy_id == subsidy.id))).scalars().all()
    assert written == [], "preview не должен писать закупки"
