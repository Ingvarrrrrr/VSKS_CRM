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


_LEVEL_LABELS = {2: "Уровень 2", 3: "Уровень 3", 4: "Уровень 4", 5: "Товар/услуга"}


def level_label(level_src: int) -> str:
    """Единая пользовательская подпись уровня ФЭО (Правило №6 — одна таблица
    подписей, не строковые литералы «Ур.N» по местам).

    Баг 2026-09-09 (владелец): внутренние сообщения писали «Ур.5», хотя в
    шаблоне (см. app/routers/feo_import_template.py) колонки называются
    «Уровень 2 (Направление расходов по ФЭО)», «Уровень 3 (Тип расходов по
    ФЭО)», «Уровень 4 (Конкретизированный)» — а самый глубокий уровень данных
    (level_src=5 во внутреннем разборе строки) пользователю виден как колонка
    «Товар/услуга», а не как несуществующий «пятый уровень разбивки».
    """
    return _LEVEL_LABELS.get(level_src, f"Уровень {level_src}")
