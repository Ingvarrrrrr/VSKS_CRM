"""Чистые хелперы разбора ячеек импорта ФЭО — общие для feo_import_apply.py и
feo_import_plan.py (Правило №6: один источник, не дублировать в каждом
файле-этапе). Вынесены из тела `_do_feo_import` (были ~строки 160–202 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики — только сняты с закрытия функции (были вложенными def,
не обращались ни к чему, кроме своих аргументов и импорта normalize_feo_name).
"""
from decimal import Decimal

from app.models.feo_category import FeoCategory
from app.services.feo_payroll import is_payroll_name
from app.services.plan_need_level import resolve_need_level_text
from app.utils.text import normalize_feo_name

ZERO = Decimal("0")
QUANT = Decimal("0.01")


async def find_or_create_category(db, cat_cache: dict, subsidy_id: int, parent_id, name: str, level: int):
    """Единственная реализация upsert категории по (subsidy_id, parent_id,
    имя) — Правило №6 (QA, 22.09): раньше был байт-в-байт дублирован как
    вложенный `find_or_create` в feo_import_apply.py и (устаревший путь по
    нумерации A–D, удалён 22.09) — построчный путь создаёт/находит категории
    этой логикой. `cat_cache` — общий кэш вызывающей стороны (ключ —
    тот же кортеж), мутируется на месте."""
    key = (subsidy_id, parent_id, name.lower().strip())
    if key in cat_cache:
        return cat_cache[key], False
    # БАГ ДНР5 id 97 (найден 13.10.2026, план expense-kinds.md): миграция
    # e3f5g7h9i1j3 разово проставила is_payroll по имени для СУЩЕСТВОВАВШИХ
    # на 07.10 категорий, а её докстринг обещал, что дальше новые статьи
    # метит импорт — но ЭТА функция (единственное место, где импорт создаёт
    # FeoCategory, см. докстринг выше) is_payroll вообще не трогала, поэтому
    # статья «ФОТ и иные выплаты персоналу», созданная импортом ПОСЛЕ
    # бэкфилла, осталась is_payroll=false и вся её сумма падала в unspecified.
    # is_payroll_name — тот же единственный источник правила (ПРАВИЛО №6,
    # app.services.feo_payroll), что и у миграции и у ручного переключателя.
    cat = FeoCategory(
        name=name, subsidy_id=subsidy_id, parent_id=parent_id, level=level,
        is_active=True, is_payroll=is_payroll_name(name),
    )
    db.add(cat)
    await db.flush()
    cat_cache[key] = cat
    return cat, True


def get_cell(row, col: int | None) -> str | None:
    if col is None or col < 0:
        return None
    if col >= len(row):
        return None
    v = row[col]
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ('none', 'null'):
        return None
    return s


def to_bool(v: str | None) -> bool:
    if v is None:
        return True
    return v.lower() in ("да", "yes", "true", "1", "+")


def to_dec(v: str | None):
    if not v:
        return None
    s = str(v).strip()
    if not s or s in ('-', '—', '–', 'None', 'null', 'н/д', 'N/A'):
        return None
    s = s.replace(" ", "").replace("\xa0", "").replace(" ", "")
    s = s.replace("₽", "").replace("руб", "").replace("р.", "").replace("р", "")
    s = s.replace(",", ".")
    s = s.rstrip(".")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def to_dec_money(v: str | None):
    """`to_dec`, но для ДЕНЕЖНЫХ ячеек импорта ФЭО (суммы/цены — Правило №6,
    один источник чтения денег: budget, item_plan_amount/price, per-level
    feo_amt/feo_sum/plan_amt/plan_sum, построчные feo/plan price/sum,
    see feo_import_apply.py) — КОЛИЧЕСТВО этой функцией не читается (qty
    остаётся на `to_dec`, см. ниже).

    Повод (прод, 22.10.2026, субсидия ДНР_2026 id 105): ячейка «Сумма» листа
    хранит результат формулы Excel кол-во×цена — `50*34.2` даёт не 1710, а
    1710.0000000000002 (двоичная арифметика float), `3*45452.63` — не
    136357.89, а 136357.88999999998. Колонка numeric(15,2) в БД такое число
    всё равно хранит как 1710.00 — но `_upsert_one` (feo_import_duplicates.py)
    сравнивает СЫРОЕ `Decimal('1710.0000000000002')` из файла с уже
    округлённым `Decimal('1710.00')` из БД, видит неравенство и на КАЖДОМ
    повторном импорте того же файла пишет «обновлено» и лишнюю запись в
    историю, хотя по смыслу сумма не менялась.

    Округление до копейки — ЗДЕСЬ, в точке чтения ячейки, а не в месте
    сравнения: тогда и сравнение в `_upsert_one`, и запись в БД, и любой
    другой код, читающий эти поля дальше по циклу (budget-конфликты,
    collected_plan, предупреждения mismatch), видят одно и то же уже верное
    число — второго места округления не завели (Правило №6)."""
    v = to_dec(v)
    if v is None:
        return None
    return v.quantize(QUANT)


def fmt(v) -> str:
    """Число для читаемых предупреждений: разряды — пробелом, дробная часть —
    запятой (владелец, 10.10.2026: «10 954,41», не «10 954.41» — русский
    десятичный разделитель). Только для текста сообщений — ни в БД, ни в
    ключах/сравнениях эта строка не участвует (см. grep по вызывающим файлам
    при правке — везде используется исключительно внутри f-строки warning's
    "message")."""
    try:
        s = f"{float(v):,.2f}"  # "10,954.41" — запятая=разряды, точка=дробь
        return s.replace(",", " ").replace(".", ",")  # "10 954,41"
    except Exception:
        return str(v)


def norm(s: str) -> str:
    """Нормализация имени уровня для сравнения."""
    return normalize_feo_name(s)


# Правило №6: разбор текста ячейки (код/подпись/синонимы листа владельца)
# целиком живёт в app/services/plan_need_level.py::resolve_need_level_text —
# этот модуль не копирует и не держит свой словарь, только отличает «пусто»
# (дальше трактуется как 'likely' без ошибки) от «мусора» (None —
# вызывающий код, feo_import_apply.py, заводит построчную ошибку).
def normalize_need_level_cell(v: str | None) -> str | None:
    """Ячейка колонки «Нужность» импорта ФЭО -> код need_level, см. докстринг
    resolve_need_level_text в plan_need_level.py."""
    return resolve_need_level_text(v)


def resolve_target_subsidy_id(
    sub_name: str | None, sub_by_name: dict, default_subsidy_id: int | None,
) -> int | None:
    """Единая логика выбора субсидии-назначения строки импорта (Правило №6,
    один источник — используется и feo_import_gate.py, и feo_import_apply.py,
    вместо двух копий одного и того же выражения).

    Баг 2026-09-09 (прод, владелец): новая пустая субсидия «ЦП_2026_2» (открыта
    в карточке, `default_subsidy_id` мастер шлёт ВСЕГДА при импорте из карточки
    субсидии — см. useFeoImport.ts) получала «Будет обновлено: N» при импорте
    шаблона, ранее заполненного под другую субсидию: колонка «Субсидия» файла
    называла ДРУГУЮ существующую субсидию, и старое выражение
    `sub_by_name.get(...) or default_subsidy_id` отдавало приоритет имени из
    файла — строки уходили в чужую субсидию целиком, открытая оставалась
    пустой. Эмпирически проверено (2026-09-09): при имени, которого нет ни в
    одной субсидии, старое выражение и так падало на default_subsidy_id
    (0 неверно созданных/обновлённых); бага не было — но при имени
    СУЩЕСТВУЮЩЕЙ другой субсидии 100% строк уходили ей, ни одной в открытую.

    Открытая субсидия (`default_subsidy_id`) побеждает БЕЗУСЛОВНО, когда она
    задана — колонка «Субсидия» файла в этом случае вообще не маршрутизирует.
    Маршрутизация по имени работает ТОЛЬКО когда `default_subsidy_id` не
    передан вовсе (мультисубсидийный режим — сегодня единственный вызывающий
    путь: самостоятельная страница /api/feo-categories/import без карточки
    субсидии, см. FeoCategoriesView.vue, а не мастер карточки субсидии).
    """
    if default_subsidy_id:
        return default_subsidy_id
    if sub_name and not sub_name.startswith("←"):
        return sub_by_name.get(sub_name.lower().strip())
    return None


def row_is_position(has_own_name: bool, item_column_in_use: bool) -> bool:
    """Правило «эта строка — плановая позиция?» — ОДИН источник для импорта
    ФЭО (`feo_import_apply.py`) и импорта факта (`historical_fact_import/
    rows.py`), Правило №6. Решение владельца: строка без СВОЕЙ «Плановой
    позиции» — статья (категория), а не позиция; старое поведение (строка
    без имени позиции всё равно становится позицией с именем статьи)
    сохраняется только для файлов, где колонки «Плановая позиция» нет вообще
    (`item_column_in_use=False` — ни одна строка файла её не использует).

    `has_own_name` — у ЭТОЙ строки есть собственное значение «Плановой
    позиции» (не подставленное откуда-то, не пустое). `item_column_in_use` —
    в файле ВООБЩЕ есть колонка «Плановая позиция» (хоть где-то заполнена/
    сопоставлена) — т.е. решает факт по файлу целиком, не по одной строке
    (feedback_no_logic_keyed_to_optional_level.md: нельзя включать правило по
    наличию опциональной колонки в конкретной строке).

    Перенесено из `feo_import_apply.py` (было `_row_treat_as_real_position =
    _row_had_own_position_name or not _lvl5_column_in_use`, строки ~405-413)
    без изменения логики — вызывающий код и его тесты не меняются."""
    return has_own_name or not item_column_in_use


def format_rows(rows, max_parts: int = 10) -> str:
    """Компактный список номеров строк файла для текста предупреждений импорта
    ФЭО (задача владельца 2026-09-09: сводные предупреждения — «В файле N
    повторяющихся позиций», «Бюджет родителя ≠ сумма дочерних» — не называли
    ни одной строки, разбор жалобы требовал повторного дебага).

    Подряд идущие номера схлопываются в диапазон «N–M» (например, построчная
    разбивка «Товар/услуга» одной категории — строки 217–245). После
    `max_parts` кусков остаток сворачивается в «и ещё K» (K — сколько строк
    файла не показано явно, а не сколько «кусков» отброшено).

    Правило №6: единственное место форматирования списков строк в
    предупреждениях импорта ФЭО — feo_import_apply.py/feo_import_plan.py
    вызывают эту функцию, а не собирают строку вручную по месту.
    """
    uniq = sorted({r for r in rows if r is not None})
    if not uniq:
        return ""
    ranges: list[tuple[int, int]] = []
    start = prev = uniq[0]
    for r in uniq[1:]:
        if r == prev + 1:
            prev = r
            continue
        ranges.append((start, prev))
        start = prev = r
    ranges.append((start, prev))

    shown = ranges[:max_parts]
    shown_count = sum(b - a + 1 for a, b in shown)
    parts = [str(a) if a == b else f"{a}–{b}" for a, b in shown]
    text = ", ".join(parts)
    remaining = len(uniq) - shown_count
    if remaining > 0:
        text += f" и ещё {remaining}"
    word = "строка" if len(uniq) == 1 else "строки"
    return f"{word} {text}"


# 🟡 Правка 16.10.2026 (задача 1, лист GoodsService владельца, колонка AH
# «Тип расходов конкретизированный (свой)» — 4-й настраиваемый уровень
# категории ПОД Уровнем 4): новый уровень называется level_src=5 («Уровень
# 5»), поэтому «Плановая позиция» (раньше жила на level_src=5 во внутреннем
# разборе строки) сдвинута на level_src=6 — см. 3 места, называющие её
# level_label(6) ниже (feo_import_apply.py/feo_import_duplicates.py/
# feo_import_plan.py). c_lvl5 (колонка «Плановая позиция») сам параметр НЕ
# переименован — только числовая метка level_src в этой подписи.
_LEVEL_LABELS = {2: "Уровень 2", 3: "Уровень 3", 4: "Уровень 4", 5: "Уровень 5", 6: "Плановая позиция"}


def level_label(level_src: int) -> str:
    """Единая пользовательская подпись уровня ФЭО (Правило №6 — одна таблица
    подписей, не строковые литералы «Ур.N» по местам).

    Баг 2026-09-09 (владелец): внутренние сообщения писали «Ур.5», хотя в
    шаблоне (см. app/routers/feo_import_template.py) колонки называются
    «Уровень 2 (Направление расходов по ФЭО)», «Уровень 3 (Тип расходов по
    ФЭО)», «Уровень 4 (Конкретизированный)» — а самый глубокий уровень данных
    (level_src=5 во внутреннем разборе строки) — это колонка «Плановая
    позиция», а не «Товар/услуга» (это СОСЕДНЯЯ колонка-классификатор,
    normalize_item_type) — из-за старой подписи владелец не понял
    предупреждение по строке 248 (задача 2026-09-09, план dreamy-booping-piglet).
    """
    return _LEVEL_LABELS.get(level_src, f"Уровень {level_src}")


def row_feo_money(
    row,
    c_row_feo_sum: int | None,
    c_feo_sum_lvl2: int | None,
    c_feo_sum_lvl3: int | None,
    c_feo_sum_lvl4: int | None,
    c_budget: int | None,
):
    """Первая ненулевая денежная сумма строки импорта ФЭО среди колонок,
    которые могли бы её нести: плоская «Сумма по ФЭО», её per-level варианты
    и легаси «Финансирование» (Правило №6 — единый источник; раньше один и
    тот же перебор был написан дважды в feo_import_apply.py — в ветке
    amount_without_level2 и, отдельно, был нужен продвижению «Плановой
    позиции» в уровень, см. план dreamy-booping-piglet.md, задача A, п.1/2).
    """
    for col in (c_row_feo_sum, c_feo_sum_lvl2, c_feo_sum_lvl3, c_feo_sum_lvl4, c_budget):
        if col is None:
            continue
        v = to_dec_money(get_cell(row, col))
        if v:
            return v
    return None


def row_plan_money(
    row,
    c_row_plan_sum: int | None,
    c_plan_sum_lvl2: int | None,
    c_plan_sum_lvl3: int | None,
    c_plan_sum_lvl4: int | None,
):
    """Сестра `row_feo_money` (Правило №6, единый источник) — первая ненулевая
    сумма ПЛАНА строки среди колонок, которые могли бы её нести: плоская
    «Сумма плана» и её per-level варианты. Нужна там, где у строки есть только
    план, а «Сумма по ФЭО» не задана вовсе — задача владельца 2026-09-09,
    третий разбор: боевой файл, строка 214 («Хозяйственные, административные
    расходы...» объявлена Уровнем 3 в строке 213, но здесь — Плановая позиция
    внутри чужого «Обеспечение топливом...», из денег у строки только Сумма
    плана 200 000, Суммы по ФЭО нет вовсе) — см. item_name_used_as_level в
    feo_import_apply.py, ей нужно назвать именно ПЛАН, если ФЭО у строки нет.
    """
    for col in (c_row_plan_sum, c_plan_sum_lvl2, c_plan_sum_lvl3, c_plan_sum_lvl4):
        if col is None:
            continue
        v = to_dec_money(get_cell(row, col))
        if v:
            return v
    return None


def resolve_origin_flags(feo_money, plan_money) -> tuple[bool, bool]:
    """Единственный источник происхождения плановой позиции (Правило №6) —
    решает, какими должны стоять `FeoPlannedItem.is_feo_breakdown` /
    `is_internal_plan`, по деньгам, которые реально нашлись у строки/позиции
    в разделе ФЭО (`feo_money`, обычно результат `row_feo_money`) и в
    плановом разделе (`plan_money`, обычно `row_plan_money`).

    Задача владельца 2026-09-1x: «по ФЭО» — только когда в разделе ФЭО
    ДЕЙСТВИТЕЛЬНО стоят суммы, а не потому, что позиция попала в ветку кода
    «Плановая позиция файла». Раньше все три места установки признака
    (feo_import_apply.py, feo_import_plan.py, plan_autoassign.py) решали
    безусловно, глядя на то, В КАКУЮ ветку импорта попала строка, а не на то,
    откуда взялись деньги — категория «Питание, в т.ч. закупка продуктов…»,
    заполненная только в плановом разделе, получала шильдик «По ФЭО» просто
    потому, что оказалась Ур.5-строкой файла.

    is_feo_breakdown — в разделе ФЭО есть деньги (`feo_money` непусто/не 0).
    is_internal_plan — в плановом разделе есть деньги, ЛИБО денег нет вовсе
    НИГДЕ (тогда считаем, что позиция заведена вручную и в ФЭО её не было —
    обе галочки ложными быть не должны). Оба признака могут быть True
    одновременно — владелец явно допускает разбивку по ФЭО, у которой есть
    ещё и отдельный (отличающийся) план.

    `plan_autoassign.py` (позиция рождается из реальной закупки/заявки, без
    файла ФЭО вообще) зовёт эту же функцию с `feo_money=None` — у такой
    позиции раздела ФЭО не существует по построению, а не потому что он
    пуст в конкретной строке; повторно писать `has_plan or not has_feo`
    там не нужно — тот же вывод отдаёт эта функция.
    """
    has_feo = bool(feo_money)
    has_plan = bool(plan_money)
    return has_feo, (has_plan or not has_feo)


def build_level_name_index(
    rows,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
) -> dict:
    """Пред-проход по ВСЕМ строкам файла (задача владельца 2026-09-09, вторая
    часть правила — предупреждение, НЕ переклассификация узлов): для каждого
    нормализованного имени, встречающегося ГДЕ-ТО в файле как значение колонки
    уровня (Ур.2/3/4), запомнить ВСЕ пары (уровень, номер строки), где оно
    встречается. Используется потом строкой, у которой то же имя стоит в
    «Плановой позиции» и осталось ПОЗИЦИЕЙ (уровни строки заполнены как обычно,
    дерево НЕ меняем) — чтобы предупредить о человеческом факторе: то же имя
    где-то в файле само является названием уровня, возможно эта строка на
    самом деле подраздел, а не позиция. Владелец решил дерево/суммы не менять
    — файл читается буквально (Ур.3 строки остаётся тем, что в нём написано).

    Боевой пример: строка 211 (Плановая позиция=«Обеспечение топливом при
    работах в зоне гуманитарной помощи», Ур.3=«Межрегиональные перевозки») —
    позиция остаётся внутри «Межрегиональных перевозок», как и было, но то же
    имя «Обеспечение топливом...» стоит как значение Уровня 3 в строке 212 —
    предупреждение показывает обе строки.

    Должен быть вызван ДО основного цикла по строкам — само имя может
    встретиться как значение уровня в строке, которая идёт ПОСЛЕ строки с
    деньгами (211 < 212 в боевом файле, но порядок не гарантирован в общем
    случае).

    Служебные строки-подсказки («← ...») исключаются, как и везде в импорте.

    Возвращает {normalized_name: [(level, row_num), ...]} — список НЕ
    схлопнут ни по уровню, ни по строке; вызывающий код сам решает, что
    показать (см. item_name_used_as_level в feo_import_apply.py).
    """
    occurrences: dict[str, list[tuple[int, int]]] = {}
    for row_num, row in enumerate(rows, start=2):
        lvl2v = get_cell(row, c_lvl2)
        if lvl2v and lvl2v.startswith("←"):
            continue
        for lvl, col in ((2, c_lvl2), (3, c_lvl3), (4, c_lvl4)):
            if col is None:
                continue
            v = get_cell(row, col)
            if not v or v.startswith("←"):
                continue
            occurrences.setdefault(norm(v), []).append((lvl, row_num))
    return occurrences


def find_uniformly_empty_levels(
    rows,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
) -> set[int]:
    """Уровни (2/3/4), чья колонка пуста ВО ВСЕХ строках данных файла — это
    раскладка файла целиком, а не N отдельных построчных аномалий (боевой
    инцидент 2026-09-15, владелец: файл «Абхазия ЦЭМАК (1).xlsx» — «Уровень 2»
    не заполнен ни в одной из 189 строк, категории у него всегда начинаются с
    «Уровень 3»). Единственный источник (Правило №6): используется и для
    одного агрегированного предупреждения `level_column_empty_in_file` вместо
    построчных `level_gap`, и для подавления построчных `level_gap`, целиком
    вызванных именно такой колонкой (см. feo_import_apply.py) — построчный
    `level_gap` остаётся только для разрывов, которых нет во всех строках.

    Пред-проход рядом с `build_level_name_index` (тот же критерий служебной
    строки — «← ...» в Уровне 2 пропускается целиком), а не второй независимый
    цикл где-то ещё в коде. Пустой файл (нет ни одной строки данных) не
    считается «пустой колонкой» — возвращает пустое множество.

    Требует МИНИМУМ 2 строки данных, иначе возвращает пустое множество: при
    одной-единственной строке «пусто во всех строках» и «пусто в этой одной
    строке» неотличимы, а по существующему поведению (test_feo_import_tree.py
    ::test_level_gap_still_collapses_when_no_number_column_involved — Ур.3
    пуст в единственной строке синтетического теста) это ОБЫЧНЫЙ построчный
    разрыв, а не раскладка файла — построчный `level_gap` должен остаться.
    """
    cols = [(2, c_lvl2), (3, c_lvl3), (4, c_lvl4)]
    candidates = {lvl for lvl, col in cols if col is not None}
    seen_rows = 0
    for row in rows:
        lvl2v = get_cell(row, c_lvl2)
        if lvl2v and lvl2v.startswith("←"):
            continue
        seen_rows += 1
        for lvl, col in cols:
            if lvl not in candidates:
                continue
            v = get_cell(row, col)
            if v and not v.startswith("←"):
                candidates.discard(lvl)
        if not candidates:
            break
    if seen_rows < 2:
        return set()
    return candidates
