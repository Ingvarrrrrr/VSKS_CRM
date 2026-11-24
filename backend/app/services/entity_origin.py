"""Service for attaching human-readable entity origin to EntityChange records.

Determines where an entity came from (import run, wish, purchase, statement, manual)
even if the cell was never modified after creation or created before entity_changes table.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_import_run import FeoImportRun
from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.task import Task
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem


def _to_dt(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    return None


async def _user_label(db: AsyncSession, uid: Optional[int]) -> Optional[str]:
    if not isinstance(uid, int):
        return None
    u = await db.get(User, uid)
    return getattr(u, "full_name", None) or getattr(u, "username", None) or None


async def _latest_run(db: AsyncSession, subsidy_id: Optional[int]) -> Optional[FeoImportRun]:
    if not isinstance(subsidy_id, int):
        return None
    q = select(FeoImportRun).where(FeoImportRun.subsidy_id == subsidy_id).order_by(FeoImportRun.id.desc()).limit(1)
    return (await db.execute(q)).scalar_one_or_none()


def _get_val(r: Any, key: str, default: Any = None) -> Any:
    return r.get(key, default) if isinstance(r, dict) else getattr(r, key, default)


def _set_val(r: Any, key: str, val: Any) -> None:
    if isinstance(r, dict):
        r[key] = val
    else:
        setattr(r, key, val)


async def _enrich_created_row(db: AsyncSession, entity_type: str, entity_id: int, r: Any) -> None:
    source, source_ref = _get_val(r, "source"), _get_val(r, "source_ref")
    if not isinstance(source_ref, int):
        source_ref = None

    origin_label: Optional[str] = None
    author: Optional[str] = None
    dt: Optional[datetime] = None

    if source == "import":
        run = await db.get(FeoImportRun, source_ref) if source_ref else None
        fname = f"«{run.filename}»" if (run and getattr(run, "filename", None)) else "файла импорта"
        s_row = ""
        if entity_type == "feo_item":
            item = await db.get(FeoPlannedItem, entity_id)
            if item and isinstance(getattr(item, "source_row", None), int):
                s_row = f" (строка {item.source_row})"
        origin_label = f"Загружено импортом из {fname}{s_row}"
        if run:
            author = getattr(run, "user_name", None) or await _user_label(db, getattr(run, "user_id", None))
            dt = _to_dt(getattr(run, "started_at", None) or getattr(run, "finished_at", None))
    elif source == "wish":
        wish = await db.get(Wish, source_ref) if source_ref else None
        if wish and isinstance(getattr(wish, "id", None), int):
            t = f" «{wish.title}»" if getattr(wish, "title", None) else ""
            origin_label = f"Создано из заявки №{wish.id}{t}"
            author = await _user_label(db, getattr(wish, "created_by", None))
            dt = _to_dt(getattr(wish, "created_at", None))
        else:
            origin_label = f"Создано из заявки №{source_ref}" if source_ref else "Создано из заявки"
    elif source == "purchase":
        p = await db.get(Purchase, source_ref) if source_ref else None
        if p and isinstance(getattr(p, "id", None), int):
            num = getattr(p, "purchase_number", None) or p.id
            s = f" «{p.subject}»" if getattr(p, "subject", None) else ""
            origin_label = f"Создано из закупки №{num}{s}"
            author = await _user_label(db, getattr(p, "assigned_user_id", None) or getattr(p, "service_note_by", None))
            dt = _to_dt(getattr(p, "order_date", None) or getattr(p, "contract_date", None) or getattr(p, "service_note_at", None))
        else:
            origin_label = f"Создано из закупки №{source_ref}" if source_ref else "Создано из закупки"
    elif source == "autoassign":
        origin_label = "Создано автоматически при включении заявки/закупки в план"
    elif source == "collapse":
        origin_label = "Создано при объединении дублирующих направлений ФЭО"
    else:
        origin_label = "Внесено вручную при создании записи"

    _set_val(r, "origin_label", origin_label)
    if author and not _get_val(r, "changed_by_name"):
        _set_val(r, "changed_by_name", author)
    if dt and not _get_val(r, "changed_at"):
        _set_val(r, "changed_at", dt)


async def _resolve_synthetic_origin(
    db: AsyncSession, entity_type: str, entity_id: int
) -> tuple[Optional[str], Optional[str], Optional[int], Optional[datetime], Optional[str], Optional[int]]:
    origin_label, changed_by_name, changed_by_id, changed_at, source, source_ref = None, None, None, None, None, None

    if entity_type == "feo_item":
        item = await db.get(FeoPlannedItem, entity_id)
        if item and isinstance(getattr(item, "id", None), int):
            if getattr(item, "auto_created", None) is True:
                w_row = (await db.execute(select(WishItem.wish_id).where(WishItem.feo_planned_item_id == entity_id).limit(1))).first()
                if w_row and isinstance(w_row[0], int):
                    wish = await db.get(Wish, w_row[0])
                    if wish and isinstance(getattr(wish, "id", None), int):
                        origin_label, source, source_ref = f"Создано из заявки №{wish.id}" + (f" «{wish.title}»" if getattr(wish, "title", None) else ""), "wish", wish.id
                        changed_at = _to_dt(getattr(wish, "created_at", None) or getattr(item, "created_at", None))
                        changed_by_id = getattr(wish, "created_by", None)
                        changed_by_name = await _user_label(db, changed_by_id)
                if not origin_label:
                    p_row = (await db.execute(select(PurchaseItem.purchase_id).where(PurchaseItem.feo_planned_item_id == entity_id).limit(1))).first()
                    if p_row and isinstance(p_row[0], int):
                        p = await db.get(Purchase, p_row[0])
                        if p and isinstance(getattr(p, "id", None), int):
                            num = getattr(p, "purchase_number", None) or p.id
                            origin_label, source, source_ref = f"Создано из закупки №{num}" + (f" «{p.subject}»" if getattr(p, "subject", None) else ""), "purchase", p.id
                            changed_at = _to_dt(getattr(p, "order_date", None) or getattr(p, "contract_date", None) or getattr(item, "created_at", None))
                            changed_by_id = getattr(p, "assigned_user_id", None) or getattr(p, "service_note_by", None)
                            changed_by_name = await _user_label(db, changed_by_id)
                if not origin_label:
                    origin_label, source, changed_at = "Создано автоматически при включении заявки/закупки в план", "autoassign", _to_dt(getattr(item, "created_at", None))
            else:
                cat = await db.get(FeoCategory, item.feo_category_id) if isinstance(getattr(item, "feo_category_id", None), int) else None
                run = await _latest_run(db, getattr(cat, "subsidy_id", None))
                if run and isinstance(getattr(run, "id", None), int):
                    s_row = f" (строка {item.source_row})" if isinstance(getattr(item, "source_row", None), int) else ""
                    origin_label, source, source_ref = f"Загружено из файла «{getattr(run, 'filename', None) or 'ФЭО.xlsx'}»{s_row}", "import", run.id
                    changed_at = _to_dt(getattr(item, "created_at", None) or getattr(run, "started_at", None))
                    changed_by_name = getattr(run, "user_name", None) or await _user_label(db, getattr(run, "user_id", None))
                    changed_by_id = getattr(run, "user_id", None)
                elif isinstance(getattr(item, "source_row", None), int):
                    origin_label, source, changed_at = f"Загружено при импорте файла ФЭО (строка {item.source_row})", "import", _to_dt(getattr(item, "created_at", None))
                else:
                    origin_label, source, changed_at = "Внесено в план закупок", "manual", _to_dt(getattr(item, "created_at", None))

    elif entity_type == "feo_category":
        cat = await db.get(FeoCategory, entity_id)
        if cat and isinstance(getattr(cat, "id", None), int):
            run = await _latest_run(db, getattr(cat, "subsidy_id", None))
            if run and isinstance(getattr(run, "id", None), int):
                origin_label, source, source_ref = f"Загружено при импорте ФЭО «{getattr(run, 'filename', None) or 'ФЭО.xlsx'}»", "import", run.id
                changed_at = _to_dt(getattr(run, "started_at", None) or getattr(run, "finished_at", None))
                changed_by_name = getattr(run, "user_name", None) or await _user_label(db, getattr(run, "user_id", None))
                changed_by_id = getattr(run, "user_id", None)
            else:
                sub_name = ""
                if isinstance(getattr(cat, "subsidy_id", None), int):
                    sub = await db.get(Subsidy, cat.subsidy_id)
                    if sub and isinstance(getattr(sub, "id", None), int):
                        sub_name, changed_at = f" «{sub.name}»", _to_dt(getattr(sub, "approved_at", None))
                        changed_by_id = getattr(sub, "created_by", None)
                        changed_by_name = await _user_label(db, changed_by_id)
                origin_label, source = f"Создано в структуре субсидии{sub_name}", "manual"

    elif entity_type == "purchase":
        p = await db.get(Purchase, entity_id)
        if p and isinstance(getattr(p, "id", None), int):
            changed_at = _to_dt(getattr(p, "order_date", None) or getattr(p, "contract_date", None) or getattr(p, "service_note_at", None))
            if isinstance(getattr(p, "wish_id", None), int):
                origin_label, source, source_ref = f"Сформировано из заявки №{p.wish_id}", "wish", p.wish_id
                w = await db.get(Wish, p.wish_id)
                if w and isinstance(getattr(w, "id", None), int):
                    changed_at = _to_dt(getattr(w, "created_at", None) or changed_at)
                    changed_by_id = getattr(w, "created_by", None)
                    changed_by_name = await _user_label(db, changed_by_id)
            else:
                origin_label, source = "Внесено при создании закупки", "manual"
            if not changed_by_name:
                changed_by_id = getattr(p, "assigned_user_id", None) or getattr(p, "service_note_by", None)
                changed_by_name = await _user_label(db, changed_by_id)

    elif entity_type == "wish":
        w = await db.get(Wish, entity_id)
        if w and isinstance(getattr(w, "id", None), int):
            origin_label, source, changed_at = f"Внесено при создании заявки №{w.id}", "manual", _to_dt(getattr(w, "created_at", None))
            changed_by_id = getattr(w, "created_by", None)
            changed_by_name = await _user_label(db, changed_by_id)

    elif entity_type == "contract":
        c = await db.get(Contract, entity_id)
        if c and isinstance(getattr(c, "id", None), int):
            num_str = f" №{c.number}" if getattr(c, "number", None) else ""
            origin_label, source = f"Внесено при оформлении договора{num_str}", "manual"
            changed_at = _to_dt(getattr(c, "date", None) or getattr(c, "start_date", None))
            p = (await db.execute(select(Purchase).where(Purchase.contract_id == c.id).limit(1))).scalar_one_or_none()
            if p and isinstance(getattr(p, "id", None), int):
                changed_by_id = getattr(p, "assigned_user_id", None) or getattr(p, "service_note_by", None)
                changed_by_name = await _user_label(db, changed_by_id)

    elif entity_type == "payment":
        pay = await db.get(Payment, entity_id)
        if pay and isinstance(getattr(pay, "id", None), int):
            changed_at = _to_dt(getattr(pay, "payment_date", None))
            b_id, r_id = getattr(pay, "bank_payment_id", None), getattr(pay, "import_run_id", None)
            if isinstance(b_id, int) or isinstance(r_id, int) or getattr(pay, "confirmed_by_statement", None) is True:
                origin_label, source = "Загружено из банковской выписки", "import"
                source_ref = b_id if isinstance(b_id, int) else (r_id if isinstance(r_id, int) else None)
            else:
                origin_label, source = "Внесено при регистрации платежа", "manual"
            if isinstance(getattr(pay, "purchase_id", None), int):
                p = await db.get(Purchase, pay.purchase_id)
                if p and isinstance(getattr(p, "assigned_user_id", None), int):
                    changed_by_id = p.assigned_user_id
                    changed_by_name = await _user_label(db, changed_by_id)

    elif entity_type == "task":
        t = await db.get(Task, entity_id)
        if t and isinstance(getattr(t, "id", None), int):
            origin_label, source, changed_at = "Внесено при постановке задачи", "manual", _to_dt(getattr(t, "created_at", None))
            changed_by_id = getattr(t, "created_by_id", None)
            changed_by_name = await _user_label(db, changed_by_id)

    elif entity_type == "subsidy":
        sub = await db.get(Subsidy, entity_id)
        if sub and isinstance(getattr(sub, "id", None), int):
            origin_label, source, changed_at = "Заведено при создании субсидии", "manual", _to_dt(getattr(sub, "approved_at", None))
            changed_by_id = getattr(sub, "created_by", None)
            changed_by_name = await _user_label(db, changed_by_id)

    return origin_label, changed_by_name, changed_by_id, changed_at, source, source_ref


async def attach_entity_origin(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    rows: list[Any],
) -> list[Any]:
    """Ensure change history contains origin_label on __created__ row."""
    out_list = list(rows)
    created_items = [r for r in out_list if _get_val(r, "field_name") == "__created__"]

    if created_items:
        for r in created_items:
            await _enrich_created_row(db, entity_type, entity_id, r)
        return out_list

    (origin_label, changed_by_name, changed_by_id,
     changed_at, source, source_ref) = await _resolve_synthetic_origin(db, entity_type, entity_id)

    if not origin_label:
        return out_list

    from app.routers.entity_changes import EntityChangeOut

    synth = EntityChangeOut(
        id=0,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name="__created__",
        old_value=None,
        new_value=None,
        changed_by_id=changed_by_id,
        changed_by_name=changed_by_name,
        changed_at=changed_at,
        source=source,
        source_ref=source_ref,
        origin_label=origin_label,
    )
    if out_list and isinstance(out_list[0], dict):
        out_list.append(synth.model_dump())
    else:
        out_list.append(synth)
    return out_list
