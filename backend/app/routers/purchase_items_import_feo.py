"""Purchase FEO-format import — extracted from purchase_items_import.py
(Правило №5, разрезание сессии 2026-09-08).

Handles:
  GET  /api/purchases/import/feo-format/template  — download FEO-format template
  POST /api/purchases/import/feo-format           — import purchases from FEO 57-column format

Same prefix as purchase_items_import.router ("/api/purchases"); both paths are
literal (no catch-all involved), registration order relative to
purchases.router / purchase_items_import.router doesn't matter. Registered
next to purchase_items_import.router for readability.
"""
from urllib.parse import quote as _url_quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from typing import Optional
from decimal import Decimal
from datetime import datetime, date

from app.database import get_db
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.auth.jwt import get_single_org_id
from app.auth.permissions import require_tab, has_org_key
from app.utils.numbers import to_decimal
from app.models.user import User

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    Workbook = None
    load_workbook = None

router = APIRouter(prefix="/api/purchases", tags=["purchase-items-import"])

# ---------------------------------------------------------------------------
# FEO-format import (57-column layout, headers in row 6)
# ---------------------------------------------------------------------------

FEO_HEADERS = [
    "№ п.п.", "Вид расходов", "Номер субсидии",
    "Номер строки плана закупок", "Категория расходов (ФЭО направление)",
    "Наименование товара", "Контрагент", "Количество поставлено",
    "Ед. изм.", "Стоимость единицы по смете", "Стоимость по плану всего",
    "Подтверждено", "Контрактная цена за единицу", "Стоимость контракта",
    "НМЦК всего", "НМЦК по субсидии", "КПП поставщика",
    "Номер договора", "Дата договора", "Номер ПП",
    "Описание платёжного поручения", "Дата платежа", "Сумма оплаты",
    "Всего исполнено", "Резерв 25", "Резерв 26", "Резерв 27",
    "Статус закупки", "Соответствие НДС (законодательство)", "НДС включён",
    "Соответствие требованиям НДС", "Страна происхождения", "Модель",
    "Номер категории ФЭО", "Статус исполнения", "Процент исполнения",
    "Остаток по обязательствам", "Срок исполнения", "Ссылка на торговую площадку",
    "НДС-расчёт", "Совместные", "Прямой контракт",
    "Прямой контракт (повторный)", "Малые контракты", "Конкурсные",
    "Дата последнего изменения", "Стоимость единицы по оплате", "Итого к оплате",
    "Субсидия", "Часть расходов (направление)", "Период",
    "Оплата", "Сумма НДС", "Счётчик",
    "Описание контракта", "Номер и дата платежа", "",
]


def _feo_find_header_row(rows: list) -> int:
    """Return 0-based index of the header row (first row with >=5 non-empty cells)."""
    for i, row in enumerate(rows[:10]):
        non_empty = sum(1 for c in row if c is not None and str(c).strip())
        if non_empty >= 5:
            return i
    return 0


@router.get("/import/feo-format/template")
async def download_feo_template(_=Depends(require_tab('purchases'))):
    """Скачать шаблон Excel в ФЭО-формате (57 колонок, заголовки в строке 6)."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "ФЭО закупки"

    # Rows 1-5: instruction header (merged across all columns)
    ws.merge_cells("A1:BE5")
    instr_cell = ws["A1"]
    instr_cell.value = (
        "ШАБЛОН ДЛЯ ЗАГРУЗКИ ЗАКУПОК В ФЭО-ФОРМАТЕ\n"
        "Строка 6 — заголовки колонок (не изменять).\n"
        "Начиная со строки 7 — данные.\n"
        "Субсидия определяется автоматически по категории ФЭО (колонка 5).\n"
        "Обязательные колонки: 5 (ФЭО направление), 6 (Наименование товара)."
    )
    instr_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    instr_cell.font = Font(bold=True, size=11)
    ws.row_dimensions[1].height = 80

    # Row 6: headers
    ws.append(FEO_HEADERS)
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    for cell in ws[6]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[6].height = 35

    # Row 7: example
    ws.append([
        1, "Товары", "", "1",
        "Направление 1 - Техническое оснащение",
        "Компьютер офисный", "ООО Поставщик", 5, "шт",
        "50000", "250000", "да",
        "48000", "240000", "260000", "260000",
        "771234567890", "Д-001/2026", "15.03.2026",
        "70", "Оплата по договору Д-001/2026", "20.03.2026", "240000",
        "", "", "", "",
        "исполнено", "", "", "", "РФ", "", "",
        "оплачено", "1", "0",
        "30.06.2026", "", "", "", "", "", "", "",
        "", "", "", "", "", "", "", "2026",
        "240000", "0", "", "70 от 20.03.2026", "",
    ])
    ws.row_dimensions[7].height = 20

    ws.freeze_panes = "A7"

    # Column widths
    col_widths = [6, 12, 10, 12, 40, 35, 30, 10, 8, 14, 14, 12,
                  14, 14, 14, 14, 14, 18, 14, 10, 30, 14, 14, 14,
                  10, 10, 10, 14, 25, 14, 25, 18, 14, 14, 16, 12,
                  14, 14, 30, 12, 12, 16, 18, 14, 12, 16, 14, 14,
                  16, 20, 10, 14, 12, 20, 30, 20, 8]
    for i, w in enumerate(col_widths, 1):
        if i <= ws.max_column:
            ws.column_dimensions[ws.cell(6, i).column_letter].width = w

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote('Шаблон_импорта_закупок_формат_ФЭО.xlsx', safe='-_.~')}"},
    )


@router.post("/import/feo-format")
async def import_feo_format(
    file: UploadFile = File(...),
    assigned_user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('purchases')),
):
    """Импорт закупок из ФЭО-формата (57 колонок, заголовки в строке 6).
    Субсидия определяется автоматически через feo_category.subsidy_id.
    assigned_user_id: если передан — присваивается всем созданным закупкам; иначе — текущий пользователь.
    """
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    # Resolve assigned user
    if assigned_user_id is not None:
        target_user = await db.get(User, assigned_user_id)
        if target_user is None:
            raise HTTPException(400, f"Пользователь {assigned_user_id} не найден")
        resolved_assigned_user_id = assigned_user_id
    else:
        resolved_assigned_user_id = current_user.id

    content = await file.read()
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой")

    header_idx = _feo_find_header_row(rows)
    header_row = rows[header_idx]

    # Build column index by position keyword matching
    def _norm(v) -> str:
        return str(v).strip().lower() if v is not None else ""

    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        hn = _norm(h)
        if not hn:
            continue
        if "наименован" in hn or "товар" in hn or "услуг" in hn:
            col.setdefault("item_name", i)
        elif "вид расход" in hn or "вид" == hn:
            col.setdefault("item_type", i)
        elif "категори" in hn and ("фэо" in hn or "расход" in hn or "направлен" in hn):
            col.setdefault("feo_name", i)
        elif "контрагент" in hn:
            col.setdefault("contractor_name", i)
        elif "количеств" in hn or "кол-во" in hn:
            col.setdefault("quantity", i)
        elif "ед. изм" in hn or "единиц" in hn:
            col.setdefault("unit", i)
        elif "стоимость единицы по смете" in hn or ("стоимость" in hn and "единиц" in hn and "смет" in hn):
            col.setdefault("planned_unit_price", i)
        elif "стоимость по плану" in hn or ("стоимость" in hn and "план" in hn):
            col.setdefault("planned_total_price", i)
        elif "подтвержд" in hn:
            col.setdefault("confirmed", i)
        elif "стоимость контракта" in hn or ("стоимость" in hn and "контракт" in hn):
            col.setdefault("contract_price", i)
        elif "нмцк" in hn and "субсидии" not in hn:
            col.setdefault("nmck", i)
        elif "кпп" in hn:
            col.setdefault("kpp", i)
        elif "номер договора" in hn or ("номер" in hn and "договор" in hn):
            col.setdefault("contract_number", i)
        elif "дата договора" in hn or ("дата" in hn and "договор" in hn):
            col.setdefault("contract_date", i)
        elif "номер пп" in hn or ("номер" in hn and "платёжн" in hn) or ("номер" in hn and "поручен" in hn):
            col.setdefault("payment_doc_number", i)
        elif "дата платежа" in hn or ("дата" in hn and "платеж" in hn):
            col.setdefault("payment_doc_date", i)
        elif "сумма оплаты" in hn or ("сумма" in hn and "оплат" in hn):
            col.setdefault("payment_amount", i)
        elif "срок исполнения" in hn or ("срок" in hn and "исполнен" in hn):
            col.setdefault("execution_term", i)
        elif "сумма ндс" in hn:
            col.setdefault("vat_amount", i)

    # Fallback: use positional mapping (column indices 0-based from FEO_HEADERS order)
    # Col 5(idx=4)=feo, 6(5)=item_name, 7(6)=contractor, 8(7)=qty, 9(8)=unit,
    # 10(9)=unit_price, 11(10)=planned_total, 12(11)=confirmed, 14(13)=contract_price,
    # 15(14)=nmck, 17(16)=kpp, 18(17)=contract_num, 19(18)=contract_date,
    # 20(19)=pp_num, 22(21)=pp_date, 23(22)=payment_amount, 38(37)=execution_term, 53(52)=vat
    POSITIONAL = {
        "feo_name": 4, "item_name": 5, "item_type": 1,
        "contractor_name": 6, "quantity": 7, "unit": 8,
        "planned_unit_price": 9, "planned_total_price": 10, "confirmed": 11,
        "contract_price": 13, "nmck": 14, "kpp": 16,
        "contract_number": 17, "contract_date": 18,
        "payment_doc_number": 19, "payment_doc_date": 21, "payment_amount": 22,
        "execution_term": 37, "vat_amount": 52,
    }
    if "item_name" not in col and len(header_row) >= 57:
        # Headers didn't match keywords — use positional
        col = {k: v for k, v in POSITIONAL.items()}

    if "item_name" not in col and "feo_name" not in col:
        raise HTTPException(400, "Не удалось найти колонки наименования или ФЭО. Проверьте формат файла.")

    # Load lookup tables
    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name: dict[str, FeoCategory] = {}
    for f in feo_rows:
        feo_by_name[f.name.lower().strip()] = f

    cont_rows = (await db.execute(select(Contractor))).scalars().all()
    cont_by_name: dict[str, int] = {c.name.lower().strip(): c.id for c in cont_rows}
    cont_by_kpp: dict[str, int] = {c.kpp.strip(): c.id for c in cont_rows if c.kpp}

    org_id = get_single_org_id(current_user)

    def _cell(row, field) -> Optional[str]:
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("none", "null", "-", "—", "") else None

    def _to_dec(v) -> Optional[Decimal]:
        return to_decimal(v)

    def _to_date(v) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, (date, datetime)):
            return v.date() if isinstance(v, datetime) else v
        s = str(v).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        return None

    created = 0
    skipped = 0
    errors_list = []

    data_start = header_idx + 1

    # ---- Permission pre-pass ----
    # Субсидия определяется только через feo_category.subsidy_id, поэтому
    # какие субсидии затронуты — известно только ПОСЛЕ разбора ФЭО-колонки.
    # Право «редактировать субсидию» (subsidy.edit) проверяется по КАЖДОЙ
    # затронутой субсидии ДО создания хоть одной закупки — нет права хотя бы
    # по одной → 403 с названием этой субсидии, ничего не создаётся
    # (требование владельца, 2026-08-19).
    def _resolve_feo_for_row(row):
        feo_name_raw = _cell(row, "feo_name")
        if not feo_name_raw:
            return None
        feo_obj = feo_by_name.get(feo_name_raw.lower().strip())
        if not feo_obj:
            for k, v in feo_by_name.items():
                if feo_name_raw.lower() in k or k in feo_name_raw.lower():
                    feo_obj = v
                    break
        return feo_obj

    touched_subsidy_ids: set[int] = set()
    for row in rows[data_start:]:
        if not _cell(row, "item_name"):
            continue
        feo_obj = _resolve_feo_for_row(row)
        if feo_obj is not None:
            touched_subsidy_ids.add(feo_obj.subsidy_id)

    if touched_subsidy_ids:
        touched_subsidies = (
            await db.execute(select(Subsidy).where(Subsidy.id.in_(touched_subsidy_ids)))
        ).scalars().all()
        subsidies_by_id = {s.id: s for s in touched_subsidies}
        for sub_id in touched_subsidy_ids:
            sub = subsidies_by_id.get(sub_id)
            sub_name = sub.name if sub else f"id {sub_id}"
            has_perm = (
                sub is not None
                and await has_org_key(current_user, db, sub.org_id, 'subsidy.edit', subsidy_id=sub_id)
            )
            if not has_perm:
                raise HTTPException(
                    403,
                    f"Импортировать закупки в субсидию «{sub_name}» может только тот, у кого "
                    "есть право её редактирования",
                )

    for row_num, row in enumerate(rows[data_start:], start=data_start + 1):
        item_name = _cell(row, "item_name")
        if not item_name:
            skipped += 1
            continue

        # FEO lookup → subsidy
        feo_name_raw = _cell(row, "feo_name")
        feo_obj = None
        if feo_name_raw:
            feo_obj = feo_by_name.get(feo_name_raw.lower().strip())
            if not feo_obj:
                # Partial match
                for k, v in feo_by_name.items():
                    if feo_name_raw.lower() in k or k in feo_name_raw.lower():
                        feo_obj = v
                        break

        if feo_obj is None:
            errors_list.append({"row": row_num, "name": item_name, "message": f"ФЭО категория не найдена: {feo_name_raw!r}"})
            skipped += 1
            continue

        feo_category_id = feo_obj.id
        subsidy_id = feo_obj.subsidy_id

        # Contractor lookup
        cont_name = _cell(row, "contractor_name")
        kpp_raw = _cell(row, "kpp")
        contractor_id = None
        if cont_name:
            contractor_id = cont_by_name.get(cont_name.lower().strip())
            if contractor_id is None and kpp_raw:
                contractor_id = cont_by_kpp.get(kpp_raw.strip())
            if contractor_id is None:
                # Create new contractor
                new_cont = Contractor(name=cont_name, kpp=kpp_raw, org_id=org_id)
                db.add(new_cont)
                await db.flush()
                contractor_id = new_cont.id
                cont_by_name[cont_name.lower().strip()] = contractor_id
                if kpp_raw:
                    cont_by_kpp[kpp_raw.strip()] = contractor_id

        # Numeric fields
        planned_qty = _to_dec(_cell(row, "quantity"))
        planned_unit = _to_dec(_cell(row, "planned_unit_price"))
        planned_total = _to_dec(_cell(row, "planned_total_price"))
        contract_price = _to_dec(_cell(row, "contract_price"))
        nmck = _to_dec(_cell(row, "nmck"))
        payment_amount = _to_dec(_cell(row, "payment_amount"))
        vat_amount = _to_dec(_cell(row, "vat_amount"))

        # Dates
        def _raw_date(field):
            idx = col.get(field)
            if idx is None or idx >= len(row):
                return None
            return _to_date(row[idx])

        contract_date = _raw_date("contract_date")
        payment_doc_date = _raw_date("payment_doc_date")
        execution_term = _raw_date("execution_term")

        # Status inference
        contract_number = _cell(row, "contract_number")
        payment_doc_number = _cell(row, "payment_doc_number")
        if payment_amount and payment_amount > 0:
            status = "paid"
        elif contract_number:
            status = "contracted"
        else:
            status = "work_in_progress"

        # Confirmed flag (legacy column — maps to boolean field Purchase.confirmed, not status)
        conf_raw = (_cell(row, "confirmed") or "").lower()
        confirmed = conf_raw in ("да", "yes", "1", "true", "+")

        # Item type
        item_type_raw = (_cell(row, "item_type") or "").lower()
        item_type = "услуга" if "услуг" in item_type_raw else "товар"

        # VAT
        vat_applicable = bool(vat_amount and vat_amount > 0)

        p = Purchase(
            item_name=item_name,
            item_type=item_type,
            feo_category_id=feo_category_id,
            subsidy_id=subsidy_id,
            contractor_id=contractor_id,
            planned_quantity=planned_qty,
            unit=_cell(row, "unit"),
            planned_unit_price=planned_unit,
            planned_total_price=planned_total,
            confirmed=confirmed,
            contract_price=contract_price,
            nmck=nmck,
            total_nmck=nmck,
            contract_number=contract_number,
            contract_date=contract_date,
            payment_doc_number=payment_doc_number,
            payment_doc_date=payment_doc_date,
            payment_amount=payment_amount,
            execution_term=execution_term,
            vat_applicable=vat_applicable,
            status=status,
            assigned_user_id=resolved_assigned_user_id,
        )
        db.add(p)
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors_list}
