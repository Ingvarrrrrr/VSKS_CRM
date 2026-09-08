"""Golden regression test for the purchase-import parser (D-05 test debt item 5).

Generates a real template workbook via
services.import_template_builder.build_purchase_import_template_workbook (the
same function GET /api/purchases/import/template uses), fills 3 data rows,
runs it through services.purchase_import_parser_group._parse_and_group
(commit=False, i.e. the /import/preview path) and compares the JSON-safe
result against a saved golden file. Catches accidental behaviour drift in the
~900-line parser without re-testing every branch by hand.

Fixture is minimal: one throwaway Subsidy (no FeoCategory rows — the test
relies on the parser's simulate-mode FEO auto-creation, so no "heavy" fixture
tree is needed). All 3 rows use distinct contract_number/item_name/amounts so
duplicate-detection stays empty and the run is deterministic.

Golden file: backend/tests/golden/purchase_import_parser.json — created on
first run if missing, otherwise the result must match it exactly.
"""
import json
from pathlib import Path

import pytest
import pytest_asyncio

from app.models.subsidy import Subsidy
from app.services.import_template_builder import build_purchase_import_template_workbook
from app.services.purchase_import_parser import _parse_and_group

GOLDEN_PATH = Path(__file__).parent / "golden" / "purchase_import_parser.json"

# header (exact text from import_template_spec._COL_SPEC) -> value, per row.
# Same feo_l1 for all 3 rows on purpose: the parser dedups pending FEO
# creation by full path, so feo_to_create ends up with exactly one entry.
_ROWS = [
    {
        "Наименование товара": "Ноутбук офисный",
        "ФЭО Ур.1": "Прочее",
        "ИНН контрагента": "1111111111",
        "№ договора": "GOLD-001",
        "Дата договора": "01.02.2026",
        "Количество (план)": 2,
        "Ед. изм.": "шт",
        "Цена за ед. (план)": 50000,
        "Сумма факт": 100000,
    },
    {
        "Наименование товара": "Стул офисный",
        "ФЭО Ур.1": "Прочее",
        "ИНН контрагента": "1111111111",
        "№ договора": "GOLD-002",
        "Дата договора": "02.02.2026",
        "Количество (план)": 10,
        "Ед. изм.": "шт",
        "Цена за ед. (план)": 3000,
        "Сумма факт": 30000,
    },
    {
        "Наименование товара": "Бумага А4",
        "ФЭО Ур.1": "Прочее",
        "ИНН контрагента": "2222222222",
        "№ договора": "GOLD-003",
        "Дата договора": "03.02.2026",
        "Количество (план)": 50,
        "Ед. изм.": "уп",
        "Цена за ед. (план)": 250,
        "Сумма факт": 12500,
    },
]


@pytest_asyncio.fixture
async def golden_subsidy(db_session):
    """Throwaway Subsidy — no FeoCategory rows, parser simulates them."""
    s = Subsidy(name="GoldenParserTest", year=2026, budget=0, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _build_workbook_bytes(wb) -> bytes:
    from io import BytesIO

    ws = wb["Закупки"]
    header_row = next(ws.iter_rows(min_row=1, max_row=1))
    headers = [c.value for c in header_row]
    col_of = {h: i for i, h in enumerate(headers) if h}

    for row_data in _ROWS:
        row_values = [None] * len(headers)
        for header, value in row_data.items():
            assert header in col_of, f"Template header not found: {header!r} (headers changed?)"
            row_values[col_of[header]] = value
        ws.append(row_values)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_purchase_import_parser_golden(db_session, golden_subsidy):
    wb = await build_purchase_import_template_workbook(
        db_session, subsidy_id=golden_subsidy.id, subsidy_name=golden_subsidy.name
    )
    content = _build_workbook_bytes(wb)

    result = await _parse_and_group(content, golden_subsidy.id, db_session, commit=False)

    # JSON-safe normalisation (defensive — current fields are already plain
    # str/int/float/bool/list/None, but `default=str` guards against a future
    # Decimal/date slipping into the preview dict without this test choking
    # on a TypeError instead of a golden mismatch).
    result_json = json.loads(json.dumps(result, ensure_ascii=False, default=str))

    if not GOLDEN_PATH.exists():
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(
            json.dumps(result_json, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pytest.fail(
            f"Golden file created at {GOLDEN_PATH} — rerun the test to compare against it."
        )

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert result_json == golden, (
        "Purchase import parser output drifted from the golden snapshot — "
        f"see {GOLDEN_PATH}. If the change is intentional, delete the file "
        "and rerun to regenerate it."
    )
