"""Этап 2 импорта ФЭО: затронутые субсидии + гейт записи по каждой из них.

Перенесено из тела `_do_feo_import` (было ~строки 387–409 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5),
логика не менялась — только вынесена из тела функции в два module-level
шага, вызываемых оркестратором (feo_import_core.py) в том же порядке.

collect_affected_subsidies — лёгкий пред-проход по строкам файла ТОЛЬКО ради
определения затронутых субсидий (нужен снимку предыдущей редакции дерева,
который берёт feo_import_apply.py), без накопления ошибок — их соберёт
основной цикл (feo_import_apply.py).

assert_write_gate — B2 (дыра импорта, закрыта 2026-09-01): гейт ЗАПИСИ по
КАЖДОЙ субсидии из touched_subsidies — ДО снимка версии дерева и ДО основного
цикла, а значит и ДО выдачи dry_run-превью (в dry_run обработка идёт точно
так же, откат — только в самом конце). См. docstring
`app.routers.feo_categories._require_feo_import_write` за картиной дыры.
"""
from app.routers import feo_categories as fc
from app.services.feo_import_common import get_cell


def collect_affected_subsidies(state) -> None:
    rows = state.rows
    c_lvl2 = state.c_lvl2
    c_subsidy = state.c_subsidy
    sub_by_name = state.sub_by_name
    default_subsidy_id = state.default_subsidy_id

    touched_subsidies: set[int] = set()
    for _row in rows:
        _lvl2 = get_cell(_row, c_lvl2)
        if not _lvl2 or _lvl2.startswith("←"):
            continue
        _sub_name = get_cell(_row, c_subsidy) if c_subsidy is not None else None
        if _sub_name and not _sub_name.startswith("←"):
            _sid = sub_by_name.get(_sub_name.lower().strip()) or default_subsidy_id
        else:
            _sid = default_subsidy_id
        if _sid:
            touched_subsidies.add(_sid)
    state.touched_subsidies = touched_subsidies


async def assert_write_gate(state) -> None:
    await fc._require_feo_import_write(state.user, state.db, state.touched_subsidies, state.sub_rows)
