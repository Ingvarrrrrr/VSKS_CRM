"""Purchase import — core parse-and-group logic shared by /import and
/import/preview.

Split out of `services/purchase_import_parser.py` (refactor, 2026-09):
`_parse_and_group` is one large (~900-line) function with no internal
`def`-scoped stages to cut along (only two tiny nested closures — `cell` in
_make_cell_helper and `_pay_fp_local` here — neither is a separable stage),
so per ПРАВИЛО №5 it is kept whole in its own module, the same treatment
`feo_plan_tree.py::compute_feo_plan_tree` got in the sibling ФЭО refactor
(git d0bb409). Column maps and label→code lookup tables live in
`purchase_import_parser_maps.py`; small per-cell/ФЭО-path helpers live in
`purchase_import_parser_helpers.py`. `services/purchase_import_parser.py`
re-exports everything from all three for backward compatibility.
"""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.event import Event
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.item_contractor import set_item_contractor
from app.models.subsidy import Subsidy
from app.routers.events import normalize_event_name
from app.services.purchase_payments import recompute_purchase_payments
from app.services import acceptance_docs as _acc_docs
from app.services.purchase_import_parser_helpers import (
    _build_feo_index,
    _find_payments_sheet,
    _make_cell_helper,
    _resolve_feo_levels,
    _resolve_feo_path,
    _to_dec,
    _to_date_val,
)
from app.services.purchase_import_parser_maps import (
    _COLUMN_MAP,
    _CONTRACT_TYPE_MAP,
    _ITEM_TYPE_MAP,
    _METHOD_MAP,
    _NEW_TEMPLATE_MARKER_FIELDS,
    _OLD_TEMPLATE_MARKER_FIELDS,
    _PAYMENT_BASIS_MAP,
    _PAYMENTS_COLUMN_MAP,
    _REQUIRED_FIELDS,
    _STATUS_MAP,
    _SUBSTATUS_MAP,
)

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


# ---------------------------------------------------------------------------
# Core parse-and-group logic (shared by /import and /import/preview)
# ---------------------------------------------------------------------------

async def _parse_and_group(
    content: bytes,
    sid: int,
    db: AsyncSession,
    commit: bool,
) -> Dict[str, Any]:
    """
    Parse Excel content (single «Закупки» sheet with inline payments; legacy 2-sheet
    workbooks with a «Платежи» sheet are still supported), validate rows, group into purchases,
    optionally commit. Handles both new (5-level FEO, 2-sheet) and old (path, 1-sheet) templates.

    Returns dict with keys:
      created_purchases, created_items, created_payments, skipped, errors   (commit=True)
      purchases (list of preview dicts), payments_errors, skipped, errors   (commit=False)
    """
    wb = load_workbook(BytesIO(content), data_only=True)

    # Find «Закупки» sheet — use first sheet (active) as primary
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(400, "Файл пустой или содержит только заголовки")

    # --- Build col_idx for «Закупки» ---
    raw_headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    col_idx: Dict[str, int] = {}
    for i, h in enumerate(raw_headers):
        field = _COLUMN_MAP.get(h)
        if field and field not in col_idx:
            col_idx[field] = i

    cell = _make_cell_helper(col_idx)

    # Detect template format: prefer new (feo_l1) over old (feo_path)
    has_new_feo = bool(_NEW_TEMPLATE_MARKER_FIELDS & set(col_idx.keys()))
    has_old_feo = bool(_OLD_TEMPLATE_MARKER_FIELDS & set(col_idx.keys()))
    # is_new_template: new format with level cols, OR both — prefer levels
    is_new_template = has_new_feo

    # --- Load lookup tables ---
    subs_rows = (await db.execute(select(Subsidy))).scalars().all()
    subs_by_name = {s.name.lower().strip(): s.id for s in subs_rows}

    contractors_all = (await db.execute(select(Contractor))).scalars().all()
    cont_by_inn  = {c.inn.strip(): c.id for c in contractors_all if c.inn}
    cont_by_name = {c.name.lower().strip(): c.id for c in contractors_all}

    feo_rows_all = (await db.execute(select(FeoCategory))).scalars().all()
    feo_index = _build_feo_index(feo_rows_all, sid)

    # Мероприятия (Приложение №3): единственная точка ввода — карточка
    # субсидии; импорт только резолвит event_name → event_id среди
    # мероприятий ЭТОЙ субсидии, ничего не создаёт (требование владельца
    # 2026-08-19, «иначе я потом никогда ничего не посчитаю»).
    event_rows_all = (await db.execute(select(Event))).scalars().all()
    events_by_subsidy: Dict[int, Dict[str, tuple]] = defaultdict(dict)
    for _ev in event_rows_all:
        events_by_subsidy[_ev.subsidy_id][normalize_event_name(_ev.name)] = (_ev.id, _ev.name)

    # Anti-dup: existing (contract_number, order_number) pairs for this subsidy
    existing_q = await db.execute(
        select(Purchase.contract_number, Purchase.order_number).where(
            Purchase.subsidy_id == sid,
            Purchase.contract_number.isnot(None),
            Purchase.contract_number != "",
        )
    )
    existing_keys = {(r[0], r[1]) for r in existing_q.fetchall()}

    # Duplicate-purchase index: существующие разовые (НЕ ежемесячные) закупки субсидии,
    # ключ (contractor_id, сумма). Сумма = ЛЮБАЯ из {НМЦК, цена договора, платёж} +
    # суммы отдельных платежей (Payment). Совпадение по любой сумме = возможный повтор.
    existing_dup_q = await db.execute(
        select(
            Purchase.id, Purchase.purchase_number, Purchase.item_name,
            Purchase.subject, Purchase.status, Purchase.contract_date,
            Purchase.contractor_id, Purchase.total_nmck,
            Purchase.contract_price, Purchase.payment_amount,
        ).where(
            Purchase.subsidy_id == sid,
            Purchase.is_monthly_payment.isnot(True),
            Purchase.contractor_id.isnot(None),
        )
    )
    existing_rows = existing_dup_q.fetchall()
    _exist_ids = [r.id for r in existing_rows]
    exist_pay_amounts: dict = defaultdict(list)
    if _exist_ids:
        _pay_q = await db.execute(
            select(Payment.purchase_id, Payment.amount).where(
                Payment.purchase_id.in_(_exist_ids),
                Payment.amount.isnot(None),
            )
        )
        for _pr in _pay_q.fetchall():
            exist_pay_amounts[_pr.purchase_id].append(_pr.amount)

    existing_dup_index: dict = defaultdict(list)
    for r in existing_rows:
        _base = {
            "source": "db",
            "id": r.id,
            "purchase_number": r.purchase_number,
            "name": r.item_name or r.subject or "",
            "status": r.status,
            "contract_date": r.contract_date.isoformat() if r.contract_date else None,
        }
        _pairs = [("НМЦК", r.total_nmck), ("цена договора", r.contract_price), ("платёж", r.payment_amount)]
        _pairs += [("платёж", a) for a in exist_pay_amounts.get(r.id, [])]
        for _reason, _val in _pairs:
            if _val is None:
                continue
            _fv = float(_val)
            if _fv <= 0:
                continue
            existing_dup_index[(r.contractor_id, round(_fv, 2))].append({**_base, "amount": _fv, "match_reason": _reason})

    errors: list[dict] = []
    warnings: list[dict] = []
    skipped = 0

    # --- Simulate mode: коллектор создаваемых ФЭО и счётчик отрицательных id ---
    simulate = not commit
    pending_created: list = []          # список {level, name, path} без дублей
    sim_id_counter: list = [-1]         # изменяемый счётчик [текущее_значение]
    subsidy_has_feo: bool = bool(feo_index)  # были ли категории ДО разбора

    # --- Parse «Закупки» rows ---
    parsed_rows = []
    for row_num, row in enumerate(rows[1:], start=2):
        # Blank row guard
        non_empty = any(
            v is not None and str(v).strip() != ""
            for v in row
        )
        if not non_empty:
            skipped += 1
            continue

        item_name = cell(row, "item_name")
        if not item_name:
            skipped += 1
            continue

        # ---- Resolve FEO ----
        feo_id = None
        feo_levels_display = None  # list of non-empty level strings, for preview display

        if has_new_feo and any(cell(row, f"feo_l{n}") for n in range(1, 6)):
            # New: collect non-empty level values in order
            raw_levels = [cell(row, f"feo_l{n}") or "" for n in range(1, 6)]
            levels = [v for v in raw_levels if v.strip()]
            feo_levels_display = levels

            if is_new_template:
                # feo_l1 is required — already validated below in required-field check,
                # but guard here too
                if not levels:
                    errors.append({"row": row_num, "name": item_name, "message": "ФЭО Ур.1 обязателен"})
                    continue
                feo_id, feo_err = await _resolve_feo_levels(
                    levels, sid, feo_index,
                    db=db, feo_rows_all=feo_rows_all, create_missing=commit,
                    simulate=simulate, pending_created=pending_created,
                    _sim_id_counter=sim_id_counter,
                )
                if feo_err:
                    # В режиме симуляции ФЭО-ошибок не должно быть (simulate обработал),
                    # но если всё же есть — добавляем ошибку, НЕ выбрасываем строку
                    if commit:
                        errors.append({"row": row_num, "name": item_name, "message": feo_err})
                        continue
                    else:
                        errors.append({"row": row_num, "name": item_name, "message": feo_err})
                        # Не делаем continue — строка уходит в превью как есть
            else:
                if levels:
                    feo_id, _ = await _resolve_feo_levels(
                        levels, sid, feo_index,
                        db=db, feo_rows_all=feo_rows_all, create_missing=commit,
                        simulate=simulate, pending_created=pending_created,
                        _sim_id_counter=sim_id_counter,
                    )
        elif has_old_feo:
            # Old: single path column (backward compat)
            feo_path_raw = cell(row, "feo_path") or cell(row, "feo_category_name")
            if feo_path_raw:
                feo_id, feo_err = await _resolve_feo_path(
                    feo_path_raw, feo_index,
                    sid=sid, db=db, feo_rows_all=feo_rows_all, create_missing=commit,
                    simulate=simulate, pending_created=pending_created,
                    _sim_id_counter=sim_id_counter,
                )
                if feo_err and not has_new_feo:
                    # only hard-error in old-style-only templates if it was new-enough format
                    pass  # leave feo_id as None
                feo_levels_display = [p.strip() for p in feo_path_raw.replace(">", "/").split("/") if p.strip()]

        # ---- Required-field validation (new template) ----
        if is_new_template:
            missing_labels = []
            for field, label in _REQUIRED_FIELDS:
                val = cell(row, field)
                if not val:
                    missing_labels.append(label)
            if missing_labels:
                errors.append({"row": row_num, "name": item_name, "missing": missing_labels})
                continue

        # ---- Contract number required (all modes) ----
        contract_num = cell(row, "contract_number")
        if is_new_template and not contract_num:
            errors.append({"row": row_num, "name": item_name, "message": "№ договора обязателен"})
            continue

        # ---- Subsidy ----
        row_sid = sid
        sub_name = cell(row, "subsidy_name")
        if not row_sid and sub_name:
            row_sid = subs_by_name.get(sub_name.lower().strip())
        if not row_sid:
            errors.append({"row": row_num, "name": item_name, "message": "Субсидия не указана"})
            continue

        # ---- Event (Приложение №3) ----
        # НЕ обязательно (требование владельца, 2026-08-19): «не всегда
        # известно». Пустая ячейка — молча, без предупреждения. Название, не
        # найденное среди мероприятий субсидии, тоже больше НЕ роняет строку —
        # закупка создаётся без event_id, а пользователь видит предупреждение
        # (preview/импорт) и оранжевый значок в реестре закупок. Ничего не
        # создаётся автоматически — единственная точка ввода мероприятий это
        # карточка субсидии.
        event_id_val = None
        event_name_raw = cell(row, "event_name")
        if event_name_raw:
            _ev_match = events_by_subsidy.get(row_sid, {}).get(normalize_event_name(event_name_raw))
            if _ev_match:
                event_id_val = _ev_match[0]
            else:
                warnings.append({
                    "row": row_num,
                    "name": item_name,
                    "message": (
                        f"Строка {row_num}: мероприятие «{event_name_raw}» не найдено среди "
                        "мероприятий субсидии — закупка создана без привязки. Заведите "
                        "мероприятие в карточке субсидии (Приложение №3) и привяжите вручную."
                    ),
                })

        # ---- Contractor ----
        c_inn  = cell(row, "contractor_inn")
        c_name = cell(row, "contractor_name")
        cont_id = None
        if c_inn:
            cont_id = cont_by_inn.get(c_inn.strip())
        if not cont_id and c_name:
            cont_id = cont_by_name.get(c_name.lower().strip())
        if not cont_id and c_inn:
            if commit:
                new_cont = Contractor(name=c_name or c_inn, inn=c_inn.strip())
                db.add(new_cont)
                await db.flush()
                cont_id = new_cont.id
                cont_by_inn[c_inn.strip()] = cont_id
                if c_name:
                    cont_by_name[c_name.lower().strip()] = cont_id

        # ---- Status ----
        status_raw = (cell(row, "status") or "").lower().strip()
        status = _STATUS_MAP.get(status_raw)
        if not status:
            # old-style payment columns on this sheet (backward compat)
            pay_amt = _to_dec(cell(row, "payment_amount"))
            if pay_amt and pay_amt > 0:
                status = "paid"
            elif contract_num:
                status = "contracted"
            else:
                status = "work_in_progress"

        # ---- Substatus ----
        substatus_raw = (cell(row, "substatus") or "").lower().strip()
        substatus_val = _SUBSTATUS_MAP.get(substatus_raw) if substatus_raw else None

        # ---- Contract type (purchase_contract_type) ----
        ct_raw = (cell(row, "contract_type_raw") or "").lower().strip()
        contract_type_val = _CONTRACT_TYPE_MAP.get(ct_raw) if ct_raw else None

        # ---- Item type ----
        it_raw = (cell(row, "item_type") or "").lower().strip()
        item_type_val = _ITEM_TYPE_MAP.get(it_raw) if it_raw else (it_raw or None)

        # ---- Payment basis type ----
        pb_raw = (cell(row, "payment_basis_type") or "").lower().strip()
        payment_basis_type_val = _PAYMENT_BASIS_MAP.get(pb_raw) if pb_raw else None

        # ---- Method ----
        method_raw = (cell(row, "purchase_method") or "").lower().strip()
        method = _METHOD_MAP.get(method_raw)

        # ---- New fields: purchase group number, order number, contract subject ----
        pg = cell(row, "purchase_group_num")
        order_no = cell(row, "order_number")
        subject_val = cell(row, "subject")

        # ---- Group key: prioritise purchase+order, then contract, then row ----
        if pg:
            group_key = f"pg:{pg}|{order_no or ''}"
        elif contract_num:
            group_key = f"contract:{contract_num}"
        else:
            group_key = f"row:{row_num}"

        # ---- Collect raw date cells for post-processing ----
        raw_contract_date           = row[col_idx["contract_date"]]           if "contract_date"           in col_idx else None
        raw_execution_term          = row[col_idx["execution_term"]]          if "execution_term"          in col_idx else None
        raw_execution_term_changed  = row[col_idx["execution_term_changed"]]  if "execution_term_changed"  in col_idx else None
        raw_delivery_date           = row[col_idx["delivery_date"]]           if "delivery_date"           in col_idx else None
        raw_payment_doc_date        = row[col_idx["payment_doc_date"]]        if "payment_doc_date"        in col_idx else None
        raw_acceptance_doc_date     = row[col_idx["acceptance_doc_date"]]     if "acceptance_doc_date"     in col_idx else None
        raw_contract_end_date       = row[col_idx["contract_end_date"]]       if "contract_end_date"       in col_idx else None
        raw_planned_payment_month   = row[col_idx["planned_payment_month"]]   if "planned_payment_month"   in col_idx else None
        raw_submission_deadline     = row[col_idx["submission_deadline"]]     if "submission_deadline"     in col_idx else None

        # ---- Boolean flags ----
        vat_applicable_raw  = (cell(row, "vat_applicable") or "").lower().strip()
        is_prepayment_raw   = (cell(row, "is_prepayment") or "").lower().strip()
        is_monthly_raw      = (cell(row, "is_monthly_payment") or "").lower().strip()

        # ---- Commitment quarter ----
        _cq_raw = cell(row, "commitment_quarter")
        commitment_quarter_val = None
        if _cq_raw:
            try:
                _cq_int = int(str(_cq_raw).strip())
                if 1 <= _cq_int <= 4:
                    commitment_quarter_val = _cq_int
            except Exception:
                pass

        # ---- VAT mode ----
        vat_mode_raw = (cell(row, "vat_mode") or "").lower().strip()
        _vat_mode_map = {"одинаковый": "uniform", "для каждого товара": "per_item",
                         "uniform": "uniform", "per_item": "per_item"}
        vat_mode_val = _vat_mode_map.get(vat_mode_raw, "uniform") if vat_mode_raw else None

        parsed_rows.append({
            "row_num":                  row_num,
            "group_key":                group_key,
            "purchase_group_num":       pg,
            "order_number":             order_no,
            "subject":                  subject_val,
            "item_name":                item_name,
            "item_type":                item_type_val,
            "feo_id":                   feo_id,
            "feo_levels":               feo_levels_display or [],
            "cont_id":                  cont_id,
            "cont_inn":                 c_inn,
            "cont_name":                c_name,
            "event_name":               event_name_raw,
            "event_id":                 event_id_val,
            "status":                   status,
            "substatus":                substatus_val,
            "contract_type_val":        contract_type_val,
            "payment_basis_type":       payment_basis_type_val,
            "method":                   method,
            "registry_number":          cell(row, "registry_number"),
            "contract_number":          contract_num,
            "contract_date":            _to_date_val(raw_contract_date),
            "contract_price":           _to_dec(cell(row, "contract_price")),
            "execution_term":           _to_date_val(raw_execution_term),
            "execution_term_changed":   _to_date_val(raw_execution_term_changed),
            "delivery_date":            _to_date_val(raw_delivery_date),
            "purchase_basis":           cell(row, "purchase_basis"),
            "responsible_person":       cell(row, "responsible_person"),
            "etp_url":                  cell(row, "etp_url"),
            "vat_applicable":           vat_applicable_raw in ("да", "yes", "1", "true"),
            "vat_exemption_article":    cell(row, "vat_exemption_article"),
            # Closing document
            "acceptance_doc_name":      cell(row, "acceptance_doc_name"),
            "acceptance_doc_number":    cell(row, "acceptance_doc_number"),
            "acceptance_doc_date":      _to_date_val(raw_acceptance_doc_date),
            "acceptance_doc_amount":    _to_dec(cell(row, "acceptance_doc_amount")),
            # Boolean flags
            "is_prepayment":            is_prepayment_raw in ("да", "yes", "1", "true"),
            "is_monthly_payment":       is_monthly_raw in ("да", "yes", "1", "true"),
            # Inline payment fields (new template) + legacy backward compat
            "payment_doc_number":       cell(row, "payment_doc_number"),
            "payment_doc_date":         _to_date_val(raw_payment_doc_date),
            "payment_amount":           _to_dec(cell(row, "payment_amount")),
            "payment_federal":          _to_dec(cell(row, "payment_federal")),
            "payment_purpose":          cell(row, "payment_purpose"),
            "plan_qty":                 _to_dec(cell(row, "plan_qty")),
            "unit":                     cell(row, "unit"),
            "plan_unit_price":          _to_dec(cell(row, "plan_unit_price")),
            "plan_total":               _to_dec(cell(row, "plan_total")),
            "fact_qty":                 _to_dec(cell(row, "fact_qty")),
            "fact_unit_price":          _to_dec(cell(row, "fact_unit_price")),
            "fact_total":               _to_dec(cell(row, "fact_total")),
            "country_origin":           cell(row, "country_origin"),
            "vat_rate":                 cell(row, "vat_rate"),
            "nmck":                     _to_dec(cell(row, "nmck")),
            "sid":                      row_sid,
            # New extended fields
            "region":                   cell(row, "region"),
            "delivery_region":          cell(row, "delivery_region"),
            "delivery_location":        cell(row, "delivery_location"),
            "delivery_address":         cell(row, "delivery_address"),
            "economy":                  _to_dec(cell(row, "economy")),
            "contract_end_date":        _to_date_val(raw_contract_end_date),
            "commitment_quarter":       commitment_quarter_val,
            "planned_payment_month":    _to_date_val(raw_planned_payment_month),
            "submission_deadline":      _to_date_val(raw_submission_deadline),
            "vat_mode":                 vat_mode_val,
            "stage_label":              cell(row, "stage_label"),
        })

    # --- Parse «Платежи» sheet ---
    pay_sheet = _find_payments_sheet(wb)
    parsed_payments: List[Dict[str, Any]] = []
    payments_errors: List[dict] = []

    if pay_sheet is not None:
        pay_rows = list(pay_sheet.iter_rows(values_only=True))
        if len(pay_rows) >= 2:
            raw_pay_headers = [str(h).strip().lower() if h is not None else "" for h in pay_rows[0]]
            pay_col_idx: Dict[str, int] = {}
            for i, h in enumerate(raw_pay_headers):
                field = _PAYMENTS_COLUMN_MAP.get(h)
                if field and field not in pay_col_idx:
                    pay_col_idx[field] = i

            pay_cell = _make_cell_helper(pay_col_idx)

            for pay_row_num, pay_row in enumerate(pay_rows[1:], start=2):
                # Skip blank rows and note rows (e.g. the hint text we put in row 3)
                non_empty = any(
                    v is not None and str(v).strip() != ""
                    for v in pay_row
                )
                if not non_empty:
                    continue

                p_contract = pay_cell(pay_row, "contract_number")
                if not p_contract:
                    continue
                # Skip the hint-text row if it landed in col 1
                if "одна строка" in p_contract.lower() or "платёж" in p_contract.lower():
                    continue

                raw_pay_date = pay_row[pay_col_idx["payment_date"]] if "payment_date" in pay_col_idx else None

                parsed_payments.append({
                    "pay_row_num":      pay_row_num,
                    "contract_number":  p_contract,
                    "document_number":  pay_cell(pay_row, "document_number"),
                    "payment_date":     _to_date_val(raw_pay_date),
                    "amount":           _to_dec(pay_cell(pay_row, "amount")),
                    "payment_purpose":  pay_cell(pay_row, "payment_purpose"),
                })

    # --- Group rows ---
    groups: Dict[str, List[dict]] = defaultdict(list)
    for pr in parsed_rows:
        groups[pr["group_key"]].append(pr)

    created_purchases = 0
    created_items = 0
    created_payments = 0
    preview_list = []
    batch_seen_dup: dict = defaultdict(list)
    duplicates_count = 0
    without_event = 0  # закупки (созданные/preview), у которых event_id не проставлен

    # Map contract_number → Purchase (built during commit, used for payment linking)
    contract_to_purchase: Dict[str, Purchase] = {}

    for group_key, group_rows in groups.items():
        first = group_rows[0]
        contract_num = first["contract_number"]

        # Anti-dup check (keyed on contract_number + order_number for рамочные)
        order_no = first.get("order_number")
        if contract_num and (contract_num, order_no) in existing_keys:
            skipped += 1
            if not commit:
                preview_list.append({
                    "group_key": group_key,
                    "contract_number": contract_num,
                    "purchase_group": first.get("purchase_group_num") or "",
                    "order_number": first.get("order_number") or "",
                    "contractor": first["cont_name"] or first["cont_inn"] or "",
                    "feo_path": " / ".join(first["feo_levels"]) if first["feo_levels"] else "",
                    "items_count": len(group_rows),
                    "plan_total": None,
                    "fact_total": None,
                    "status": first["status"],
                    "payments_count": 0,
                    "payments_total": None,
                    "skipped": True,
                    "skip_reason": "Дублирующийся договор",
                })
            continue

        # Aggregate sums
        plan_total_sum = sum(
            (pr["plan_total"] or (
                (pr["plan_qty"] or Decimal(0)) * (pr["plan_unit_price"] or Decimal(0))
            ))
            for pr in group_rows
        )
        fact_total_sum = sum(
            (pr["fact_total"] or Decimal(0))
            for pr in group_rows
        )

        # --- Collect inline payments from group rows ---
        inline_payments = []
        for pr in group_rows:
            if pr.get("payment_doc_number") or pr.get("payment_amount") or pr.get("payment_doc_date"):
                inline_payments.append({
                    "document_number": pr.get("payment_doc_number"),
                    "payment_date":    pr.get("payment_doc_date"),
                    "amount":          pr.get("payment_amount"),
                    "payment_purpose": pr.get("payment_purpose"),
                    "row_num":         pr["row_num"],
                })

        # Payments for preview: inline first, then sheet (backward compat)
        sheet_payments = [pp for pp in parsed_payments if pp["contract_number"] == contract_num] if contract_num else []

        # Deduplicate inline payments by fingerprint
        def _pay_fp_local(dn, pd, am):
            return (
                str(dn or "").strip(),
                str(pd or ""),
                round(float(am), 2) if am is not None else None,
            )
        seen_fps: set = set()
        unique_inline: list = []
        for ip in inline_payments:
            fp = _pay_fp_local(ip["document_number"], ip["payment_date"], ip["amount"])
            if fp not in seen_fps:
                seen_fps.add(fp)
                unique_inline.append(ip)

        # Total payments for preview = unique inline + sheet (deduped against inline)
        all_preview_payments = list(unique_inline)
        for sp in sheet_payments:
            fp = _pay_fp_local(sp.get("document_number"), sp.get("payment_date"), sp.get("amount"))
            if fp not in seen_fps:
                seen_fps.add(fp)
                all_preview_payments.append(sp)

        pay_count = len(all_preview_payments)
        pay_total = sum((ip.get("amount") or Decimal(0)) for ip in all_preview_payments)

        # Deduped item count (same key as commit-side PurchaseItem dedup)
        unique_item_keys = {
            ((pr["item_name"] or "").lower().strip(), pr["plan_qty"], pr["plan_unit_price"])
            for pr in group_rows
        }

        if not commit:
            # --- Duplicate-purchase detection (preview only) ---
            dup_matches = []
            if (
                not first.get("is_monthly_payment")
                and first.get("cont_id")
                and first["cont_id"] != -1
            ):
                _cand = [("НМЦК", first.get("nmck")), ("цена договора", plan_total_sum if plan_total_sum else None)]
                _cand += [("платёж", ip.get("amount")) for ip in all_preview_payments]
                _seen_db: set = set()
                _seen_file: set = set()
                for _reason, _val in _cand:
                    if _val is None:
                        continue
                    _fv = float(_val)
                    if _fv <= 0:
                        continue
                    dkey = (first["cont_id"], round(_fv, 2))
                    for m in existing_dup_index.get(dkey, []):
                        if m["id"] not in _seen_db:
                            _seen_db.add(m["id"])
                            dup_matches.append(m)
                    for prev in batch_seen_dup.get(dkey, []):
                        _fk = (prev["name"], prev["amount"])
                        if _fk not in _seen_file:
                            _seen_file.add(_fk)
                            dup_matches.append(prev)
                    batch_seen_dup[dkey].append({
                        "source": "file",
                        "id": None,
                        "purchase_number": None,
                        "name": (first.get("cont_name") or "") + " — " + (contract_num or group_key),
                        "amount": _fv,
                        "status": None,
                        "contract_date": None,
                        "match_reason": _reason,
                    })
            if dup_matches:
                duplicates_count += 1
            if not first.get("event_id"):
                without_event += 1
            preview_list.append({
                "group_key": group_key,
                "contract_number": contract_num or "",
                "purchase_group": first.get("purchase_group_num") or "",
                "order_number": first.get("order_number") or "",
                "contractor": first["cont_name"] or first["cont_inn"] or "",
                "feo_path": " / ".join(first["feo_levels"]) if first["feo_levels"] else "",
                "items_count": len(unique_item_keys),
                "plan_total": float(plan_total_sum) if plan_total_sum else None,
                "fact_total": float(fact_total_sum) if fact_total_sum else None,
                "status": first["status"],
                "payments_count": pay_count,
                "payments_total": float(pay_total) if pay_total else None,
                "skipped": False,
                "duplicate_matches": dup_matches,
                "event_id": first.get("event_id"),
                "event_name": first.get("event_name"),
            })
            continue

        # --- Create Purchase ---
        # For inline payments: sum all unique amounts, first doc_number, min date
        inline_amounts  = [ip["amount"] for ip in unique_inline if ip["amount"] is not None]
        inline_dates    = [ip["payment_date"] for ip in unique_inline if ip["payment_date"] is not None]
        inline_doc_nums = [ip["document_number"] for ip in unique_inline if ip["document_number"]]

        # Resolve purchase_basis (backward compat: accept both key and label)
        basis_raw = (first.get("purchase_basis") or "").lower().strip()
        basis_val = None
        if basis_raw in ("план закупок", "план_график", "plan_schedule"):
            basis_val = "plan_schedule"
        elif basis_raw in ("служебная записка", "служебная_записка", "service_note"):
            basis_val = "service_note"

        # Build acceptance_docs JSONB (first closing document, if any data given)
        acc_name   = first.get("acceptance_doc_name")
        acc_number = first.get("acceptance_doc_number")
        acc_date   = first.get("acceptance_doc_date")
        acc_amount = first.get("acceptance_doc_amount")
        acceptance_docs_val = []
        if any([acc_name, acc_number, acc_date, acc_amount]):
            acceptance_docs_val = [{
                "name":   acc_name or "",
                "number": acc_number or "",
                "date":   str(acc_date) if acc_date else "",
                "amount": float(acc_amount) if acc_amount else None,
            }]

        p = Purchase(
            subsidy_id=first["sid"],
            feo_category_id=first["feo_id"],
            event_id=first.get("event_id"),
            contractor_id=first["cont_id"] if (first["cont_id"] and first["cont_id"] != -1) else None,
            item_name=(first.get("subject") or first["item_name"]),
            purchase_number=int(first["purchase_group_num"]) if (first.get("purchase_group_num") or "").strip().isdigit() else None,
            order_number=first.get("order_number"),
            subject=first.get("subject"),
            status=first["status"],
            substatus=first.get("substatus"),
            purchase_method=first["method"],
            purchase_contract_type=first.get("contract_type_val"),
            payment_basis_type=first.get("payment_basis_type"),
            registry_number=first["registry_number"],
            contract_number=contract_num,
            contract_date=first["contract_date"],
            contract_price=first["contract_price"],
            execution_term=first["execution_term"],
            execution_term_changed=first.get("execution_term_changed"),
            delivery_date=first.get("delivery_date"),
            purchase_basis=basis_val,
            responsible_person=first.get("responsible_person"),
            etp_url=first.get("etp_url"),
            # НДС
            vat_applicable=first.get("vat_applicable") or False,
            # `first.get("vat_rate") and ...` терял явный 0 (falsy int/float)
            # — та же ошибка, что и «or 20» в documents.py: ставка 0%
            # молчаливо превращалась в «не указана». None-check сохраняет 0.
            vat_rate=(
                int(first["vat_rate"])
                if (first.get("vat_rate") is not None and str(first["vat_rate"]).strip() != ""
                    and str(first["vat_rate"]).isdigit())
                else None
            ),
            vat_exemption_article=first.get("vat_exemption_article"),
            # ПРАВИЛО №6 (2026-09-07, группа D4): источник истины — JSONB
            # acceptance_docs; скаляры acceptance_doc_name/number/date/amount
            # НЕ передаются здесь напрямую — их пишет только sync_scalars()
            # ниже (единственный писатель кэша, см. app.services.acceptance_docs).
            acceptance_docs=_acc_docs.dedup(acceptance_docs_val) if acceptance_docs_val else [],
            # Flags
            is_prepayment=first.get("is_prepayment") or False,
            is_monthly_payment=first.get("is_monthly_payment") or False,
            # Summary payment fields from inline rows (or legacy single-row if no inline)
            payment_doc_number=inline_doc_nums[0] if inline_doc_nums else first.get("payment_doc_number"),
            payment_doc_date=min(inline_dates) if inline_dates else first.get("payment_doc_date"),
            payment_amount=sum(inline_amounts) if inline_amounts else first.get("payment_amount"),
            payment_federal=first.get("payment_federal") if first.get("payment_federal") else None,
            nmck=first["nmck"],
            total_nmck=first["nmck"],
            planned_quantity=first["plan_qty"],
            planned_unit_price=first["plan_unit_price"],
            planned_total_price=plan_total_sum if plan_total_sum else first["nmck"],
            final_total_amount=fact_total_sum if fact_total_sum else None,
            country_origin=first["country_origin"],
            # Item type — from first row (group-level attribute)
            item_type=first.get("item_type"),
            # New extended fields
            region=first.get("region"),
            delivery_region=first.get("delivery_region"),
            delivery_location=first.get("delivery_location"),
            delivery_address=first.get("delivery_address"),
            economy=first.get("economy"),
            contract_end_date=first.get("contract_end_date"),
            commitment_quarter=first.get("commitment_quarter"),
            planned_payment_month=first.get("planned_payment_month"),
            submission_deadline=first.get("submission_deadline"),
            vat_mode=first.get("vat_mode") or "uniform",
            stage_label=first.get("stage_label"),
        )
        # ПРАВИЛО №6 (2026-09-07): acceptance_doc_name/number/date/amount —
        # производный кэш, пишется ТОЛЬКО через sync_scalars (единственный
        # писатель, см. app.services.acceptance_docs) — здесь вызывается
        # вручную, т.к. это ещё не персистентный ORM-объект (add_doc/
        # replace_docs рассчитаны на уже существующую закупку).
        _acc_docs.sync_scalars(p)

        # --- Create PurchaseItems (dedup by key within group) ---
        items = []
        seen_item_keys: set = set()
        for pr in group_rows:
            # Normalize item key to avoid duplicates for monthly-payment rows
            norm_name = (pr["item_name"] or "").lower().strip()
            item_key = (norm_name, pr["plan_qty"], pr["plan_unit_price"])
            if item_key in seen_item_keys:
                continue
            seen_item_keys.add(item_key)

            item_plan_total = pr["plan_total"] or (
                (pr["plan_qty"] or Decimal(0)) * (pr["plan_unit_price"] or Decimal(0))
            ) or None
            pi = PurchaseItem(
                item_name=pr["item_name"],
                item_type=pr["item_type"],
                quantity=pr["plan_qty"],
                unit=pr["unit"],
                unit_price=pr["plan_unit_price"],
                total_price=item_plan_total,
                final_unit_price=pr["fact_unit_price"],
                final_total=pr["fact_total"],
                country_origin=pr["country_origin"],
                feo_category_id=pr["feo_id"],
                # Аналогично Purchase.vat_rate выше: truthy-check терял 0.
                vat_rate=str(pr["vat_rate"]) if pr["vat_rate"] not in (None, "") else None,
            )
            # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
            _cont_id = pr["cont_id"] if (pr["cont_id"] and pr["cont_id"] != -1) else None
            set_item_contractor(pi, contractor_id=_cont_id, inn=pr["cont_inn"], name=pr["cont_name"])
            items.append(pi)

        p.items = items
        db.add(p)
        await db.flush()  # get p.id

        if contract_num:
            existing_keys.add((contract_num, order_no))
            contract_to_purchase[contract_num] = p

        created_purchases += 1
        created_items += len(items)
        if not first.get("event_id"):
            without_event += 1

        # --- Create Payment records from inline rows ---
        if unique_inline:
            # Anti-dup against already-existing payments (freshly flushed purchase has no payments yet)
            existing_pays_q = (await db.execute(
                select(Payment.document_number, Payment.payment_date, Payment.amount)
                .where(Payment.purchase_id == p.id)
            )).all()

            def _pay_fp(dn, pd, am):
                return (
                    str(dn or "").strip(),
                    str(pd or ""),
                    round(float(am), 2) if am is not None else None,
                )

            existing_fps_inline = {_pay_fp(dn, pd, am) for dn, pd, am in existing_pays_q}

            for ip in unique_inline:
                fp = _pay_fp(ip["document_number"], ip["payment_date"], ip["amount"])
                if fp in existing_fps_inline:
                    continue
                existing_fps_inline.add(fp)
                pay_obj = Payment(
                    purchase_id=p.id,
                    document_number=ip["document_number"],
                    payment_date=ip["payment_date"],
                    amount=ip["amount"],
                    payment_purpose=ip["payment_purpose"],
                )
                db.add(pay_obj)
                created_payments += 1

    # --- Process «Платежи» sheet (commit mode) ---
    if commit and parsed_payments:
        pay_by_contract: Dict[str, List[dict]] = defaultdict(list)
        for pp in parsed_payments:
            pay_by_contract[pp["contract_number"]].append(pp)

        for contract_num, pay_list in pay_by_contract.items():
            # Find the Purchase — may be newly created or already existing
            purchase = contract_to_purchase.get(contract_num)
            if purchase is None:
                # Check DB for existing purchases with this contract_number
                existing_p = (await db.execute(
                    select(Purchase).where(
                        Purchase.subsidy_id == sid,
                        Purchase.contract_number == contract_num,
                    )
                )).scalars().first()
                purchase = existing_p

            if purchase is None:
                for pp in pay_list:
                    payments_errors.append({
                        "row": pp["pay_row_num"],
                        "name": contract_num,
                        "message": f"Платёж: закупка с № договора '{contract_num}' не найдена",
                    })
                continue

            # Anti-dup: fingerprints of payments already stored for this purchase
            existing_pays = (await db.execute(
                select(Payment.document_number, Payment.payment_date, Payment.amount)
                .where(Payment.purchase_id == purchase.id)
            )).all()
            def _pay_fp(dn, pd, am):
                return (
                    str(dn or "").strip(),
                    str(pd or ""),
                    round(float(am), 2) if am is not None else None,
                )
            existing_fps = {_pay_fp(dn, pd, am) for dn, pd, am in existing_pays}

            payment_objects = []
            for pp in pay_list:
                fp = _pay_fp(pp["document_number"], pp["payment_date"], pp["amount"])
                if fp in existing_fps:
                    continue
                existing_fps.add(fp)
                pay_obj = Payment(
                    purchase_id=purchase.id,
                    document_number=pp["document_number"],
                    payment_date=pp["payment_date"],
                    amount=pp["amount"],
                    payment_purpose=pp["payment_purpose"],
                )
                db.add(pay_obj)
                payment_objects.append(pay_obj)
                created_payments += 1

            # Владелец (2026-08-19): платежи из Excel-импорта — это тоже «по нашим
            # данным» (payment_source='manual' по умолчанию на модели,
            # confirmed_by_statement=False), НЕ подтверждённая казначейством
            # оплата. Раньше здесь payment_amount проставлялся напрямую суммой
            # ИМПОРТИРОВАННЫХ платежей — что и выдавало заявленное за
            # подтверждённое. Теперь агрегаты (payment_amount = подтверждено,
            # payment_amount_declared = заявлено) считает recompute_purchase_payments
            # по тем же правилам, что и форма в карточке закупки.
            if payment_objects:
                await recompute_purchase_payments(db, purchase.id)

    elif not commit and parsed_payments:
        # Preview mode: validate payment links only
        for pp in parsed_payments:
            contract_num = pp["contract_number"]
            # Check if any parsed group has this contract_number
            matched = any(
                pr["contract_number"] == contract_num
                for pr in parsed_rows
            )
            if not matched and not any(k[0] == contract_num for k in existing_keys):
                payments_errors.append({
                    "row": pp["pay_row_num"],
                    "name": contract_num,
                    "message": f"Платёж: закупка с № договора '{contract_num}' не найдена",
                })

    if commit:
        await db.commit()
        return {
            "created_purchases": created_purchases,
            "created_items": created_items,
            "created_payments": created_payments,
            "skipped": skipped,
            "errors": errors + payments_errors,
            "warnings": warnings,
            "without_event": without_event,
        }
    else:
        return {
            "purchases": preview_list,
            "payments_errors": payments_errors,
            "skipped": skipped,
            "errors": errors,
            "warnings": warnings,
            "without_event": without_event,
            "duplicates_count": duplicates_count,
            "feo_to_create": sorted(pending_created, key=lambda x: x["path"]),
            "subsidy_has_feo": subsidy_has_feo,
        }
