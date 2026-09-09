"""Чистые хелперы разбора ячеек импорта ФЭО — общие для feo_import_apply.py и
feo_import_plan.py (Правило №6: один источник, не дублировать в каждом
файле-этапе). Вынесены из тела `_do_feo_import` (были ~строки 160–202 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики — только сняты с закрытия функции (были вложенными def,
не обращались ни к чему, кроме своих аргументов и импорта normalize_feo_name).
"""
from decimal import Decimal

from app.utils.text import normalize_feo_name

ZERO = Decimal("0")
QUANT = Decimal("0.01")


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


def fmt(v) -> str:
    """Число с разделителями разрядов для читаемых предупреждений."""
    try:
        return f"{float(v):,.2f}".replace(",", " ")
    except Exception:
        return str(v)


def norm(s: str) -> str:
    """Нормализация имени уровня для сравнения."""
    return normalize_feo_name(s)


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


_LEVEL_LABELS = {2: "Уровень 2", 3: "Уровень 3", 4: "Уровень 4", 5: "Плановая позиция"}


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
        v = to_dec(get_cell(row, col))
        if v:
            return v
    return None
