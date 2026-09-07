"""Импорт/экспорт дерева категорий ФЭО из/в Excel (+PDF/DOCX/XLS для предпросмотра).

Разрезано из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения. Все пять путей — статичные (без {cat_id}) и обязаны
регистрироваться в app/routes.py ДО feo_categories.router (несёт catch-all
GET/PUT/DELETE "/{cat_id}") — иначе Starlette матчит их на catch-all раньше.

Тяжёлое ядро парсинга (_do_feo_import) вынесено в
app/services/feo_import_engine.py — этот модуль только определяет колонки
файла и передаёт готовые индексы туда. Гейты записи зовутся через
`from app.routers import feo_categories as fc` — так monkeypatch
`fc._require_feo_category_write` в тестах продолжает работать независимо от
того, в каком файле реально живёт вызывающий обработчик.

_relink_feo_category/_feo_category_load живут здесь (не в ядре) — их
единственный вызывающий код, _do_feo_import, импортирует их ЛОКАЛЬНО (внутри
функции), а не на уровне модуля services/feo_import_engine.py, чтобы не
получить цикл (этот модуль сам импортирует _do_feo_import ИЗ
feo_import_engine на уровне модуля, для /import и /import-mapped ниже).
"""
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
except ImportError:
    Workbook = None
    load_workbook = None
    DataValidation = None

from app.database import get_db
from app.models.feo_category import FeoCategory
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.auth.visibility import get_visible_subsidy_ids
from app.utils.http import content_disposition
from app.routers import feo_categories as fc
from app.services.feo_import_engine import _do_feo_import

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


_content_disposition = content_disposition


@router.get("/import/template")
async def download_feo_template(
    subsidy_id: Optional[int] = Query(
        None,
        description=(
            "Если передан — шаблон делается ПОД ЭТУ субсидию: колонка «Субсидия» в "
            "примерах = её имя, строки-примеры используют её РЕАЛЬНЫЕ названия "
            "уровней, а колонки «Уровень 2/3/4» получают выпадающий список из "
            "реальных категорий этой субсидии (лист «Справочники»). Без параметра — "
            "общий шаблон с нейтральными примерами, без выпадающих списков по уровням."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Шаблон Excel для импорта категорий ФЭО (18 колонок, переверстан 2026-08-14;
    subsidy_id + выпадающие списки по категориям добавлены 2026-09-04).

    Причина переверстки (боевой файл владельца, «Субсидия ДНР 2.xlsx»): в
    37-колоночном шаблоне между заголовком уровня и его числовыми колонками
    стояло по семь числовых колонок — легко промахнуться и набрать название
    следующего уровня в числовой колонке предыдущего (см. level_name_in_number_column
    в _do_feo_import). Новый шаблон разводит уровни (только названия, 4 колонки)
    и числа (2 ОДНА-на-всю-строку пары колонок «по ФЭО»/«плана», а не по 12
    числовых колонок на каждый уровень) — числа сами прикрепляются к самому
    глубокому заполненному уровню строки, либо к плановой позиции, если она
    заполнена (колонка 5).

    Колонки: Субсидия | Уровень 2 | Уровень 3 | Уровень 4 | Плановая позиция
    (папка НЕ создаётся) | Товар/услуга | Количество/Ед.изм./Цена/Сумма по ФЭО
    (одна пара на строку) | Плановое количество/Ед.изм./Цена/Сумма плана (одна
    пара на строку) | Код | Приложение | Активна | Финансирование (устар.).
    Если уровень пропущен, содержимое нижнего поднимается на его место. Если в
    строке нет ни одного уровня, а плановая позиция заполнена — её название
    становится Уровнем 2. Сумма строки приоритетнее кол-во × цена; расхождение —
    предупреждение. Второй лист «Как заполнять» — текстовые правила.

    2026-09-04 (владелец): раньше примеры ВСЕГДА были зашиты строками с именем
    «ДНР_2026» и её реальными уровнями — при скачивании шаблона из ЛЮБОЙ другой
    субсидии (например, ЦентрПоиск_2026) пользователь путал чужие уровни/название
    со своими. Теперь: subsidy_id передан → примеры и списки строятся из дерева
    ЭТОЙ субсидии; не передан → нейтральный заполнитель «Название вашей субсидии»,
    никакого чужого имени/уровней.
    """
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    from app.models.subsidy import Subsidy

    subsidy: Optional[Subsidy] = None
    # db level 1/2/3 = UI «Уровень 2/3/4» (см. find_or_create/db_level в _do_feo_import).
    cats_by_level: dict[int, list[FeoCategory]] = {1: [], 2: [], 3: []}
    cats_by_id: dict[int, FeoCategory] = {}
    if subsidy_id is not None:
        subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
        if subsidy is None:
            raise HTTPException(404, "Субсидия не найдена")
        # Та же видимость, что и у списка/дерева категорий (list_categories/category_tree):
        # доступ к субсидии по вкладке ФЭО ИЛИ заявок ИЛИ закупок.
        vis = await get_visible_subsidy_ids(current_user, db, "feo_categories")
        if vis is not None:
            vis = vis | await get_visible_subsidy_ids(current_user, db, "purchases")
            vis = vis | await get_visible_subsidy_ids(current_user, db, "wishes")
            if subsidy_id not in vis:
                raise HTTPException(403, "Нет доступа к этой субсидии")
        cats_q = (
            select(FeoCategory)
            .where(FeoCategory.subsidy_id == subsidy_id, FeoCategory.is_active.is_(True))
            .order_by(FeoCategory.level, FeoCategory.sort_order.nulls_last(), FeoCategory.id)
        )
        all_cats = (await db.execute(cats_q)).scalars().all()
        cats_by_id = {c.id: c for c in all_cats}
        for c in all_cats:
            if c.level in cats_by_level:
                cats_by_level[c.level].append(c)

    wb = Workbook()
    ws = wb.active
    ws.title = "Категории ФЭО"
    headers = [
        "Субсидия",                                          # A   1
        "Уровень 2 (Направление расходов по ФЭО)",           # B   2
        "Уровень 3 (Тип расходов по ФЭО)",                    # C   3
        "Уровень 4 (Конкретизированный)",                     # D   4
        "Плановая позиция (папка НЕ создаётся)",              # E   5
        "Товар/услуга",                                       # F   6
        "Количество по ФЭО",                                  # G   7
        "Ед. изм. по ФЭО",                                    # H   8
        "Цена за единицу по ФЭО",                             # I   9
        "Сумма по ФЭО",                                       # J  10
        "Плановое количество",                                # K  11
        "Ед. изм. плана",                                     # L  12
        "Плановая цена за единицу",                           # M  13
        "Сумма плана",                                        # N  14
        "Код",                                                # O  15
        "Приложение",                                         # P  16
        "Активна",                                            # Q  17
        "Финансирование (устар., можно не заполнять)",        # R  18
    ]
    ws.append(headers)

    # Цветовое кодирование заголовков
    fill_cat  = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")   # синий — субсидия/уровни + ФЭО
    fill_plan = PatternFill(start_color="0891B2", end_color="0891B2", fill_type="solid")   # голубой — план
    fill_item = PatternFill(start_color="059669", end_color="059669", fill_type="solid")   # зелёный — плановая позиция
    fill_attr = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")   # фиолетовый — атрибуты
    font_w = Font(color="FFFFFF", bold=True, size=10)

    _blue_cols  = {1, 2, 3, 4, 7, 8, 9, 10}    # субсидия, уровни, «по ФЭО» (одна пара на строку)
    _cyan_cols  = {11, 12, 13, 14}             # план (одна пара на строку)
    _green_cols = {5, 6}                       # плановая позиция + тип

    for i, cell in enumerate(ws[1], start=1):
        if i in _blue_cols:
            cell.fill = fill_cat
        elif i in _cyan_cols:
            cell.fill = fill_plan
        elif i in _green_cols:
            cell.fill = fill_item
        else:
            cell.fill = fill_attr
        cell.font = font_w
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 40

    # Примеры (строки 2..N), 18 элементов каждая:
    # col: 1=Субс 2=Ур2 3=Ур3 4=Ур4 5=Плановая_позиция 6=Тип 7=feoQ 8=feoU 9=feoЦена 10=feoСумма 11=planQ 12=planU 13=planЦена 14=planСумма 15=Код 16=Прил 17=Акт 18=Финанс(устар.)
    #
    # 2026-09-04 (владелец): раньше здесь стояло жёстко «ДНР_2026» с её реальными
    # уровнями — при открытии шаблона из ЛЮБОЙ другой субсидии пользователь видел
    # чужие название/уровни и путался. Теперь: если subsidy_id передан и у субсидии
    # УЖЕ есть категории — примеры строятся из её РЕАЛЬНОГО дерева (по одному
    # примеру на глубину, где эта глубина существует). Иначе (subsidy_id не передан,
    # либо у субсидии дерево ещё пустое) — нейтральный нейтральный нейтральный заполнитель, никакой чужой субсидии.
    subsidy_label = subsidy.name if subsidy is not None else "Название вашей субсидии"

    def _path_names(cat: FeoCategory) -> tuple[str, str, str]:
        """(имя Ур.2, Ур.3, Ур.4) для цепочки cat → его родителей (пусто, если родителя нет на этом уровне)."""
        chain: list[FeoCategory] = []
        cur: Optional[FeoCategory] = cat
        seen: set[int] = set()
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            chain.append(cur)
            cur = cats_by_id.get(cur.parent_id) if cur.parent_id else None
        chain.reverse()  # от корня (Ур.2) к листу
        names = [c.name for c in chain]
        while len(names) < 3:
            names.append("")
        return names[0], names[1], names[2]

    example_rows: list[list] = []
    has_real_tree = bool(cats_by_level[1] or cats_by_level[2] or cats_by_level[3])
    if subsidy is not None and has_real_tree:
        if cats_by_level[1]:
            leaf = cats_by_level[1][0]
            n1, n2, n3 = _path_names(leaf)
            example_rows.append([
                subsidy_label, n1, n2, n3, "", "", "", "", "", "2000000", "", "", "", "",
                leaf.code or "", leaf.appendix or "", "да" if leaf.is_active else "нет", "",
            ])
        if cats_by_level[2]:
            leaf = cats_by_level[2][0]
            n1, n2, n3 = _path_names(leaf)
            example_rows.append([
                subsidy_label, n1, n2, n3, "", "", "6", "шт", "150000", "", "6", "шт", "150000", "900000",
                leaf.code or "", leaf.appendix or "", "да" if leaf.is_active else "нет", "",
            ])
        if cats_by_level[3]:
            leaf = cats_by_level[3][0]
            n1, n2, n3 = _path_names(leaf)
            example_rows.append([
                subsidy_label, n1, n2, n3, "", "", "", "", "", "", "1", "усл", "178779.59", "178779.59",
                leaf.code or "", leaf.appendix or "", "да" if leaf.is_active else "нет", "",
            ])
    else:
        # Общий шаблон (нет subsidy_id) ИЛИ субсидия передана, но дерево у неё ещё
        # пустое — реальных уровней показать нечего, только условные подписи.
        example_rows.extend([
            [subsidy_label, "Пример: Техническое оснащение", "Пример: Оргтехника", "", "", "", "", "", "", "2000000", "", "", "", "", "01.01.01", "Прил. 1", "да", ""],
            [subsidy_label, "Пример: Техническое оснащение", "Пример: Оргтехника", "Пример: Закупка компьютеров", "", "", "6", "шт", "150000", "", "6", "шт", "150000", "900000", "01.01.02", "Прил. 1", "да", ""],
        ])
    # Эти две строки — условные во всех случаях (демонстрируют «Плановую позицию»
    # и план без разбивки на уровни, а не сами уровни ФЭО) — реальных категорий не касаются.
    example_rows.append([subsidy_label, "", "", "", "Пример: Услуга по заправке техники", "Услуга", "", "", "", "", "500", "л", "60", "30000", "", "", "да", ""])
    example_rows.append([subsidy_label, "Пример: Организация мероприятий", "Пример: Слёт студентов", "", "", "", "", "", "", "", "", "", "", "3500000", "02.02.01", "Прил. 2", "да", ""])

    for row in example_rows:
        ws.append(row)

    # Подсказки в строке 7
    hints = [
        "← Точное название как в системе",                                                              # A   1
        "← Направление расходов (создаётся если нет)",                                                  # B   2
        "← Тип расходов (если пусто — атрибуты к Ур.2); пропущенный уровень поднимается вверх",          # C   3
        "← Конкретизированный (если пусто — к Ур.3); пропущенный уровень поднимается вверх",             # D   4
        "← Плановая позиция — папка НЕ создаётся; если уровней в строке вовсе нет, станет Уровнем 2",    # E   5
        "← Товар / Услуга / Работа (выпадающий список)",                                                 # F   6
        "← Кол-во по ФЭО — одна колонка на строку, привязывается к самому глубокому уровню",             # G   7
        "← Ед. изм. по ФЭО",                                                                              # H   8
        "← Цена за единицу по ФЭО (руб.)",                                                                # I   9
        "← Сумма по ФЭО (руб.); если пусто — кол-во × цена; сумма приоритетнее",                          # J  10
        "← Плановое кол-во — одна колонка на строку; если задана «Плановая позиция», уходит в неё",       # K  11
        "← Ед. изм. плана",                                                                               # L  12
        "← Плановая цена за единицу (руб.)",                                                              # M  13
        "← Сумма плана (руб.); если пусто — кол-во × цена; сумма приоритетнее",                           # N  14
        "← Код категории",                                                                                # O  15
        "← Номер приложения",                                                                             # P  16
        "← да/нет",                                                                                       # Q  17
        "← устарело, можно не заполнять — используйте «Сумма по ФЭО»",                                    # R  18
    ]
    for col, hint in enumerate(hints, start=1):
        ws.cell(7, col).value = hint
        ws.cell(7, col).font = Font(italic=True, color="888888", size=8)

    # Ширины колонок (18 штук)
    col_widths = [18, 42, 42, 42, 42, 14, 16, 14, 16, 16, 16, 14, 16, 16, 10, 12, 10, 22]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"

    # Выпадающий список Товар/Услуга/Работа на колонку F (Товар/услуга), строки данных 2:1000.
    if DataValidation is not None:
        dv_item_type = DataValidation(
            type="list",
            formula1='"Товар,Услуга,Работа"',
            allow_blank=True,
            showErrorMessage=False,
            showInputMessage=True,
        )
        dv_item_type.error = "Значение не из списка — будет принято как есть"
        dv_item_type.errorTitle = "Нестандартное значение"
        dv_item_type.promptTitle = "Товар/услуга"
        dv_item_type.prompt = "Выберите Товар, Услуга или Работа"
        dv_item_type.sqref = "F2:F1000"
        ws.add_data_validation(dv_item_type)

    # Лист «Справочники» + выпадающие списки по колонкам Уровень 2/3/4 (только
    # когда subsidy_id передан и у субсидии УЖЕ есть хоть одна категория —
    # 2026-09-04). Список — ПОДСКАЗКА, не запрет: через этот шаблон заводят и
    # НОВЫЕ категории, поэтому showErrorMessage=False (как у dv_item_type выше).
    # Инлайн-список (formula1='"a,b,c"') не годится — Excel режет его на ~255
    # символах, категорий может быть больше, поэтому список живёт на отдельном
    # листе, а формула ссылается на диапазон.
    if subsidy is not None and has_real_tree and DataValidation is not None:
        ws3 = wb.create_sheet("Справочники")
        level_ref_cols = {1: "A", 2: "B", 3: "C"}   # колонки листа "Справочники"
        level_titles = {1: "Уровень 2", 2: "Уровень 3", 3: "Уровень 4"}
        level_target_cols = {1: "B", 2: "C", 3: "D"}  # колонки листа "Категории ФЭО"
        for lvl, col_letter in level_ref_cols.items():
            cell = ws3[f"{col_letter}1"]
            cell.value = level_titles[lvl]
            cell.font = Font(bold=True)
            ws3.column_dimensions[col_letter].width = 42
        for lvl, ref_col in level_ref_cols.items():
            names = sorted(dict.fromkeys(c.name for c in cats_by_level[lvl] if c.name))
            for i, name in enumerate(names, start=2):
                ws3[f"{ref_col}{i}"] = name
            if not names:
                continue  # у субсидии нет категорий этого уровня — список не вешаем
            last_row = len(names) + 1 + 50  # запас с рядом, чтобы список не обрезался
            dv_level = DataValidation(
                type="list",
                formula1=f"Справочники!${ref_col}$2:${ref_col}${last_row}",
                allow_blank=True,
                showErrorMessage=False,
                showInputMessage=True,
            )
            dv_level.error = "Значение не из списка — можно ввести и новую категорию"
            dv_level.errorTitle = "Нестандартное значение"
            dv_level.promptTitle = level_titles[lvl]
            dv_level.prompt = f"Выберите существующую категорию «{level_titles[lvl]}» или впишите новую"
            target_col = level_target_cols[lvl]
            dv_level.sqref = f"{target_col}2:{target_col}1000"
            ws.add_data_validation(dv_level)

    # Второй лист — текстовые правила заполнения.
    ws2 = wb.create_sheet("Как заполнять")
    ws2.column_dimensions["A"].width = 110
    rules = [
        "Как заполнять шаблон импорта направлений ФЭО",
        "",
        "1. Уровни (Уровень 2 → Уровень 3 → Уровень 4) идут СЛЕВА НАПРАВО. Уровень 2 — обязателен.",
        "2. Пропущенный уровень поджимается вверх: заполнены Уровень 2 и Уровень 4, а Уровень 3 пуст — Уровень 4 становится ребёнком Уровня 2 напрямую.",
        "3. «Плановая позиция» (колонка 5) — конкретный товар/услуга/работа ВНУТРИ категории. Заполненная «Плановая позиция» папку (категорию) НЕ создаёт — только позицию.",
        "4. Если в строке не заполнен НИ ОДИН из уровней (2/3/4), а «Плановая позиция» заполнена — её название становится Уровнем 2 (создаётся направлением), а позиция при этом не создаётся.",
        "5. «Количество/Ед.изм./Цена/Сумма по ФЭО» и «Плановое количество/Ед.изм./Цена/Сумма плана» — ОДНА пара колонок на всю строку, а не по уровням. Если «Плановая позиция» не задана — числа привязываются к самому глубокому заполненному уровню строки. Если позиция задана — числа плана описывают именно её.",
        "6. Сумма (по ФЭО / плана) ПРИОРИТЕТНЕЕ «количество × цена»: если сумма указана явно — используется она; расхождение с расчётом по кол-во × цена попадёт в предупреждения импорта.",
        "7. «Товар/услуга» (колонка 6) — тип плановой позиции: Товар, Услуга или Работа (выпадающий список в ячейке).",
        "8. Не меняйте заголовки колонок — импорт определяет их по названию, а не по порядку.",
        "9. Строка-подсказка (начинается с «←», строка 7 примера) в файл не попадает — служебная, игнорируется при импорте.",
    ]
    for line in rules:
        ws2.append([line])
    ws2["A1"].font = Font(bold=True, size=12)

    wb.active = 0
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition("Шаблон_импорта_направлений_ФЭО.xlsx")})


@router.post("/import-preview")
async def feo_import_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Read Excel/DOCX file and return headers + sample rows for column mapping."""
    # B2: файл ещё не связан с конкретной субсидией на этом шаге (маппинг колонок
    # выбирается ПОСЛЕ) — subsidy_id=None, право проверяется по любой доступной орге.
    await fc._require_feo_category_write(current_user, db, None)
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".docx", ".doc", ".pdf")):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .docx, .pdf")

    content = await file.read()

    _FEO_HINTS = (
        "субсидия", "наименован", "направлен", "расходов", "уровень",
        "код", "финансирован", "количеств", "ед. изм", "ед.изм",
        "активн", "приложен", "бюджет", "плановый", "тип расх",
    )

    def _detect_hdr(rows):
        best_score, best_idx = 0, 0
        for ri, row in enumerate(rows[:20]):
            norm = [str(h).strip().lower() if h is not None else "" for h in row]
            score = sum(1 for h in norm if h and any(x in h for x in _FEO_HINTS))
            if score > best_score:
                best_score = score
                best_idx = ri
        return best_idx

    try:
        # ── PDF ──
        if fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь таблицы из PDF")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "PDF", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── DOCX ──
        if fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
            if not all_rows:
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text:
                        all_rows.append([text])
            if not all_rows:
                raise HTTPException(400, "Не удалось извлечь данные из документа")
            hdr_idx = _detect_hdr(all_rows)
            headers = [str(h).strip() if h else f"Столбец {j+1}" for j, h in enumerate(all_rows[hdr_idx])]
            data = all_rows[hdr_idx + 1:]
            sample = [[str(c) if c else "" for c in r] for r in data[:5]]
            return {"sheets": [{"name": "Document", "headers": headers, "sample": sample, "total_rows": len(data), "header_row_offset": hdr_idx}]}

        # ── XLS ──
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            sheets = []
            for sheet_name in wb_xls.sheet_names():
                ws_xls = wb_xls.sheet_by_name(sheet_name)
                all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": ws_xls.nrows - hdr_idx - 1, "header_row_offset": hdr_idx})

        # ── XLSX ──
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
            sheets = []
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                all_rows = list(ws.iter_rows(values_only=True))
                if not all_rows:
                    continue
                hdr_idx = _detect_hdr(all_rows)
                hdr_rows = all_rows[hdr_idx:]
                if not hdr_rows:
                    continue
                headers = [str(c).strip() if c else f"Столбец {j+1}" for j, c in enumerate(hdr_rows[0])]
                sample = [[str(c).strip() if c is not None else "" for c in row] for row in hdr_rows[1:min(6, len(hdr_rows))]]
                sheets.append({"name": sheet_name, "headers": headers, "sample": sample,
                               "total_rows": len(all_rows) - hdr_idx - 1, "header_row_offset": hdr_idx})
            wb.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл ({file.filename}): {e}")

    if not sheets:
        raise HTTPException(400, "Файл не содержит листов с данными")

    return {"sheets": sheets}


@router.post("/import")
async def import_feo_from_excel(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    remap: str = Query(""),
    apply_remap: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Импорт категорий ФЭО из Excel.
    Формат: Субсидия | Уровень 2 | Уровень 3 | Уровень 4 | Код | Приложение | Финансирование | Активна
    Каждая строка задаёт путь в иерархии. Промежуточные узлы создаются автоматически.
    Код/Приложение/Финансирование/Активна применяются к самому глубокому указанному уровню.
    dry_run=true: возвращает {created, updated, skipped, errors, warnings} без записи в БД.
    Переезд (remap) несопоставленных узлов и удаление опустевших старых узлов выполняются
    только при apply_remap=true; иначе выполняется только анализ (unmatched/new_paths).
    Возвращает {created, updated, skipped, errors, warnings}."""
    # B2: субсидия — построчная колонка внутри файла (может касаться нескольких
    # субсидий за один импорт), единого subsidy_id на уровне запроса нет.
    # Это ТОЛЬКО дешёвый предварительный фильтр («есть ли право хоть где-то» —
    # отсекает пользователей без feo_category.edit вообще, до чтения файла).
    # Авторитетная проверка — ПО КАЖДОЙ реально резолвящейся субсидии файла —
    # происходит внутри _do_feo_import (_require_feo_import_write, ДО первой
    # записи в БД); дыра импорта была именно в отсутствии этой второй проверки.
    await fc._require_feo_category_write(current_user, db, None)
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только .xlsx и .xls")

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    # Определяем индексы столбцов по заголовку строки 1
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    # Каждая колонка достаётся ровно одному полю
    _used_cols: set[int] = set()

    def find_col(keywords: list[str]) -> int | None:
        for kw in keywords:
            for i, h in enumerate(raw_headers):
                if i in _used_cols:
                    continue
                if kw in h:
                    _used_cols.add(i)
                    return i
        return None

    c_subsidy  = find_col(["субсидия"])
    c_lvl2     = find_col(["уровень 2", "направление расходов", "level 2"])
    c_lvl3     = find_col(["уровень 3", "тип расходов", "level 3"])
    c_lvl4     = find_col(["уровень 4", "конкретизир", "level 4"])
    c_lvl5     = find_col(["плановая позиция", "уровень 5", "плановый товар", "level 5"])
    c_qty      = find_col(["количество (ур.5)", "количество ур.5", "кол-во (ур.5)", "кол-во ур.5"])
    # Новый шаблон: «кол-во по фэо» — feo_quantity
    c_feo_qty_lvl2  = find_col(["кол-во по фэо (ур.2)", "кол-во по фэо ур.2"])
    c_feo_qty_lvl3  = find_col(["кол-во по фэо (ур.3)", "кол-во по фэо ур.3"])
    c_feo_qty_lvl4  = find_col(["кол-во по фэо (ур.4)", "кол-во по фэо ур.4"])
    c_feo_unit_lvl2 = find_col(["ед. изм. по фэо (ур.2)", "ед. изм. по фэо ур.2"])
    c_feo_unit_lvl3 = find_col(["ед. изм. по фэо (ур.3)", "ед. изм. по фэо ур.3"])
    c_feo_unit_lvl4 = find_col(["ед. изм. по фэо (ур.4)", "ед. изм. по фэо ур.4"])
    c_feo_amt_lvl2  = find_col(["стоимость по фэо (ур.2)", "стоимость по фэо ур.2"])
    c_feo_amt_lvl3  = find_col(["стоимость по фэо (ур.3)", "стоимость по фэо ур.3"])
    c_feo_amt_lvl4  = find_col(["стоимость по фэо (ур.4)", "стоимость по фэо ур.4"])
    # Сумма по ФЭО (итог строки) — НОВЫЕ колонки; НЕ путать со стоимостью за ед.
    c_feo_sum_lvl2  = find_col(["сумма по фэо (ур.2)", "сумма по фэо ур.2"])
    c_feo_sum_lvl3  = find_col(["сумма по фэо (ур.3)", "сумма по фэо ур.3"])
    c_feo_sum_lvl4  = find_col(["сумма по фэо (ур.4)", "сумма по фэо ур.4"])
    # Плановое кол-во (CRM-план)
    c_qty_lvl2 = find_col(["плановое кол-во (ур.2)", "плановое кол-во ур.2", "кол-во (ур.2)", "кол-во ур.2", "количество (ур.2)"])
    c_qty_lvl3 = find_col(["плановое кол-во (ур.3)", "плановое кол-во ур.3", "кол-во (ур.3)", "кол-во ур.3", "количество (ур.3)"])
    c_qty_lvl4 = find_col(["плановое кол-во (ур.4)", "плановое кол-во ур.4", "кол-во (ур.4)", "кол-во ур.4", "количество (ур.4)"])
    c_unit_lvl2 = find_col(["ед. изм. плана (ур.2)", "ед. изм. плана ур.2", "ед. изм. (ур.2)", "ед.изм. ур.2", "единица ур.2"])
    c_unit_lvl3 = find_col(["ед. изм. плана (ур.3)", "ед. изм. плана ур.3", "ед. изм. (ур.3)", "ед.изм. ур.3", "единица ур.3"])
    c_unit_lvl4 = find_col(["ед. изм. плана (ур.4)", "ед. изм. плана ур.4", "ед. изм. (ур.4)", "ед.изм. ур.4", "единица ур.4"])
    # Плановая стоимость за ед. — НЕ путать с «сумма плана»
    c_amt_lvl2 = find_col(["плановая стоимость за ед. (ур.2)", "плановая стоимость (ур.2)", "стоимость за ед. (ур.2)", "стоимость ур.2"])
    c_amt_lvl3 = find_col(["плановая стоимость за ед. (ур.3)", "плановая стоимость (ур.3)", "стоимость за ед. (ур.3)", "стоимость ур.3"])
    c_amt_lvl4 = find_col(["плановая стоимость за ед. (ур.4)", "плановая стоимость (ур.4)", "стоимость за ед. (ур.4)", "стоимость ур.4"])
    # Сумма плана — отдельные колонки; старые алиасы «плановая сумма / сумма ур.N» сюда, а НЕ в c_amt_lvl*
    c_plan_sum_lvl2 = find_col(["сумма плана (ур.2)", "плановая сумма (ур.2)", "сумма ур.2"])
    c_plan_sum_lvl3 = find_col(["сумма плана (ур.3)", "плановая сумма (ур.3)", "сумма ур.3"])
    c_plan_sum_lvl4 = find_col(["сумма плана (ур.4)", "плановая сумма (ур.4)", "сумма ур.4"])
    # Новый плоский 18-колоночный шаблон (2026-08-14): числа по ФЭО/плану — ОДНА
    # пара колонок на всю строку (не по уровням), см. _do_feo_import, блок «плоские
    # числа». Объявлены ПОСЛЕ всех per-level find_col выше и ДО generic-фолбэков
    # ниже (c_qty/c_unit) — иначе более общие ключи перехватили бы эти колонки
    # раньше специфичных. На старых 37-колоночных файлах колонки этих названий нет
    # (там «Кол-во по ФЭО (Ур.N)» уже разобран per-level выше и помечен used) — эти
    # find_col останутся None, старое поведение не меняется.
    c_row_feo_qty    = find_col(["количество по фэо"])
    c_row_feo_unit   = find_col(["ед. изм. по фэо"])
    c_row_feo_price  = find_col(["цена за единицу по фэо", "цена за ед. по фэо"])
    c_row_feo_sum    = find_col(["сумма по фэо"])
    c_row_plan_qty   = find_col(["плановое количество"])
    c_row_plan_unit  = find_col(["ед. изм. плана"])
    c_row_plan_price = find_col(["плановая цена за единицу", "плановая цена за ед."])
    c_row_plan_sum   = find_col(["сумма плана"])
    c_item_type      = find_col(["товар/услуга", "тип позиции"])
    # Fallback: generic qty column if no specific level columns present
    if c_qty is None and c_qty_lvl2 is None and c_qty_lvl3 is None and c_qty_lvl4 is None and c_feo_qty_lvl2 is None and c_feo_qty_lvl3 is None and c_feo_qty_lvl4 is None:
        c_qty = find_col(["количество", "кол-во", "qty"])
    c_unit      = find_col(["ед. измерения (ур.5)", "ед. изм. (ур.5)", "единица ур.5", "ед. изм", "единица изм", "ед.изм"])
    c_item_price = find_col(["цена за ед. (ур.5)", "цена за ед. ур.5"])
    c_item_amt  = find_col(["сумма по позиции (ур.5)", "сумма (ур.5)", "сумма ур", "плановая стоимость за ед. (ур.5)", "плановая стоимость (ур.5)", "стоимость за ед. (ур.5)", "стоимость ур.5", "сумма плановая"])
    c_code      = find_col(["код"])
    c_appendix  = find_col(["приложение"])
    c_budget    = find_col(["финансирование", "бюджет", "budget"])
    c_active    = find_col(["активна", "активен", "active"])

    return await _do_feo_import(
        rows=rows[1:],
        c_subsidy=c_subsidy, c_lvl2=c_lvl2, c_lvl3=c_lvl3, c_lvl4=c_lvl4,
        c_lvl5=c_lvl5, c_qty=c_qty, c_unit=c_unit, c_item_amt=c_item_amt,
        c_code=c_code, c_appendix=c_appendix, c_budget=c_budget, c_active=c_active,
        c_qty_lvl2=c_qty_lvl2, c_qty_lvl3=c_qty_lvl3, c_qty_lvl4=c_qty_lvl4,
        c_unit_lvl2=c_unit_lvl2, c_unit_lvl3=c_unit_lvl3, c_unit_lvl4=c_unit_lvl4,
        c_amt_lvl2=c_amt_lvl2, c_amt_lvl3=c_amt_lvl3, c_amt_lvl4=c_amt_lvl4,
        c_feo_qty_lvl2=c_feo_qty_lvl2, c_feo_qty_lvl3=c_feo_qty_lvl3, c_feo_qty_lvl4=c_feo_qty_lvl4,
        c_feo_unit_lvl2=c_feo_unit_lvl2, c_feo_unit_lvl3=c_feo_unit_lvl3, c_feo_unit_lvl4=c_feo_unit_lvl4,
        c_feo_amt_lvl2=c_feo_amt_lvl2, c_feo_amt_lvl3=c_feo_amt_lvl3, c_feo_amt_lvl4=c_feo_amt_lvl4,
        c_feo_sum_lvl2=c_feo_sum_lvl2, c_feo_sum_lvl3=c_feo_sum_lvl3, c_feo_sum_lvl4=c_feo_sum_lvl4,
        c_plan_sum_lvl2=c_plan_sum_lvl2, c_plan_sum_lvl3=c_plan_sum_lvl3, c_plan_sum_lvl4=c_plan_sum_lvl4,
        c_item_price=c_item_price,
        c_row_feo_qty=c_row_feo_qty, c_row_feo_unit=c_row_feo_unit,
        c_row_feo_price=c_row_feo_price, c_row_feo_sum=c_row_feo_sum,
        c_row_plan_qty=c_row_plan_qty, c_row_plan_unit=c_row_plan_unit,
        c_row_plan_price=c_row_plan_price, c_row_plan_sum=c_row_plan_sum,
        c_item_type=c_item_type,
        db=db, dry_run=dry_run,
        user=current_user, remap=remap, apply_remap=apply_remap,
    )


@router.post("/import-mapped")
async def import_feo_mapped(
    file: UploadFile = File(...),
    sheet_name: str = Query(""),
    header_row_offset: int = Query(0),
    col_subsidy: int = Query(-1),
    col_lvl2: int = Query(-1),
    col_lvl3: int = Query(-1),
    col_lvl4: int = Query(-1),
    col_lvl5: int = Query(-1),
    col_code: int = Query(-1),
    col_appendix: int = Query(-1),
    col_budget: int = Query(-1),
    col_quantity: int = Query(-1),
    col_unit: int = Query(-1),
    col_item_amt: int = Query(-1),
    col_active: int = Query(-1),
    col_qty_lvl2: int = Query(-1),
    col_qty_lvl3: int = Query(-1),
    col_qty_lvl4: int = Query(-1),
    col_unit_lvl2: int = Query(-1),
    col_unit_lvl3: int = Query(-1),
    col_unit_lvl4: int = Query(-1),
    col_amt_lvl2: int = Query(-1),
    col_amt_lvl3: int = Query(-1),
    col_amt_lvl4: int = Query(-1),
    col_feo_qty_lvl2: int = Query(-1),
    col_feo_qty_lvl3: int = Query(-1),
    col_feo_qty_lvl4: int = Query(-1),
    col_feo_unit_lvl2: int = Query(-1),
    col_feo_unit_lvl3: int = Query(-1),
    col_feo_unit_lvl4: int = Query(-1),
    col_feo_amount_lvl2: int = Query(-1),
    col_feo_amount_lvl3: int = Query(-1),
    col_feo_amount_lvl4: int = Query(-1),
    # Новые параметры — сумма по ФЭО, сумма плана, цена за ед. Ур.5
    col_feo_sum_lvl2: int = Query(-1),
    col_feo_sum_lvl3: int = Query(-1),
    col_feo_sum_lvl4: int = Query(-1),
    col_plan_sum_lvl2: int = Query(-1),
    col_plan_sum_lvl3: int = Query(-1),
    col_plan_sum_lvl4: int = Query(-1),
    col_item_price: int = Query(-1),
    # Новый плоский 18-колоночный шаблон (2026-08-14) — одна пара колонок «по
    # ФЭО»/«плана» на всю строку, плюс тип плановой позиции.
    col_row_feo_qty: int = Query(-1),
    col_row_feo_unit: int = Query(-1),
    col_row_feo_price: int = Query(-1),
    col_row_feo_sum: int = Query(-1),
    col_row_plan_qty: int = Query(-1),
    col_row_plan_unit: int = Query(-1),
    col_row_plan_price: int = Query(-1),
    col_row_plan_sum: int = Query(-1),
    col_item_type: int = Query(-1),
    default_subsidy_id: int = Query(-1),
    dry_run: bool = Query(False),
    remap: str = Query(""),
    apply_remap: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Импорт категорий ФЭО с пользовательским маппингом столбцов.
    dry_run=true: вся обработка выполняется, транзакция откатывается; возвращает предупреждения.
    Переезд (remap) несопоставленных узлов и удаление опустевших старых узлов выполняются
    только при apply_remap=true; иначе выполняется только анализ (unmatched/new_paths).
    """
    if col_lvl2 < 0:
        raise HTTPException(400, "Не указан обязательный столбец: Уровень 2")
    if col_subsidy < 0 and default_subsidy_id <= 0:
        raise HTTPException(400, "Укажите столбец Субсидия или выберите субсидию назначения")

    # B2: если субсидия назначения ОДНА на весь импорт (нет построчной колонки
    # «Субсидия», задан только default_subsidy_id) — проверяем право именно по ней
    # уже здесь (строже и точнее, отказ до чтения файла). Если субсидия построчная
    # (col_subsidy задан) — единого subsidy_id нет, здесь только дешёвый
    # предварительный фильтр «право хоть где-то» (как в /import). В ОБОИХ случаях
    # авторитетная проверка ПО КАЖДОЙ реально резолвящейся субсидии файла (включая
    # default_subsidy_id как построчный фолбэк при заданном col_subsidy — именно
    # тут была дыра) происходит внутри _do_feo_import (_require_feo_import_write),
    # ДО первой записи в БД.
    _gate_subsidy_id = default_subsidy_id if (col_subsidy < 0 and default_subsidy_id > 0) else None
    await fc._require_feo_category_write(current_user, db, _gate_subsidy_id)

    fname = (file.filename or "").lower()
    content = await file.read()

    try:
        if fname.endswith(".xls"):
            try:
                import xlrd as _xlrd_mod
            except ImportError:
                raise HTTPException(500, "xlrd не установлен")
            wb_xls = _xlrd_mod.open_workbook(file_contents=content)
            ws_names = wb_xls.sheet_names()
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws_xls = wb_xls.sheet_by_name(target_sheet)
            all_rows = [list(ws_xls.row_values(i)) for i in range(ws_xls.nrows)]
        elif fname.endswith(".pdf"):
            try:
                import pdfplumber
            except ImportError:
                raise HTTPException(500, "pdfplumber не установлен")
            pdf = pdfplumber.open(BytesIO(content))
            all_rows = []
            for page in pdf.pages:
                for t in (page.extract_tables() or []):
                    if t:
                        all_rows.extend([[str(c).strip() if c else "" for c in row] for row in t])
            pdf.close()
        elif fname.endswith((".docx", ".doc")):
            try:
                from docx import Document as _DDoc
            except ImportError:
                raise HTTPException(500, "python-docx не установлен")
            doc = _DDoc(BytesIO(content))
            all_rows = []
            for table in doc.tables:
                for row in table.rows:
                    all_rows.append([cell.text.strip() for cell in row.cells])
        else:
            if load_workbook is None:
                raise HTTPException(500, "openpyxl не установлен")
            wb = load_workbook(BytesIO(content), data_only=True)
            ws_names = wb.sheetnames
            target_sheet = sheet_name if sheet_name in ws_names else ws_names[0]
            ws = wb[target_sheet]
            all_rows = list(ws.iter_rows(values_only=True))
            wb.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    if len(all_rows) <= header_row_offset + 1:
        raise HTTPException(400, "Файл пустой или не содержит данных после строки заголовка")

    data_rows = all_rows[header_row_offset + 1:]

    return await _do_feo_import(
        rows=data_rows,
        c_subsidy=col_subsidy if col_subsidy >= 0 else None,
        c_lvl2=col_lvl2,
        c_lvl3=col_lvl3 if col_lvl3 >= 0 else None,
        c_lvl4=col_lvl4 if col_lvl4 >= 0 else None,
        c_lvl5=col_lvl5 if col_lvl5 >= 0 else None,
        c_qty=col_quantity if col_quantity >= 0 else None,
        c_unit=col_unit if col_unit >= 0 else None,
        c_item_amt=col_item_amt if col_item_amt >= 0 else None,
        c_code=col_code if col_code >= 0 else None,
        c_appendix=col_appendix if col_appendix >= 0 else None,
        c_budget=col_budget if col_budget >= 0 else None,
        c_active=col_active if col_active >= 0 else None,
        c_qty_lvl2=col_qty_lvl2 if col_qty_lvl2 >= 0 else None,
        c_qty_lvl3=col_qty_lvl3 if col_qty_lvl3 >= 0 else None,
        c_qty_lvl4=col_qty_lvl4 if col_qty_lvl4 >= 0 else None,
        c_unit_lvl2=col_unit_lvl2 if col_unit_lvl2 >= 0 else None,
        c_unit_lvl3=col_unit_lvl3 if col_unit_lvl3 >= 0 else None,
        c_unit_lvl4=col_unit_lvl4 if col_unit_lvl4 >= 0 else None,
        c_amt_lvl2=col_amt_lvl2 if col_amt_lvl2 >= 0 else None,
        c_amt_lvl3=col_amt_lvl3 if col_amt_lvl3 >= 0 else None,
        c_amt_lvl4=col_amt_lvl4 if col_amt_lvl4 >= 0 else None,
        c_feo_qty_lvl2=col_feo_qty_lvl2 if col_feo_qty_lvl2 >= 0 else None,
        c_feo_qty_lvl3=col_feo_qty_lvl3 if col_feo_qty_lvl3 >= 0 else None,
        c_feo_qty_lvl4=col_feo_qty_lvl4 if col_feo_qty_lvl4 >= 0 else None,
        c_feo_unit_lvl2=col_feo_unit_lvl2 if col_feo_unit_lvl2 >= 0 else None,
        c_feo_unit_lvl3=col_feo_unit_lvl3 if col_feo_unit_lvl3 >= 0 else None,
        c_feo_unit_lvl4=col_feo_unit_lvl4 if col_feo_unit_lvl4 >= 0 else None,
        c_feo_amt_lvl2=col_feo_amount_lvl2 if col_feo_amount_lvl2 >= 0 else None,
        c_feo_amt_lvl3=col_feo_amount_lvl3 if col_feo_amount_lvl3 >= 0 else None,
        c_feo_amt_lvl4=col_feo_amount_lvl4 if col_feo_amount_lvl4 >= 0 else None,
        c_feo_sum_lvl2=col_feo_sum_lvl2 if col_feo_sum_lvl2 >= 0 else None,
        c_feo_sum_lvl3=col_feo_sum_lvl3 if col_feo_sum_lvl3 >= 0 else None,
        c_feo_sum_lvl4=col_feo_sum_lvl4 if col_feo_sum_lvl4 >= 0 else None,
        c_plan_sum_lvl2=col_plan_sum_lvl2 if col_plan_sum_lvl2 >= 0 else None,
        c_plan_sum_lvl3=col_plan_sum_lvl3 if col_plan_sum_lvl3 >= 0 else None,
        c_plan_sum_lvl4=col_plan_sum_lvl4 if col_plan_sum_lvl4 >= 0 else None,
        c_item_price=col_item_price if col_item_price >= 0 else None,
        c_row_feo_qty=col_row_feo_qty if col_row_feo_qty >= 0 else None,
        c_row_feo_unit=col_row_feo_unit if col_row_feo_unit >= 0 else None,
        c_row_feo_price=col_row_feo_price if col_row_feo_price >= 0 else None,
        c_row_feo_sum=col_row_feo_sum if col_row_feo_sum >= 0 else None,
        c_row_plan_qty=col_row_plan_qty if col_row_plan_qty >= 0 else None,
        c_row_plan_unit=col_row_plan_unit if col_row_plan_unit >= 0 else None,
        c_row_plan_price=col_row_plan_price if col_row_plan_price >= 0 else None,
        c_row_plan_sum=col_row_plan_sum if col_row_plan_sum >= 0 else None,
        c_item_type=col_item_type if col_item_type >= 0 else None,
        default_subsidy_id=default_subsidy_id if default_subsidy_id > 0 else None,
        db=db, dry_run=dry_run,
        user=current_user, remap=remap, apply_remap=apply_remap,
    )


@router.get("/export")
async def export_feo_to_excel(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Экспорт дерева категорий ФЭО в Excel."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    from app.models.subsidy import Subsidy
    from app.models.purchase import Purchase

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )).scalars().all()

    # purchase totals
    pt_rows = (await db.execute(
        select(Purchase.feo_category_id, func.coalesce(func.sum(Purchase.planned_total_price), 0).label("total"))
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.feo_category_id.isnot(None))
        .group_by(Purchase.feo_category_id)
    )).all()
    purchase_totals = {r.feo_category_id: float(r.total) for r in pt_rows}

    # Build tree
    by_id = {c.id: {"cat": c, "children": []} for c in cats}
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(by_id[c.id])
        else:
            roots.append(by_id[c.id])

    def calc_budget(node):
        c = node["cat"]
        if not node["children"]:
            return float(c.budget) if c.budget is not None else None
        child_sum = sum(v for ch in node["children"] if (v := calc_budget(ch)) is not None)
        return child_sum if any(calc_budget(ch) is not None for ch in node["children"]) else (float(c.budget) if c.budget is not None else None)

    def calc_purchased(node):
        c = node["cat"]
        if not node["children"]:
            return purchase_totals.get(c.id, 0.0)
        return sum(calc_purchased(ch) for ch in node["children"])

    wb = Workbook()
    ws = wb.active
    ws.title = sub.name[:31]

    header_fill = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    l1_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    l2_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    bold_font = Font(bold=True)
    semi_font = Font(bold=False)

    ws.append(["Наименование", "Код", "Прил.", "Финансирование по ФЭО (₽)", "Фактически запланировано (₽)", "Активна"])
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32

    def write_node(node, depth=0):
        c = node["cat"]
        indent = "  " * depth
        budget = calc_budget(node)
        purchased = calc_purchased(node)
        row = [
            indent + c.name,
            c.code or "",
            c.appendix or "",
            budget if budget is not None else "",
            purchased if purchased > 0 else "",
            "Да" if c.is_active else "Нет",
        ]
        ws.append(row)
        r = ws.max_row
        fill = l1_fill if c.level == 1 else (l2_fill if c.level == 2 else None)
        font = bold_font if c.level == 1 else (semi_font)
        for col in range(1, 7):
            cell = ws.cell(r, col)
            if fill:
                cell.fill = fill
            cell.font = font
            if col in (4, 5) and isinstance(cell.value, float):
                cell.number_format = '#,##0.00'
        for ch in node["children"]:
            write_node(ch, depth + 1)

    for root in roots:
        write_node(root)

    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 22
    ws.column_dimensions["F"].width = 10
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = sub.name.replace(" ", "_").replace("/", "-")[:40]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(f"ФЭО_{safe_name}.xlsx")},
    )


async def _relink_feo_category(old_id: int, new_id: int, db: AsyncSession) -> dict:
    """Перевести все ссылки со старой категории на новую. Не коммитит.
    Возвращает счётчик переехавших строк по каждой таблице."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem

    counts: dict[str, int] = {}

    def _rowcount(result) -> int:
        rc = result.rowcount
        return rc if rc and rc > 0 else 0

    result = await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchases"] = _rowcount(result)

    result = await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["purchase_items"] = _rowcount(result)

    result = await db.execute(
        Wish.__table__.update().where(Wish.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wishes"] = _rowcount(result)

    result = await db.execute(
        WishItem.__table__.update().where(WishItem.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["wish_items"] = _rowcount(result)

    result = await db.execute(
        Product.__table__.update().where(Product.feo_category_id == old_id).values(feo_category_id=new_id)
    )
    counts["products"] = _rowcount(result)

    # Плановые позиции — с дедупликацией по имени (регистронезависимо, trim)
    old_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == old_id)
    )).scalars().all()
    new_items = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == new_id)
    )).scalars().all()
    new_by_name = {(i.name or "").strip().lower(): i for i in new_items}

    planned_items_moved = 0
    for item in old_items:
        key = (item.name or "").strip().lower()
        existing = new_by_name.get(key)
        if existing is not None:
            await db.execute(
                PurchaseItem.__table__.update()
                .where(PurchaseItem.feo_planned_item_id == item.id)
                .values(feo_planned_item_id=existing.id)
            )
            await db.execute(
                FeoPlannedItem.__table__.delete().where(FeoPlannedItem.id == item.id)
            )
        else:
            await db.execute(
                FeoPlannedItem.__table__.update()
                .where(FeoPlannedItem.id == item.id)
                .values(feo_category_id=new_id)
            )
            new_by_name[key] = item
        planned_items_moved += 1
    counts["feo_planned_items"] = planned_items_moved

    return counts


async def _feo_category_load(ids: list[int], db: AsyncSession) -> dict:
    """Что висит на переданных категориях: количества по каждой из ссылающихся
    таблиц + список блокирующих закупок с человекочитаемым статусом.
    Позволяет вызывающему решить, пуст ли узел, и показать пользователю причину.

    own_data (2026-08, боевая причина): раньше "пусто" проверялось ТОЛЬКО по
    внешним ссылкам (закупки/позиции/заявки/товары/плановые позиции). Собственные
    данные категории — план (planned_quantity/planned_amount), финансирование
    (budget) и поля ФЭО (feo_quantity/feo_amount) — не считались ничем, поэтому
    категория с планом на 10 130 000 руб., но без единой ссылки, признавалась
    пустой и удалялась молча. Так дважды пропадала с прода категория
    «(DONGFENG) JUNFENG K33». own_data = сколько из переданных id имеют хоть одно
    из этих полей not NULL и не ноль — вызывающий код обязан учитывать его наравне
    с остальными ссылками при решении "пуст ли узел".
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.wish import Wish
    from app.models.wish_item import WishItem
    from app.routers.purchase_transitions import STATUS_LABELS
    from sqlalchemy import or_, and_

    purchases_count = (await db.execute(
        select(func.count(Purchase.id)).where(Purchase.feo_category_id.in_(ids))
    )).scalar_one()
    purchase_items_count = (await db.execute(
        select(func.count(PurchaseItem.id)).where(PurchaseItem.feo_category_id.in_(ids))
    )).scalar_one()
    wishes_count = (await db.execute(
        select(func.count(Wish.id)).where(Wish.feo_category_id.in_(ids))
    )).scalar_one()
    wish_items_count = (await db.execute(
        select(func.count(WishItem.id)).where(WishItem.feo_category_id.in_(ids))
    )).scalar_one()
    products_count = (await db.execute(
        select(func.count(Product.id)).where(Product.feo_category_id.in_(ids))
    )).scalar_one()
    planned_items_count = (await db.execute(
        select(func.count(FeoPlannedItem.id)).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalar_one()
    own_data_count = (await db.execute(
        select(func.count(FeoCategory.id)).where(
            FeoCategory.id.in_(ids),
            or_(
                and_(FeoCategory.budget.isnot(None), FeoCategory.budget != 0),
                and_(FeoCategory.feo_quantity.isnot(None), FeoCategory.feo_quantity != 0),
                and_(FeoCategory.feo_amount.isnot(None), FeoCategory.feo_amount != 0),
                and_(FeoCategory.planned_quantity.isnot(None), FeoCategory.planned_quantity != 0),
                and_(FeoCategory.planned_amount.isnot(None), FeoCategory.planned_amount != 0),
            ),
        )
    )).scalar_one()

    blocking = await fc._collect_blocking_purchases(ids, db)
    purchases_list = [
        {
            "id": p.id,
            "purchase_number": p.purchase_number,
            "subject": p.subject,
            "status": p.status,
            "status_label": STATUS_LABELS.get(p.status, p.status),
        }
        for p in blocking
    ]

    return {
        "purchases": purchases_count,
        "purchase_items": purchase_items_count,
        "wishes": wishes_count,
        "wish_items": wish_items_count,
        "products": products_count,
        "feo_planned_items": planned_items_count,
        "own_data": own_data_count,
        "blocking_purchases": purchases_list,
    }
