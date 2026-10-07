"""Строка статьи ФЭО без «Плановой позиции» (колонка O шаблона) никогда не
становится плановой позицией — решение владельца, шаг 0.5 плана
`.planning/quick/2026-10-07-dnr-feo-cards/PLAN.md`.

Боевой дефект (файл «ДНР_2026 для закачки в ГАЛА.xlsx», лист
«ДНР_ФЭО_НАСТЯ (копия) (2)», строка 149): статья 2.12 «Расходы закупка
товаров, услуг…» — в строке есть «Ед. изм.» (I), «Кол-во»/«Стоимость за
ед.»/«Всего» (J/K/L) и промежуточный итог в «Сумме плана» (S) = 1 907 229,50,
но НЕТ ни «Плановой позиции» (O), ни «Товар/услуга/работа» (U). Импорт
(apply_collected_plan, app/services/feo_import_plan.py) раньше заводил по
такой строке FeoPlannedItem с именем САМОЙ СТАТЬИ и без типа — ровно это
воспроизводит test_bare_category_plan_sum_creates_no_item ниже.

Правило (найдено в app/services/feo_import_apply.py — флаг
`_row_had_own_position_name`, читается ДО любых веток продвижения/само-
объявления «Плановой позиции»; уточнено координатором 07.10 — охват ПО
ФАЙЛУ В ЦЕЛОМ: `_lvl5_column_in_use`, True только если «Плановая позиция»
непуста хоть в одной строке ЭТОГО импорта; итоговый `_row_treat_as_real_
position = _row_had_own_position_name or not _lvl5_column_in_use`
кладётся в `collected_plan[cat.id]["has_own_position_name"]`; читается в
app/services/feo_import_plan.py::apply_collected_plan): строка без СВОЕЙ
«Плановой позиции», В ФАЙЛЕ, ГДЕ эта колонка где-то используется — статья,
не позиция, её план/ФЭО не попадают в FeoPlannedItem. Если колонка в файле
НЕ используется НИГДЕ — старое поведение (смета без позиций, план статьи =
позиция с её именем, см. test_legacy_file_without_item_name_column_keeps_
old_behavior). Строка, у которой «Плановая позиция» СОВПАЛА с именем своей
же категории (само-объявление, item_name_equals_category) — настоящая
позиция, не трогаем (отдельный тест test_self_declared_category_still_
creates_item).

Тип позиции («товар/услуга/работа», app/services/item_types.py) — ТОЛЬКО из
колонки «Товар/услуга/работа» (U в боевом файле, здесь — одноимённый
заголовок); «Ед. изм.» на тип не влияет (test_unit_column_never_sets_item_type).

Стиль вызова — как в test_feo_import_item_type_column.py: реальный роутер
`import_feo_from_excel` (нужен настоящий разбор заголовков find_col, а не
индексы руками), xlsx собирается `_mk_xlsx_upload` из того же модуля.
"""
import pytest

from app.routers.feo_import import import_feo_from_excel
from tests.test_feo_import_tree import _cleanup_subsidy, _get_categories, _get_items, _make_subsidy

_HEADERS = [
    "Субсидия", "Уровень 2", "Уровень 3",
    "Плановая позиция", "Ед. изм.", "Плановое количество",
    "Плановая цена за единицу", "Сумма плана", "Товар/услуга/работа",
]


def _row(subsidy_name, lvl2, lvl3, item_name, unit, qty, price, plan_sum, item_type):
    return [subsidy_name, lvl2, lvl3, item_name, unit, qty, price, plan_sum, item_type]


async def _run_import(db_session, superadmin_user, rows_tail):
    # _mk_xlsx_upload (tests/test_feo_import_item_type_column.py) пишет одну
    # строку данных — для единообразия с остальными тестами модуля собираем
    # книгу тем же приёмом (append), поддерживая и несколько строк.
    import io
    import uuid

    from fastapi import UploadFile
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(_HEADERS)
    for r in rows_tail:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    upload = UploadFile(file=bio, filename=f"import-{uuid.uuid4().hex[:6]}.xlsx")

    return await import_feo_from_excel(
        file=upload, dry_run=False, remap="", apply_remap=False,
        duplicate_resolutions="", item_type_decisions="",
        db=db_session, current_user=superadmin_user,
    )


@pytest.mark.asyncio
async def test_bare_category_plan_sum_creates_no_item(db_session, superadmin_user):
    """Статья 2.12 боевого файла: lvl3 заполнен, «Плановая позиция»/«Товар/
    услуга/работа» пусты, «Сумма плана» = 1 907 229,50 (воспроизводит
    1 907 229,50 без типа, боевой id 19498) — ни позиция, ни план/бюджет
    категории не создаются.

    Координатор, 07.10: охват правила — ПО ФАЙЛУ В ЦЕЛОМ (`_lvl5_column_
    in_use` в feo_import_apply.py), а не по одной строке — поэтому в файл
    (как и в боевом ДНР, где «Плановая позиция» заполнена у большинства
    строк) добавлена вторая, «нормальная» строка-позиция; без неё колонка
    считалась бы вообще не используемой в этом импорте и правило 0.5 не
    применялось бы (см. test_feo_import_category_rows_legacy_no_item_column
    ниже — ОБРАТНЫЙ случай, когда колонка нигде не использована)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            _row(
                subsidy.name, "Прочие расходы",
                "Расходы закупка товаров, услуг, в том числе проезд, проживание и питание",
                None, "усл", None, None, "1907229.50", None,
            ),
            _row(
                subsidy.name, "Прочие расходы", "Расходы на приобретение ГСМ",
                "Расходы на приобретение ГСМ", "усл", "1", "100000", "100000", "Услуга",
            ),
        ]
        result = await _run_import(db_session, superadmin_user, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        cat = next(
            c for c in cats
            if c.name == "Расходы закупка товаров, услуг, в том числе проезд, проживание и питание"
        )
        items = await _get_items(db_session, cat.id)
        assert items == [], (
            "строка статьи без «Плановой позиции» не должна создавать FeoPlannedItem "
            f"(получено: {[(it.name, it.amount) for it in items]})"
        )
        assert cat.planned_amount is None
        assert cat.budget is None

        kinds = {w["kind"] for w in result["warnings"]}
        assert "category_row_without_item_name" in kinds

        # Соседняя «нормальная» статья с реальной позицией не пострадала.
        gsm_cat = next(c for c in cats if c.name == "Расходы на приобретение ГСМ")
        gsm_items = await _get_items(db_session, gsm_cat.id)
        assert len(gsm_items) == 1
        assert gsm_items[0].amount == 100000
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_legacy_file_without_item_name_column_keeps_old_behavior(db_session, superadmin_user):
    """Координатор, 07.10: если «Плановая позиция» НЕ используется НИГДЕ в
    файле (смета старого устройства — план лежит прямо на строке статьи,
    позиций вообще не бывает), правило шага 0.5 не применяется — строка-
    статья с «Суммой плана» и без имени позиции по‑прежнему создаёт
    FeoPlannedItem с именем категории, как до шага 0.5 (урок проекта:
    feedback_no_logic_keyed_to_optional_level.md — охват правила по файлу в
    целом, не по наличию колонки в одной строке)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            _row(subsidy.name, "Направление", "Категория-смета без позиций", None, "усл", "2", "50000", "100000", None),
        ]
        result = await _run_import(db_session, superadmin_user, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        cat = next(c for c in cats if c.name == "Категория-смета без позиций")
        items = await _get_items(db_session, cat.id)
        assert len(items) == 1, "без колонки «Плановая позиция» в файле — прежнее поведение (позиция с именем статьи)"
        assert items[0].name == "Категория-смета без позиций"
        assert items[0].amount == 100000

        kinds = {w["kind"] for w in result["warnings"]}
        assert "category_row_without_item_name" not in kinds
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_self_declared_category_still_creates_item(db_session, superadmin_user):
    """«Плановая позиция» ЗАПОЛНЕНА тем же именем, что и категория (само-
    объявление, item_name_equals_category) — владелец: «позиции, у которых O
    заполнена именем статьи — настоящие позиции, их не трогать». Поведение
    НЕ меняется этим шагом: позиция создаётся."""
    subsidy = await _make_subsidy(db_session)
    try:
        _name = "Логистика и проживание"
        rows = [
            _row(subsidy.name, _name, "", _name, None, "1", "500000", "500000", None),
        ]
        result = await _run_import(db_session, superadmin_user, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        cat = next(c for c in cats if c.name == _name)
        items = await _get_items(db_session, cat.id)
        assert len(items) == 1, "само-объявленная категория=позиция обязана остаться настоящей позицией"
        assert items[0].amount == 500000
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_unit_column_never_sets_item_type(db_session, superadmin_user):
    """«Ед. изм.» = «усл» (как в строке 32 боевого файла, «Обслуживание ТС»)
    никогда не задаёт item_type — тип либо берётся из «Товар/услуга/работа»,
    либо остаётся пустым."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            _row(subsidy.name, "Направление", "", "Позиция с «усл», без типа", "усл", "1", "100000", "100000", None),
        ]
        result = await _run_import(db_session, superadmin_user, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        cat = next(c for c in cats if c.name == "Направление")
        items = await _get_items(db_session, cat.id)
        assert len(items) == 1
        assert items[0].item_type is None, (
            f"«Ед. изм.»=«усл» не должна задавать тип, получено item_type={items[0].item_type!r}"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_item_type_from_goods_service_work_column(db_session, superadmin_user):
    """«Товар/услуга/работа» = «Товар» — единственный источник item_type."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            _row(subsidy.name, "Направление", "", "Позиция-товар", "шт", "2", "500", "1000", "Товар"),
        ]
        result = await _run_import(db_session, superadmin_user, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        cat = next(c for c in cats if c.name == "Направление")
        items = await _get_items(db_session, cat.id)
        assert len(items) == 1
        assert items[0].item_type == "товар"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
