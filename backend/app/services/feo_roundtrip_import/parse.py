"""Разбор .xlsx файла «Выгрузить ФЭО» для загрузки обратно (задача владельца
20.10.2026). Единственное место, которое знает про структуру файла,
построенного app.services.feo_export_xlsx (ПРАВИЛО №6 — подписи колонок
берутся оттуда же, не копируются строкой по месту).

Формат входа: строки 1–2 — итоги, 3 — заголовки, данные с 4-й (те же
HEADER_ROW/DATA_FIRST_ROW, что и в feo_export_xlsx.py). Набор колонок МОГ
БЫТЬ ЛЮБЫМ (пользователь выбирал при выгрузке) — колонки ищутся по
ЗАГОЛОВКАМ в строке заголовков, а не по номеру. Заголовок ищется в первых 10
строках по ячейке «Наименование» (владелец, п.2) — не обязательно строка 3
(пользователь мог вставить/удалить строку).

Лист `_meta` (скрытый, пишет feo_export_xlsx.py) несёт subsidy_id/
exported_at/format_version — читается здесь в MetaInfo. Файл БЕЗ листа
_meta (набран человеком с нуля, см. задачу владельца п.2 «для новой
субсидии — выгрузите пустой файл, заполните и загрузите») — meta=None, это
НЕ ошибка (см. диалог владельца в PLAN: «пустая субсидия... apply строит
дерево»).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.services.feo_export_columns import FEO_EXPORT_COLUMNS
from app.services.feo_import_common import to_dec

# Колонки, которые реально читает загрузка обратно (остальные —
# Заказано/Надо заказать/Остаток/шесть стадий — литералы/формулы,
# вычисленные на экспорте, игнорируются при чтении, задача владельца, п.2).
READABLE_KEYS = (
    "name", "code", "app", "feo_qty", "feo_unit", "feo", "plan", "active",
    "row_type", "row_id",
)
_LABEL_BY_KEY = {k: label for k, label, _g, _w, _d in FEO_EXPORT_COLUMNS if k in READABLE_KEYS}
# Заголовок -> ключ (нормализован: strip, без учёта регистра — Excel любит
# менять регистр при автозамене/автозаполнении, тот же приём устойчивости,
# что и у остального импорта ФЭО, см. feo_import_common.norm).
_KEY_BY_LABEL_NORM = {label.strip().lower(): k for k, label in _LABEL_BY_KEY.items()}

NAME_HEADER = _LABEL_BY_KEY["name"]
FORMAT_VERSION = "feo-export-1"
_HEADER_SEARCH_ROWS = 10

CATEGORY_TYPES = ("Категория", "Категория без позиций")
POSITION_TYPE = "Позиция"


@dataclass
class ParsedRow:
    row_num: int  # номер строки файла (1-based, как в Excel) — для текстов ошибок
    name: str
    code: Optional[str] = None
    appendix: Optional[str] = None
    feo_qty: Optional[Decimal] = None
    feo_unit: Optional[str] = None
    feo_amount: Optional[Decimal] = None
    plan_amount: Optional[Decimal] = None
    is_active: Optional[bool] = None  # None = ячейка пуста ("не менять"/дефолт)
    row_type_raw: str = ""  # как в файле (может быть пустым — тип выводится)
    row_id_raw: Optional[str] = None  # "c123"/"p45"/None
    outline_level: int = 0
    leading_spaces: int = 0


@dataclass
class MetaInfo:
    subsidy_id: Optional[int]
    exported_at: Optional[str]
    format_version: Optional[str]


@dataclass
class ParseResult:
    rows: list = field(default_factory=list)       # list[ParsedRow]
    meta: Optional[MetaInfo] = None
    errors: list = field(default_factory=list)      # list[str] — ошибки формата файла (400)
    used_outline: bool = False  # True — уровни взяты из outline_level, не из отступов


def _norm_header(s) -> str:
    return str(s).strip().lower() if s is not None else ""


def _find_header_row(ws) -> Optional[int]:
    """Строка заголовков — первая из первых _HEADER_SEARCH_ROWS строк листа,
    где есть ячейка со значением «Наименование» (точное совпадение после
    strip/lower — ПРАВИЛО №6, та же подпись, что в FEO_EXPORT_COLUMNS)."""
    name_norm = NAME_HEADER.strip().lower()
    max_row = min(_HEADER_SEARCH_ROWS, ws.max_row or 0)
    for r in range(1, max_row + 1):
        for c in range(1, (ws.max_column or 0) + 1):
            if _norm_header(ws.cell(row=r, column=c).value) == name_norm:
                return r
    return None


def _read_meta(wb) -> Optional[MetaInfo]:
    if "_meta" not in wb.sheetnames:
        return None
    ws = wb["_meta"]
    values = {}
    for r in range(1, 4):
        key = ws.cell(row=r, column=1).value
        val = ws.cell(row=r, column=2).value
        if key:
            values[str(key).strip()] = val
    sid = values.get("subsidy_id")
    try:
        sid = int(sid) if sid is not None else None
    except (TypeError, ValueError):
        sid = None
    return MetaInfo(
        subsidy_id=sid,
        exported_at=str(values.get("exported_at")) if values.get("exported_at") is not None else None,
        format_version=str(values.get("format_version")) if values.get("format_version") is not None else None,
    )


def _to_bool_cell(v) -> Optional[bool]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    low = s.lower()
    if low in ("да", "yes", "true", "1", "+"):
        return True
    if low in ("нет", "no", "false", "0", "-"):
        return False
    return None


def parse_roundtrip_workbook(content: bytes) -> ParseResult:
    """Разбор файла в память — без обращения к БД (см. diff.py для
    сопоставления с текущим деревом субсидии)."""
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        return ParseResult(errors=["openpyxl не установлен"])

    try:
        from io import BytesIO
        wb = load_workbook(BytesIO(content), data_only=True)
    except Exception as e:
        return ParseResult(errors=[f"Не удалось прочитать файл как Excel (.xlsx): {e}"])

    # Основной лист данных — первый НЕ скрытый лист (сам _meta всегда скрыт,
    # остальные листы в этом файле feo_export_xlsx.py не создаёт, кроме
    # опциональных «Сводная»/«Дашборд», владелец другой задачи — те листы
    # здесь не содержат «Наименование» в первых строках и будут пропущены
    # поиском заголовка ниже, если пользователь случайно активировал их).
    ws = None
    for sheet_name in wb.sheetnames:
        if sheet_name == "_meta":
            continue
        candidate = wb[sheet_name]
        if _find_header_row(candidate) is not None:
            ws = candidate
            break
    if ws is None:
        return ParseResult(errors=["Не найдена строка заголовков (ячейка «Наименование» в первых 10 строках ни одного листа)"])

    header_row = _find_header_row(ws)
    col_by_key: dict[str, int] = {}
    for c in range(1, (ws.max_column or 0) + 1):
        label_norm = _norm_header(ws.cell(row=header_row, column=c).value)
        key = _KEY_BY_LABEL_NORM.get(label_norm)
        if key:
            col_by_key[key] = c

    if "name" not in col_by_key:
        return ParseResult(errors=["В файле нет обязательной колонки «Наименование»"])

    meta = _read_meta(wb)

    rows: list[ParsedRow] = []
    any_outline = False
    for r in range(header_row + 1, (ws.max_row or header_row) + 1):
        raw_name = ws.cell(row=r, column=col_by_key["name"]).value
        if raw_name is None or not str(raw_name).strip():
            continue  # пустое наименование — строка пропускается (задача владельца, п.2)
        name_cell = str(raw_name)
        leading_spaces = len(name_cell) - len(name_cell.lstrip(" "))
        name = name_cell.strip()

        outline_level = ws.row_dimensions[r].outline_level if r in ws.row_dimensions else 0
        if outline_level:
            any_outline = True

        def _cell_str(key: str) -> Optional[str]:
            col = col_by_key.get(key)
            if col is None:
                return None
            v = ws.cell(row=r, column=col).value
            if v is None:
                return None
            s = str(v).strip()
            return s or None

        def _cell_dec(key: str) -> Optional[Decimal]:
            s = _cell_str(key)
            return to_dec(s) if s is not None else None

        row_type_raw = _cell_str("row_type") or ""
        row_id_raw = _cell_str("row_id")
        active_col = col_by_key.get("active")
        is_active = _to_bool_cell(ws.cell(row=r, column=active_col).value) if active_col else None

        rows.append(ParsedRow(
            row_num=r,
            name=name,
            code=_cell_str("code"),
            appendix=_cell_str("app"),
            feo_qty=_cell_dec("feo_qty"),
            feo_unit=_cell_str("feo_unit"),
            feo_amount=_cell_dec("feo"),
            plan_amount=_cell_dec("plan"),
            is_active=is_active,
            row_type_raw=row_type_raw,
            row_id_raw=row_id_raw,
            outline_level=outline_level or 0,
            leading_spaces=leading_spaces,
        ))

    return ParseResult(rows=rows, meta=meta, used_outline=any_outline)
