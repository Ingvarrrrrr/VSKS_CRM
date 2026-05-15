"""Purchase receipts router (Phase 21).

5 endpoints scoped under /api/purchases/{purchase_id}/receipts:
  GET    /                — list receipts of a purchase
  POST   /import-json     — multipart upload of FNS mobile-app JSON export
  POST   /from-qr         — body { qr: "t=...&s=...&fn=..." } from QR scan
  POST   /                — manual entry (fiscal data + optional items)
  DELETE /{receipt_id}    — remove a receipt (related PurchaseItems stay)

Idempotent on (fiscal_drive_number, fiscal_document_number, fiscal_sign):
re-importing the same receipt returns the existing row, items not duplicated.
"""
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import List

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_receipt import PurchaseReceipt
from app.models.user import User
from app.product_matcher import find_matching_product
from app.schemas.schemas import ReceiptCreate, ReceiptOut


router = APIRouter(prefix="/api/purchases", tags=["receipts"])


# ── helpers ──────────────────────────────────────────────────────────────────
def _kop_to_rub(v):
    """Convert копейки → рубли. Accepts None / int / float / str."""
    if v is None:
        return None
    try:
        return (Decimal(str(v)) / Decimal('100')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    return None


def _parse_fns_json_receipt(raw: dict) -> dict:
    """Map a single FNS-mobile-app JSON entry → dict with internal field names."""
    r = (
        (raw.get('ticket') or {}).get('document', {}).get('receipt')
        or raw.get('receipt')
        or raw
    ) or {}

    items = []
    for it in (r.get('items') or []):
        try:
            qty = Decimal(str(it.get('quantity') or 1))
        except Exception:
            qty = Decimal('1')
        items.append({
            'name': (it.get('name') or '').strip(),
            'quantity': qty,
            'price': _kop_to_rub(it.get('price')),
            'sum': _kop_to_rub(it.get('sum')),
            'nds': it.get('nds'),
        })

    fd_num = r.get('fiscalDocumentNumber')
    if isinstance(fd_num, str) and fd_num.isdigit():
        fd_num = int(fd_num)
    elif not isinstance(fd_num, int):
        fd_num = None

    return {
        'fiscal_drive_number': (str(r.get('fiscalDriveNumber') or '').strip() or None),
        'fiscal_document_number': fd_num,
        'fiscal_sign': (str(r.get('fiscalSign') or '').strip() or None),
        'kkt_reg_id': (str(r.get('kktRegId') or '').strip() or None),
        'receipt_datetime': _parse_dt(r.get('dateTime')),
        'total_sum': _kop_to_rub(r.get('totalSum')),
        'cash_sum': _kop_to_rub(r.get('cashTotalSum')),
        'ecash_sum': _kop_to_rub(r.get('ecashTotalSum')),
        'prepaid_sum': _kop_to_rub(r.get('prepaidSum')),
        'nds_sum': _kop_to_rub(r.get('ndsSum')),
        'seller_name': ((r.get('user') or '').strip() or None),
        'seller_inn': (str(r.get('userInn') or '').strip() or None),
        'retail_place': r.get('retailPlace'),
        'retail_place_address': r.get('retailPlaceAddress'),
        'operator': r.get('operator'),
        'operator_inn': (str(r.get('operatorInn') or '').strip() or None),
        'taxation_type': r.get('appliedTaxationType') or r.get('taxationType'),
        'items': items,
    }


def _parse_qr_string(qr: str) -> dict:
    """Parse QR string `t=...&s=...&fn=...&i=...&fp=...&n=...` → dict."""
    parts = {}
    for chunk in (qr or '').strip().split('&'):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            parts[k.strip()] = v.strip()

    dt = None
    if 't' in parts:
        s = parts['t']
        for fmt in ('%Y%m%dT%H%M%S', '%Y%m%dT%H%M'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                continue

    total = None
    if 's' in parts:
        try:
            total = Decimal(parts['s'])
        except Exception:
            total = None

    fd_num = None
    if parts.get('i', '').isdigit():
        fd_num = int(parts['i'])

    return {
        'fiscal_drive_number': parts.get('fn') or None,
        'fiscal_document_number': fd_num,
        'fiscal_sign': parts.get('fp') or None,
        'receipt_datetime': dt,
        'total_sum': total,
    }


def _items_match_score(item_a, item_b) -> int:
    """
    Phase 26-BB: возвращает количество совпавших полей (0-4) для сопоставления
    позиции из БД (item_a — ORM объект) и позиции из raw_json чека (item_b — dict).
    Поля: name (similarity >= 0.7), quantity, unit_price, total_price.
    item_b['price'] и item_b['sum'] — уже в рублях (прошли через _extract_items или _parse_fns_json_receipt).
    """
    import difflib
    score = 0
    # name
    name_a = (getattr(item_a, 'item_name', None) or '').strip().lower()
    name_b = str(item_b.get('name') or '').strip().lower()
    if name_a and name_b:
        sim = difflib.SequenceMatcher(None, name_a, name_b).ratio()
        if sim >= 0.7:
            score += 1
    # quantity
    try:
        qa = Decimal(str(item_a.quantity or 0))
        qb = Decimal(str(item_b.get('quantity') or item_b.get('qty') or 0))
        if qa > 0 and qb > 0:
            ratio = abs(qa - qb) / max(qa, qb)
            if ratio <= Decimal('0.01'):
                score += 1
    except Exception:
        pass
    # unit_price
    try:
        pa = Decimal(str(item_a.unit_price or 0))
        pb = Decimal(str(item_b.get('price') or 0))
        if abs(pa - pb) <= Decimal('0.01'):
            score += 1
    except Exception:
        pass
    # total_price
    try:
        ta = Decimal(str(item_a.total_price or 0))
        tb_raw = item_b.get('sum') or item_b.get('total')
        tb = Decimal(str(tb_raw or 0))
        if abs(ta - tb) <= Decimal('0.01'):
            score += 1
    except Exception:
        pass
    return score


async def _create_receipt_with_items(
    purchase_id: int,
    data: dict,
    source: str,
    raw_payload,
    db: AsyncSession,
) -> PurchaseReceipt:
    """Insert PurchaseReceipt + auto-create PurchaseItem rows.

    Idempotent on the (fn, fd, fp) triple — re-importing the same receipt
    returns the already-existing row without duplicating items.
    """
    fn = data.get('fiscal_drive_number')
    fd = data.get('fiscal_document_number')
    fp = data.get('fiscal_sign')
    if fn and fd and fp:
        existing = (await db.execute(
            select(PurchaseReceipt).where(
                PurchaseReceipt.fiscal_drive_number == fn,
                PurchaseReceipt.fiscal_document_number == fd,
                PurchaseReceipt.fiscal_sign == fp,
            )
        )).scalar_one_or_none()
        if existing:
            if existing.purchase_id == purchase_id:
                return existing
            other = await db.get(Purchase, existing.purchase_id)
            ref = (other and (other.registry_number or other.purchase_number)) or f"#{existing.purchase_id}"
            raise HTTPException(
                409,
                f"Этот чек уже привязан к авансовому отчёту {ref}. Добавьте другой чек.",
            )

    # Soft duplicate check для ручного ввода (без фискальной тройки).
    # Связка (seller_inn + receipt_datetime + total_sum) — если уже есть
    # чек с такой же комбинацией, предупреждаем что данный чек заведён.
    seller_inn = data.get('seller_inn')
    receipt_dt = data.get('receipt_datetime')
    total_sum = data.get('total_sum')
    if seller_inn and receipt_dt and total_sum is not None:
        dup_q = select(PurchaseReceipt).where(
            PurchaseReceipt.seller_inn == seller_inn,
            PurchaseReceipt.receipt_datetime == receipt_dt,
            PurchaseReceipt.total_sum == total_sum,
        )
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            other = await db.get(Purchase, dup.purchase_id)
            ref = (other and (other.registry_number or other.purchase_number)) or f"#{dup.purchase_id}"
            raise HTTPException(
                409,
                f"Чек с такой же датой, ИНН продавца и суммой уже заведён в авансовом отчёте {ref}.",
            )

    items_data = data.pop('items', None) or []

    # Auto-create/find contractor по ИНН продавца из чека
    seller_inn = data.get('seller_inn')
    seller_name = data.get('seller_name')
    contractor_id_for_items = None
    if seller_inn:
        from app.models.contractor import Contractor as _Contractor
        existing_c = (await db.execute(
            select(_Contractor).where(_Contractor.inn == seller_inn)
        )).scalar_one_or_none()
        if existing_c:
            contractor_id_for_items = existing_c.id
        else:
            new_c = _Contractor(inn=seller_inn, name=seller_name or f"ИНН {seller_inn}")
            db.add(new_c)
            await db.flush()
            contractor_id_for_items = new_c.id

    valid_cols = {c.key for c in PurchaseReceipt.__table__.columns}
    receipt_kwargs = {k: v for k, v in data.items() if k in valid_cols}

    receipt = PurchaseReceipt(
        purchase_id=purchase_id,
        source=source,
        raw_json=raw_payload,
        **receipt_kwargs,
    )
    db.add(receipt)
    await db.flush()

    # Phase 26-BB: дедуплицировать existing items закупки без receipt_id
    # (ручные позиции или legacy). Если найден match >= 3/4 полей — linklink
    # на этот чек и overwrite contractor.
    existing_q = await db.execute(
        select(PurchaseItem).where(
            PurchaseItem.purchase_id == purchase_id,
            PurchaseItem.receipt_id.is_(None),
        )
    )
    existing_unlinked = list(existing_q.scalars().all())

    for idx, it in enumerate(items_data, start=1):
        try:
            qty = Decimal(str(it.get('quantity') or 1))
        except Exception:
            qty = Decimal('1')
        price = it.get('price') or Decimal('0')
        total = it.get('sum')
        if total is None:
            try:
                total = (qty * Decimal(str(price))).quantize(Decimal('0.01'))
            except Exception:
                total = Decimal('0')
        raw_name = (it.get('name') or f'Позиция {idx}')[:5000]

        # Phase 26-BB: попытаться найти match среди existing unlinked
        matched_existing = None
        best_score = 0
        for ex in existing_unlinked:
            s = _items_match_score(ex, it)
            if s >= 2 and s > best_score:
                best_score = s
                matched_existing = ex

        if matched_existing is not None:
            matched_existing.receipt_id = receipt.id
            matched_existing.contractor_id = contractor_id_for_items
            matched_existing.contractor_inn = seller_inn
            matched_existing.contractor_name = seller_name
            if it.get('vat_rate') and not matched_existing.vat_rate:
                matched_existing.vat_rate = it.get('vat_rate')
            existing_unlinked.remove(matched_existing)
            continue  # пропустить создание нового PurchaseItem

        # Phase 21.06+: token-set fuzzy match against catalog. Catches names
        # like "Карабин Ozone..." vs "Ozone..." (where the type is stored in
        # Product.product_type, not in the name itself). Matched items are
        # marked unconfirmed so the user verifies each one.
        matched = await find_matching_product(db, raw_name)
        matched_id = matched.id if matched else None
        db.add(PurchaseItem(
            purchase_id=purchase_id,
            product_id=matched_id,
            item_name=raw_name,
            quantity=qty,
            unit='шт.',
            unit_price=price,
            total_price=total,
            match_confirmed=False,
            contractor_id=contractor_id_for_items,
            contractor_inn=seller_inn,
            contractor_name=seller_name,
            receipt_id=receipt.id,  # Phase 26-BB
            vat_rate=it.get('vat_rate'),
        ))

    await db.commit()
    await db.refresh(receipt)

    # Phase 26-II: для advance закупок — автосоздать ContractItem (стадия «Договор»)
    # параллельно каждой PurchaseItem (стадия «ТЗ»), копируя name/qty/price.
    # Для авансовых чек одновременно играет роль и ТЗ, и Договора, и Поставки.
    try:
        p_check = await db.get(Purchase, purchase_id)
        if p_check and p_check.purchase_method == 'advance':
            from app.models.contract_item import ContractItem as _CI
            new_items_q = await db.execute(
                select(PurchaseItem).where(
                    PurchaseItem.purchase_id == purchase_id,
                    PurchaseItem.receipt_id == receipt.id,
                )
            )
            for pi in new_items_q.scalars().all():
                exists_ci = (await db.execute(
                    select(_CI).where(
                        _CI.purchase_id == purchase_id,
                        _CI.source_item_id == pi.id,
                    ).limit(1)
                )).scalar_one_or_none()
                if exists_ci:
                    continue
                db.add(_CI(
                    purchase_id=purchase_id,
                    source_item_id=pi.id,
                    name=pi.item_name or "Позиция",
                    quantity=pi.quantity,
                    unit=pi.unit or 'шт.',
                    unit_price=pi.unit_price,
                    total=pi.total_price,
                    match_confirmed=True,
                ))
            await db.commit()
    except Exception as _ci_exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"contract_items autocreate skipped: {_ci_exc}")

    # Auto-fill contract_date / contract_number for advance purchases.
    # First receipt sets the basis; bank_payment match will override later.
    p = await db.get(Purchase, purchase_id)
    if p and p.purchase_method == 'advance':
        from sqlalchemy.orm import attributes as _orm_attrs
        changed = False
        rd = receipt.receipt_datetime
        if rd and not p.contract_date:
            p.contract_date = rd.date() if hasattr(rd, 'date') else rd
            changed = True
        if receipt.fiscal_document_number and not p.contract_number:
            p.contract_number = str(receipt.fiscal_document_number)
            changed = True

        # Phase 26-W: чек → файл в покупке + ссылка в acceptance_docs
        pf_id = None
        try:
            import os as _os, hashlib as _hashlib
            from app.models.purchase_file import PurchaseFile as _PF
            UPLOAD_DIR = _os.environ.get('UPLOAD_DIR', '/data/uploads')
            png_bytes = _render_receipt_png(receipt)
            content_hash = _hashlib.sha256(png_bytes).hexdigest()
            # Dedup: если файл с таким hash уже привязан к этой закупке — переиспользовать
            existing_pf = (await db.execute(
                select(_PF).where(
                    _PF.purchase_id == purchase_id,
                    _PF.content_hash == content_hash,
                ).limit(1)
            )).scalar_one_or_none()
            if existing_pf:
                pf_id = existing_pf.id
            else:
                dest_dir = _os.path.join(UPLOAD_DIR, str(purchase_id))
                _os.makedirs(dest_dir, exist_ok=True)
                receipt_label = f"check_{receipt.fiscal_document_number or receipt.id}.png"
                dest_path = _os.path.join(dest_dir, receipt_label)
                with open(dest_path, 'wb') as _f:
                    _f.write(png_bytes)
                pf = _PF(
                    purchase_id=purchase_id,
                    filename=receipt_label,
                    original_name=f"Чек № {receipt.fiscal_document_number or receipt.id}.png",
                    filepath=dest_path,
                    mime_type='image/png',
                    size=len(png_bytes),
                    file_type='acceptance_doc',
                    doc_format='scan',
                    content_hash=content_hash,
                    is_active=True,
                )
                db.add(pf)
                await db.flush()
                pf_id = pf.id
        except Exception as _attach_exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"receipt {receipt.id} file attach skipped: {_attach_exc}")
            pf_id = None

        # U-4: auto-add чек в acceptance_docs (только для авансовых, дедуп по receipt_id)
        new_doc = {
            "type": "Чек",
            "number": str(receipt.fiscal_document_number or ""),
            "date": receipt.receipt_datetime.date().isoformat() if receipt.receipt_datetime else None,
            "amount": float(receipt.total_sum) if receipt.total_sum is not None else None,
            "source": "receipt",
            "receipt_id": receipt.id,
            "file_id": pf_id,
        }
        existing_docs = list(p.acceptance_docs or [])
        if not any(d.get("receipt_id") == receipt.id for d in existing_docs):
            existing_docs.append(new_doc)
            p.acceptance_docs = existing_docs
            _orm_attrs.flag_modified(p, "acceptance_docs")
            changed = True
        else:
            # Обновить file_id в уже существующей записи, если он был NULL
            updated_docs = []
            for d in existing_docs:
                if d.get("receipt_id") == receipt.id and d.get("file_id") is None and pf_id is not None:
                    d = dict(d)
                    d["file_id"] = pf_id
                    changed = True
                updated_docs.append(d)
            if updated_docs != existing_docs:
                p.acceptance_docs = updated_docs
                _orm_attrs.flag_modified(p, "acceptance_docs")

        if changed:
            await db.commit()

    return receipt


# ── core helper (Phase 26-Z-bootstrap) ───────────────────────────────────────

async def _recompute_from_receipts_core(purchase_id: int, db: AsyncSession) -> dict:
    """Idempotent recompute. Returns stats dict. Не кидает HTTPException."""
    from sqlalchemy.orm import attributes as _orm_attrs
    p = await db.get(Purchase, purchase_id)
    if not p:
        return {"ok": False, "reason": "not_found", "items_updated": 0, "files_attached": 0, "acceptance_docs_added": 0}

    receipts_q = await db.execute(
        select(PurchaseReceipt)
        .where(PurchaseReceipt.purchase_id == purchase_id)
        .order_by(PurchaseReceipt.id.asc())
    )
    receipts = receipts_q.scalars().all()

    if not receipts:
        return {"ok": True, "message": "Чеков нет — нечего пересчитывать", "items_updated": 0, "files_attached": 0, "acceptance_docs_added": 0}

    items_updated = 0
    files_attached = 0
    acceptance_docs_added = 0

    # 1. Покупка-уровень: contractor_id + contract_date + contract_number
    first_receipt = receipts[0]
    if first_receipt.seller_inn and not p.contractor_id:
        # Resolve/create Contractor
        from app.models.contractor import Contractor as _Ctr
        c_row = (await db.execute(
            select(_Ctr).where(_Ctr.inn == first_receipt.seller_inn)
        )).scalar_one_or_none()
        if not c_row:
            c_row = _Ctr(inn=first_receipt.seller_inn, name=first_receipt.seller_name or f"ИНН {first_receipt.seller_inn}")
            db.add(c_row)
            await db.flush()
        p.contractor_id = c_row.id
    if first_receipt.receipt_datetime and not p.contract_date:
        rd = first_receipt.receipt_datetime
        p.contract_date = rd.date() if hasattr(rd, 'date') else rd
    if first_receipt.fiscal_document_number and not p.contract_number:
        p.contract_number = str(first_receipt.fiscal_document_number)

    # 2. Items-уровень: Phase 26-BB per-receipt mapping
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.contractor import Contractor as _Ctr
    from decimal import Decimal as _Dec

    # Построить map: receipt_id → (contractor_id, inn, name)
    receipt_to_contractor = {}
    for r in receipts:
        if not r.seller_inn:
            continue
        c_row = (await db.execute(
            select(_Ctr).where(_Ctr.inn == r.seller_inn)
        )).scalar_one_or_none()
        if not c_row:
            c_row = _Ctr(inn=r.seller_inn, name=r.seller_name or f"ИНН {r.seller_inn}")
            db.add(c_row)
            await db.flush()
        receipt_to_contractor[r.id] = (c_row.id, r.seller_inn, r.seller_name)

    # Phase 26-WW dedup: удалить точные дубликаты PurchaseItem (если recompute запустился
    # дважды и наплодил). Группа дубликатов = одинаковые (item_name, total_price, receipt_id)
    # внутри одного purchase. Оставляем минимальный id, остальные DELETE.
    dedup_q = await db.execute(
        select(_PI.id, _PI.item_name, _PI.total_price, _PI.receipt_id)
        .where(_PI.purchase_id == purchase_id)
        .order_by(_PI.id.asc())
    )
    seen = {}  # key=(name, total, receipt_id) → first id
    ids_to_delete = []
    for row in dedup_q.all():
        iid, name, total, rid = row
        key = (str(name or '').strip().lower(), str(total or ''), rid)
        if key in seen:
            ids_to_delete.append(iid)
        else:
            seen[key] = iid
    items_deduplicated = 0
    if ids_to_delete:
        from app.models.contract_item import ContractItem as _CI
        from sqlalchemy import update as _sa_update, delete as _sa_delete
        # Снять FK ContractItem.source_item_id → SET NULL, иначе FK violation
        try:
            await db.execute(
                _sa_update(_CI)
                .where(_CI.source_item_id.in_(ids_to_delete))
                .values(source_item_id=None)
            )
        except Exception:
            pass
        await db.execute(
            _sa_delete(_PI).where(_PI.id.in_(ids_to_delete))
        )
        items_deduplicated = len(ids_to_delete)
        await db.flush()

    # Phase 26-WW: если у Purchase УЖЕ есть PurchaseItem (даже legacy без receipt_id),
    # не создавать новые из raw_json — fuzzy match (шаг B ниже) привяжет их к receipt'ам.
    # Иначе получаем дубликаты: 4 legacy + 4 autocreate = 8.
    existing_total = (await db.execute(
        select(func.count()).select_from(_PI).where(_PI.purchase_id == purchase_id)
    )).scalar_one()

    # Phase 26-DD: если в БД для receipt НЕТ привязанных PurchaseItem,
    # но raw_json содержит товары — создать PurchaseItem из raw_json.
    # Это закрывает кейс «чек загружен, items_data не распарсился при импорте».
    items_autocreated = 0
    if not existing_total:
        for r in receipts:
            linked_count = (await db.execute(
                select(_PI).where(_PI.purchase_id == purchase_id, _PI.receipt_id == r.id)
            )).scalars().all()
            if linked_count:
                continue  # уже есть items этого чека
            raw_items = _extract_items(r.raw_json or {})
            if not raw_items:
                continue
            pack = receipt_to_contractor.get(r.id)
            cid, c_inn, c_name = pack if pack else (None, r.seller_inn, r.seller_name)
            for idx, ri in enumerate(raw_items, start=1):
                try:
                    qty = _Dec(str(ri.get('quantity') or 1))
                except Exception:
                    qty = _Dec('1')
                try:
                    price = _Dec(str(ri.get('price') or 0))
                except Exception:
                    price = _Dec('0')
                try:
                    total = _Dec(str(ri.get('sum') or ri.get('total') or (qty * price)))
                except Exception:
                    total = _Dec('0')
                raw_name = (str(ri.get('name') or f"Позиция {idx}"))[:5000]
                db.add(_PI(
                    purchase_id=purchase_id,
                    item_name=raw_name,
                    quantity=qty,
                    unit='шт.',
                    unit_price=price,
                    total_price=total,
                    match_confirmed=False,
                    contractor_id=cid,
                    contractor_inn=c_inn,
                    contractor_name=c_name,
                    receipt_id=r.id,
                    vat_rate=ri.get('vat_rate'),
                ))
                items_autocreated += 1
        if items_autocreated:
            await db.flush()

    # Шаг A: items с receipt_id → overwrite contractor если mismatch
    linked_items_q = await db.execute(
        select(_PI).where(
            _PI.purchase_id == purchase_id,
            _PI.receipt_id.is_not(None),
        )
    )
    for it in linked_items_q.scalars().all():
        pack = receipt_to_contractor.get(it.receipt_id)
        if not pack:
            continue
        cid, c_inn, c_name = pack
        if it.contractor_id != cid:
            it.contractor_id = cid
            it.contractor_inn = c_inn
            it.contractor_name = c_name
            items_updated += 1

    # Шаг B: items без receipt_id → fuzzy match по raw_json чеков
    unlinked_q = await db.execute(
        select(_PI).where(
            _PI.purchase_id == purchase_id,
            _PI.receipt_id.is_(None),
        )
    )
    unlinked = unlinked_q.scalars().all()
    items_linked_by_fuzzy = 0
    for it in unlinked:
        best_receipt = None
        best_score = 0
        for r in receipts:
            items_list = _extract_items(r.raw_json or {})
            for ri in items_list:
                score = _items_match_score(it, ri)
                if score >= 2 and score > best_score:
                    best_score = score
                    best_receipt = r
        if best_receipt:
            it.receipt_id = best_receipt.id
            pack = receipt_to_contractor.get(best_receipt.id)
            if pack:
                cid, c_inn, c_name = pack
                it.contractor_id = cid
                it.contractor_inn = c_inn
                it.contractor_name = c_name
            items_updated += 1
            items_linked_by_fuzzy += 1

    # 3. acceptance_docs + PurchaseFile для каждого receipt
    import os as _os, hashlib as _hashlib
    from app.models.purchase_file import PurchaseFile as _PF
    UPLOAD_DIR = _os.environ.get('UPLOAD_DIR', '/data/uploads')
    existing_docs = list(p.acceptance_docs or [])
    existing_receipt_ids = {d.get("receipt_id") for d in existing_docs if d.get("receipt_id")}
    docs_changed = False

    for r in receipts:
        if r.id in existing_receipt_ids:
            # Запись уже есть, но проверим file_id
            for d in existing_docs:
                if d.get("receipt_id") == r.id and not d.get("file_id"):
                    # Попробовать прикрепить файл
                    try:
                        png_bytes = _render_receipt_png(r)
                        content_hash = _hashlib.sha256(png_bytes).hexdigest()
                        existing_pf = (await db.execute(
                            select(_PF).where(_PF.purchase_id == purchase_id, _PF.content_hash == content_hash).limit(1)
                        )).scalar_one_or_none()
                        if existing_pf:
                            d["file_id"] = existing_pf.id
                            docs_changed = True
                        else:
                            dest_dir = _os.path.join(UPLOAD_DIR, str(purchase_id))
                            _os.makedirs(dest_dir, exist_ok=True)
                            receipt_label = f"check_{r.fiscal_document_number or r.id}.png"
                            dest_path = _os.path.join(dest_dir, receipt_label)
                            with open(dest_path, 'wb') as _f:
                                _f.write(png_bytes)
                            pf = _PF(
                                purchase_id=purchase_id,
                                filename=receipt_label,
                                original_name=f"Чек № {r.fiscal_document_number or r.id}.png",
                                filepath=dest_path,
                                mime_type='image/png',
                                size=len(png_bytes),
                                file_type='acceptance_doc',
                                doc_format='scan',
                                content_hash=content_hash,
                                is_active=True,
                            )
                            db.add(pf)
                            await db.flush()
                            d["file_id"] = pf.id
                            files_attached += 1
                            docs_changed = True
                    except Exception:
                        pass
            continue

        # Новая запись
        pf_id = None
        try:
            png_bytes = _render_receipt_png(r)
            content_hash = _hashlib.sha256(png_bytes).hexdigest()
            existing_pf = (await db.execute(
                select(_PF).where(_PF.purchase_id == purchase_id, _PF.content_hash == content_hash).limit(1)
            )).scalar_one_or_none()
            if existing_pf:
                pf_id = existing_pf.id
            else:
                dest_dir = _os.path.join(UPLOAD_DIR, str(purchase_id))
                _os.makedirs(dest_dir, exist_ok=True)
                receipt_label = f"check_{r.fiscal_document_number or r.id}.png"
                dest_path = _os.path.join(dest_dir, receipt_label)
                with open(dest_path, 'wb') as _f:
                    _f.write(png_bytes)
                pf = _PF(
                    purchase_id=purchase_id,
                    filename=receipt_label,
                    original_name=f"Чек № {r.fiscal_document_number or r.id}.png",
                    filepath=dest_path,
                    mime_type='image/png',
                    size=len(png_bytes),
                    file_type='acceptance_doc',
                    doc_format='scan',
                    content_hash=content_hash,
                    is_active=True,
                )
                db.add(pf)
                await db.flush()
                pf_id = pf.id
                files_attached += 1
        except Exception as _e:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"recompute receipt {r.id} png skipped: {_e}")

        existing_docs.append({
            "type": "Чек",
            "number": str(r.fiscal_document_number or ""),
            "date": r.receipt_datetime.date().isoformat() if r.receipt_datetime else None,
            "amount": float(r.total_sum) if r.total_sum is not None else None,
            "source": "receipt",
            "receipt_id": r.id,
            "file_id": pf_id,
        })
        acceptance_docs_added += 1
        docs_changed = True

    if docs_changed:
        p.acceptance_docs = existing_docs
        _orm_attrs.flag_modified(p, "acceptance_docs")

    # Phase 26-II: ContractItem autocreate (стадия «Договор» = копия ТЗ для advance)
    contract_items_created = 0
    try:
        if p.purchase_method == 'advance':
            from app.models.contract_item import ContractItem as _CI
            all_items = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
            )).scalars().all()
            for pi in all_items:
                exists_ci = (await db.execute(
                    select(_CI).where(
                        _CI.purchase_id == purchase_id,
                        _CI.source_item_id == pi.id,
                    ).limit(1)
                )).scalar_one_or_none()
                if exists_ci:
                    continue
                db.add(_CI(
                    purchase_id=purchase_id,
                    source_item_id=pi.id,
                    name=pi.item_name or "Позиция",
                    quantity=pi.quantity,
                    unit=pi.unit or 'шт.',
                    unit_price=pi.unit_price,
                    total=pi.total_price,
                    match_confirmed=True,
                ))
                contract_items_created += 1
    except Exception as _ci_exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"recompute contract_items autocreate skipped: {_ci_exc}")

    await db.commit()
    return {
        "ok": True,
        "purchase_id": purchase_id,
        "receipts_count": len(receipts),
        "items_updated": items_updated,
        "items_linked_by_fuzzy": items_linked_by_fuzzy,
        "items_autocreated": items_autocreated,
        "items_deduplicated": items_deduplicated,
        "contract_items_created": contract_items_created,
        "files_attached": files_attached,
        "acceptance_docs_added": acceptance_docs_added,
    }


# ── endpoints ────────────────────────────────────────────────────────────────

@router.post("/{purchase_id}/recompute-from-receipts")
async def recompute_from_receipts(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Phase 26-Z: ручной пересчёт авансовой закупки из её PurchaseReceipt.
    Идемпотентно. Thin wrapper над _recompute_from_receipts_core.
    """
    p = await db.get(Purchase, purchase_id)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    return await _recompute_from_receipts_core(purchase_id, db)


@router.get("/{purchase_id}/receipts", response_model=List[ReceiptOut])
async def list_receipts(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(PurchaseReceipt)
        .where(PurchaseReceipt.purchase_id == purchase_id)
        .order_by(PurchaseReceipt.created_at.desc())
    )).scalars().all()
    return rows


@router.post("/{purchase_id}/receipts/import-json", response_model=List[ReceiptOut])
async def import_receipt_json(
    purchase_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Import one or more receipts from FNS mobile-app JSON export."""
    if not (file.filename or "").lower().endswith('.json'):
        raise HTTPException(400, "Поддерживается только .json")

    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    content = await file.read()
    try:
        payload = json.loads(content)
    except Exception:
        raise HTTPException(400, "Не удалось распарсить JSON")

    if not isinstance(payload, list):
        payload = [payload]

    results: List[PurchaseReceipt] = []
    conflicts: List[str] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            data = _parse_fns_json_receipt(entry)
            r = await _create_receipt_with_items(
                purchase_id, data, 'json_import', entry, db
            )
            results.append(r)
        except HTTPException as he:
            # Conflict (409) = receipt linked to another purchase — surface to user.
            if he.status_code == 409:
                conflicts.append(str(he.detail))
            # Other HTTP errors and malformed entries are skipped.
            continue
        except Exception:
            continue
    if not results and conflicts:
        # All entries conflicted — bubble first message up so the user sees it.
        raise HTTPException(409, conflicts[0])
    return results


@router.post("/{purchase_id}/receipts/from-qr", response_model=ReceiptOut)
async def import_receipt_qr(
    purchase_id: int,
    qr: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Create a receipt from a QR-string. No items (admin adds them later)."""
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    data = _parse_qr_string(qr)
    if not data.get('fiscal_drive_number'):
        raise HTTPException(400, "QR не содержит фискальных данных")

    return await _create_receipt_with_items(
        purchase_id, data, 'qr_scan', {'qr': qr}, db,
    )


@router.post("/{purchase_id}/receipts/from-qr-fetch", response_model=ReceiptOut)
async def import_receipt_qr_fetch(
    purchase_id: int,
    qr: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Fetch full receipt (with items) from proverkacheka.com API by QR string.

    Requires PROVERKACHEKA_TOKEN in env. Returns the same shape as JSON-import:
    fiscal data + items auto-matched against the catalog (match_confirmed=False).
    """
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    qr = (qr or '').strip()
    if not qr:
        raise HTTPException(400, "Пустая QR-строка")

    # Phase 24: pre-check duplicate by fiscal triple BEFORE hitting FNS API.
    # ФНС режет повторные обращения по тому же чеку → лучше отдать осмысленную
    # ошибку «уже заведён» чем «Превышено количество обращений».
    qr_data = _parse_qr_string(qr)
    fn = qr_data.get('fiscal_drive_number')
    fd = qr_data.get('fiscal_document_number')
    fp = qr_data.get('fiscal_sign')

    async def _find_existing_by_qr():
        """Найти существующий чек по любым доступным полям из QR.
        Чем больше совпало — тем выше уверенность."""
        # 1) Точная фискальная тройка
        if fn and fd and fp:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.fiscal_document_number == fd,
                    PurchaseReceipt.fiscal_sign == fp,
                )
            )).scalar_one_or_none()
            if row:
                return row
        # 2) Пара fn+fd (старые записи могли сохраниться без fp)
        if fn and fd:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.fiscal_document_number == fd,
                )
            )).scalar_one_or_none()
            if row:
                return row
        # 3) fn + дата + сумма из QR (для очень старых записей без fd/fp)
        dt = qr_data.get('receipt_datetime')
        total = qr_data.get('total_sum')
        if fn and dt and total is not None:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.receipt_datetime == dt,
                    PurchaseReceipt.total_sum == total,
                )
            )).scalar_one_or_none()
            if row:
                return row
        return None

    async def _find_existing_loose():
        """Loose поиск: только fn+fd (без fp), затем dt+inn+sum."""
        parsed = _parse_qr_string(qr) or {}
        fn2 = parsed.get('fiscal_drive_number')
        fd2 = parsed.get('fiscal_document_number')
        if fn2 and fd2:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn2,
                    PurchaseReceipt.fiscal_document_number == fd2,
                ).limit(1)
            )).scalar_one_or_none()
            if row:
                return row
        # Fallback: dt+inn+sum
        dt2 = parsed.get('receipt_datetime')
        inn2 = parsed.get('seller_inn')
        total2 = parsed.get('total_sum')
        if dt2 and inn2 and total2 is not None:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.seller_inn == inn2,
                    PurchaseReceipt.receipt_datetime == dt2,
                    PurchaseReceipt.total_sum == total2,
                ).limit(1)
            )).scalar_one_or_none()
            if row:
                return row
        return None

    async def _raise_receipt_duplicate(existing_row):
        """Поднять structured 409 со ссылкой на закупку, где этот чек уже есть."""
        other = await db.get(Purchase, existing_row.purchase_id)
        ref = (other and (other.registry_number or other.purchase_number)) or f"#{existing_row.purchase_id}"
        same = existing_row.purchase_id == purchase_id
        if same:
            message = "Этот чек уже добавлен в текущую закупку."
        else:
            message = f"Чек был загружен ранее в закупку № {ref}."
        raise HTTPException(409, detail={
            "code": "RECEIPT_DUPLICATE",
            "message": message,
            "purchase_id": existing_row.purchase_id,
            "purchase_ref": ref,
            "receipt_id": existing_row.id,
            "same_purchase": same,
        })

    pre_existing = await _find_existing_by_qr() or await _find_existing_loose()
    if pre_existing:
        await _raise_receipt_duplicate(pre_existing)

    token = os.getenv("PROVERKACHEKA_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "PROVERKACHEKA_TOKEN не настроен на сервере")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://proverkacheka.com/api/v1/check/get",
                data={"qrraw": qr, "token": token},
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Ошибка запроса к proverkacheka.com: {e}")
    except ValueError:
        raise HTTPException(502, "Не удалось распарсить ответ proverkacheka.com")

    if not isinstance(payload, dict) or payload.get("code") != 1:
        msg = (payload or {}).get("data") if isinstance(payload, dict) else None
        msg_str = msg if isinstance(msg, str) else ""
        # Если ФНС режет по rate-limit — это сильный сигнал что чек уже импортировали
        # сегодня. Пробуем ещё раз поискать в БД (loose поиск тоже).
        if "Превышено" in msg_str or "превышен" in msg_str.lower() or "уже" in msg_str.lower():
            again = await _find_existing_by_qr() or await _find_existing_loose()
            if again:
                await _raise_receipt_duplicate(again)
            raise HTTPException(429, detail={
                "code": "FNS_RATE_LIMIT",
                "message": "ФНС временно ограничила запросы. В базе CRM этот чек не найден — попробуйте через 1–2 минуты.",
                "hint": msg_str or None,
            })
        if msg_str:
            raise HTTPException(400, f"Чек не найден: {msg_str}")
        raise HTTPException(400, "Чек не найден в ФНС (proverkacheka.com)")

    body = payload.get("data") or {}
    receipt_obj = body.get("json") if isinstance(body, dict) else None
    if not isinstance(receipt_obj, dict):
        raise HTTPException(502, "Ответ proverkacheka.com без данных чека")

    data = _parse_fns_json_receipt(receipt_obj)
    if not data.get("fiscal_drive_number"):
        # fall back to QR fields if proverkacheka returned partial data
        qr_data = _parse_qr_string(qr)
        for k, v in qr_data.items():
            if v and not data.get(k):
                data[k] = v

    return await _create_receipt_with_items(
        purchase_id, data, 'qr_scan', {"qr": qr, "proverkacheka": payload}, db,
    )


@router.post("/{purchase_id}/receipts", response_model=ReceiptOut)
async def create_receipt_manual(
    purchase_id: int,
    data: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Manual entry of fiscal data + optional items."""
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    payload = data.model_dump(exclude_unset=True)
    src = payload.pop('source', None) or 'manual'
    raw_dump = data.model_dump(mode='json')
    return await _create_receipt_with_items(
        purchase_id, payload, src, raw_dump, db,
    )


@router.delete("/{purchase_id}/receipts/{receipt_id}")
async def delete_receipt(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")

    # U-4: при удалении чека — убрать запись из acceptance_docs (если авансовый)
    purchase = await db.get(Purchase, purchase_id)
    if purchase and purchase.purchase_method == 'advance' and purchase.acceptance_docs:
        from sqlalchemy.orm import attributes as _orm_attrs
        new_docs = [d for d in (purchase.acceptance_docs or []) if d.get("receipt_id") != receipt_id]
        if len(new_docs) != len(purchase.acceptance_docs or []):
            purchase.acceptance_docs = new_docs
            _orm_attrs.flag_modified(purchase, "acceptance_docs")

    await db.delete(r)
    await db.commit()
    return {"status": "ok"}


# ── PDF / PNG render ────────────────────────────────────────────────────────
# Constant maps for ФФД 1.2 codes → human-readable Russian labels.
OPERATION_TYPE_RU = {
    1: "Приход",
    2: "Возврат прихода",
    3: "Расход",
    4: "Возврат расхода",
}
PRODUCT_TYPE_RU = {
    1: "ТОВАР",
    2: "ПОДАКЦИЗНЫЙ ТОВАР",
    3: "РАБОТА",
    4: "УСЛУГА",
    5: "СТАВКА АЗАРТНОЙ ИГРЫ",
    6: "ВЫИГРЫШ АЗАРТНОЙ ИГРЫ",
    7: "ЛОТЕРЕЙНЫЙ БИЛЕТ",
    8: "ВЫИГРЫШ ЛОТЕРЕИ",
    9: "ПРЕДОСТАВЛЕНИЕ РИД",
    10: "ПЛАТЕЖ",
    11: "АГЕНТСКОЕ ВОЗНАГРАЖДЕНИЕ",
    12: "ВЫПЛАТА",
    13: "ИНОЙ ПРЕДМЕТ РАСЧЕТА",
    14: "ИМУЩЕСТВЕННОЕ ПРАВО",
    15: "ВНЕРЕАЛИЗАЦИОННЫЙ ДОХОД",
    16: "СТРАХОВЫЕ ВЗНОСЫ",
    17: "ТОРГОВЫЙ СБОР",
    18: "КУРОРТНЫЙ СБОР",
    19: "ЗАЛОГ",
    20: "РАСХОД",
    21: "ВЗНОСЫ НА ОПС ИП",
    22: "ВЗНОСЫ НА ОПС",
    23: "ВЗНОСЫ НА ОМС ИП",
    24: "ВЗНОСЫ НА ОМС",
    25: "ВЗНОСЫ НА ОСС",
    26: "ПЛАТЕЖ КАЗИНО",
    27: "ВЫДАЧА ДЕНЕЖНЫХ СРЕДСТВ",
    30: "АТНМ",
    31: "АТМ",
    32: "АТНМ",
    33: "АТМ",
}
PAYMENT_TYPE_RU = {
    1: "ПРЕДОПЛАТА 100%",
    2: "ПРЕДОПЛАТА",
    3: "АВАНС",
    4: "ПОЛНЫЙ РАСЧЕТ",
    5: "ЧАСТИЧНЫЙ РАСЧЕТ И КРЕДИТ",
    6: "ПЕРЕДАЧА В КРЕДИТ",
    7: "ОПЛАТА КРЕДИТА",
}
NDS_LABEL_RU = {
    1: "НДС 20%",
    2: "НДС 10%",
    3: "НДС 20/120",
    4: "НДС 10/110",
    5: "НДС 0%",
    6: "НДС не облагается",
    7: "НДС не облагается",
}
TAXATION_RU = {
    1: "ОСН",
    2: "УСН доход",
    4: "УСН доход-расход",
    8: "ЕНВД",
    16: "ЕСХН",
    32: "ПАТЕНТ",
}


def _get_raw_receipt(r) -> dict:
    """Pull the FNS receipt sub-dict regardless of payload shape variant."""
    raw = r.raw_json or {}
    if not isinstance(raw, dict):
        return {}
    if 'ticket' in raw and isinstance(raw['ticket'], dict):
        return raw.get('ticket', {}).get('document', {}).get('receipt', {}) or {}
    if 'receipt' in raw and isinstance(raw['receipt'], dict):
        return raw['receipt']
    return raw


def _build_qr_string(r) -> str:
    """Compose the canonical ФНС QR string `t=...&s=...&fn=...&i=...&fp=...&n=...`."""
    parts = []
    if r.receipt_datetime:
        try:
            parts.append(f"t={r.receipt_datetime.strftime('%Y%m%dT%H%M')}")
        except Exception:
            pass
    if r.total_sum is not None:
        try:
            parts.append(f"s={float(r.total_sum):.2f}")
        except Exception:
            pass
    if r.fiscal_drive_number:
        parts.append(f"fn={r.fiscal_drive_number}")
    if r.fiscal_document_number:
        parts.append(f"i={r.fiscal_document_number}")
    if r.fiscal_sign:
        parts.append(f"fp={r.fiscal_sign}")
    raw = _get_raw_receipt(r)
    op = raw.get('operationType') or 1
    parts.append(f"n={op}")
    return '&'.join(parts)


def _make_qr_image_buf(data: str) -> BytesIO:
    """Build a QR-code PNG into an in-memory buffer (for ReportLab drawImage)."""
    import qrcode
    img = qrcode.make(data, box_size=4, border=2)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


@router.get("/{purchase_id}/receipts/{receipt_id}/pdf")
async def receipt_pdf(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF on-the-fly from receipt raw_json. No auth — fiscal receipts
    are not sensitive (already public on ФНС side via the QR code). Stable URL
    allows embedding as hyperlinks in Excel exports."""
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")
    try:
        pdf_bytes = _render_receipt_pdf(r)
    except Exception:
        pdf_bytes = _render_fallback_pdf(r)
    filename = f"Cheque_{r.fiscal_drive_number or 'unknown'}_{r.fiscal_document_number or r.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/{purchase_id}/receipts/{receipt_id}/png")
async def receipt_png(
    purchase_id: int,
    receipt_id: int,
    db: AsyncSession = Depends(get_db),
):
    """PNG render of a receipt — for inline <img> embedding."""
    r = await db.get(PurchaseReceipt, receipt_id)
    if not r or r.purchase_id != purchase_id:
        raise HTTPException(404, "Чек не найден")
    png_bytes = _render_receipt_png(r)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _register_cyrillic_font() -> str:
    """Register a Cyrillic-capable TTF font. Returns the registered font name
    (or "Helvetica" as a fallback). Idempotent — safe to call multiple times."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # If we've already registered DejaVu in a previous call, reuse it.
    try:
        if "DejaVu" in pdfmetrics.getRegisteredFontNames():
            return "DejaVu"
    except Exception:
        pass

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", path))
            bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
            else:
                # No bold available — register the regular face under the bold name
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", path))
            return "DejaVu"
        except Exception:
            continue
    return "Helvetica"


def _extract_items_from_proverkacheka_html(html: str) -> list:
    """Phase 26-EE/MM: парсер HTML-таблицы товаров от proverkacheka.com.
    Парсит и НДС-строки (b-check_vblock-last с 'НДС со ставкой X%').
    """
    if not html or not isinstance(html, str):
        return []
    import re as _re

    def _clean(s):
        s = _re.sub(r'<[^>]+>', '', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        return s.strip()

    out = []
    current_item = None
    # Все строки с классом b-check_item (товары + НДС)
    all_rows = _re.findall(
        r'<tr[^>]*class="([^"]*b-check_item[^"]*)"[^>]*>(.*?)</tr>',
        html,
        flags=_re.DOTALL,
    )
    for class_attr, row in all_rows:
        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, flags=_re.DOTALL)
        cleaned = [_clean(c) for c in cells]
        is_first = 'b-check_vblock-first' in class_attr
        is_last = 'b-check_vblock-last' in class_attr
        if is_first and len(cleaned) >= 5:
            # Новая позиция: cells [№, name, price, qty, sum]
            try:
                name = cleaned[1]
                price = float(cleaned[2].replace(',', '.').replace(' ', '') or 0)
                qty = float(cleaned[3].replace(',', '.').replace(' ', '') or 1)
                sm = float(cleaned[4].replace(',', '.').replace(' ', '') or 0)
                if not name:
                    current_item = None
                    continue
                current_item = {
                    'name': name,
                    'quantity': qty,
                    'qty': qty,
                    'price': price,
                    'sum': sm,
                    'vat_rate': None,
                }
                out.append(current_item)
            except Exception:
                current_item = None
                continue
        elif is_last and current_item is not None:
            # НДС-строка позиции: ищем "НДС со ставкой X%"
            for c in cleaned:
                m = _re.search(r'НДС\s*со\s*ставкой\s*(\d+(?:[.,]\d+)?)\s*%', c)
                if m:
                    rate = m.group(1).replace(',', '.')
                    current_item['vat_rate'] = f"{rate}%"
                    break
            current_item = None  # next first opens new item
    return out


def _extract_items(raw) -> list:
    """Pull items out of the raw_json regardless of FNS shape variant."""
    if not isinstance(raw, dict):
        return []
    items_src = None
    ticket = raw.get('ticket')
    if isinstance(ticket, dict):
        doc = ticket.get('document')
        if isinstance(doc, dict):
            rcpt = doc.get('receipt')
            if isinstance(rcpt, dict):
                items_src = rcpt.get('items')
    if items_src is None:
        rcpt = raw.get('receipt')
        if isinstance(rcpt, dict):
            items_src = rcpt.get('items')
    if items_src is None:
        items_src = raw.get('items')
    if isinstance(items_src, list) and items_src:
        out = []
        for it in items_src:
            if not isinstance(it, dict):
                continue
            try:
                qty = float(it.get('quantity') or 1)
            except Exception:
                qty = 1.0
            try:
                price = float(it.get('price') or 0) / 100.0
            except Exception:
                price = 0.0
            try:
                sm = float(it.get('sum') or 0) / 100.0
            except Exception:
                sm = 0.0
            out.append({
                'name': str(it.get('name') or '').strip(),
                'quantity': qty,
                'qty': qty,
                'price': price,
                'sum': sm,
            })
        if out:
            return out
    # Phase 26-EE fallback: proverkacheka.com HTML
    pv = raw.get('proverkacheka')
    if isinstance(pv, dict):
        data = pv.get('data')
        if isinstance(data, dict):
            html = data.get('html')
            if html:
                return _extract_items_from_proverkacheka_html(html)
    return []


def _render_fallback_pdf(r) -> bytes:
    """Minimal PDF when raw_json is missing or rendering threw."""
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    c.setFont(font_name, 10)
    w, h = A6
    c.drawString(8 * mm, h - 12 * mm, f"Чек #{r.id} — данные недоступны")
    if r.fiscal_drive_number:
        c.drawString(8 * mm, h - 20 * mm, f"ФН: {r.fiscal_drive_number}")
    if r.fiscal_document_number:
        c.drawString(8 * mm, h - 26 * mm, f"ФД: {r.fiscal_document_number}")
    c.showPage()
    c.save()
    return buf.getvalue()


def _render_receipt_pdf(r) -> bytes:
    """Render a fiscal receipt in ФФД 1.2 layout (matches ФНС 'Проверка чека' app).

    A5 portrait, dynamic height. Sections (top→bottom):
      • Header (КАССОВЫЙ ЧЕК / версия ФФД 1.2 / operation type)
      • Items table — for each item: row + НДС label + НДС sum + product type + payment type
      • Totals (ИТОГО, Безналичные/Наличные/Аванс/…, НДС итог)
      • Fiscal block (СНО, РЕГ.НОМЕР ККТ, ФН, ФД, ФПД)
      • Seller block (Пользователь, Адрес, Место, ИНН, Дата, Чек №, Смена №, Кассир)
      • QR code centered
    """
    import textwrap
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    font_name = _register_cyrillic_font()
    bold_name = "DejaVu-Bold" if font_name == "DejaVu" else "Helvetica-Bold"

    raw = _get_raw_receipt(r)
    # Phase 26-EE: fallback на _extract_items для proverkacheka HTML
    items_data = list(raw.get('items') or []) or _extract_items(r.raw_json or {})

    # Dynamic height — A5 width (148mm) is enough; height grows with content.
    width = 148 * mm
    base_h = 180 * mm
    items_h = (25 * mm) * max(1, len(items_data))
    tail_h = 60 * mm
    height = base_h + items_h + tail_h

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    # Drawing state ----------------------------------------------------------
    state = {"y": height - 8 * mm}
    margin_l = 6 * mm
    margin_r = width - 6 * mm
    inner_w = margin_r - margin_l

    def set_font(size=9, bold=False, italic=False):
        # ReportLab DejaVu doesn't have an italic variant registered — use regular.
        c.setFont(bold_name if bold else font_name, size)

    def line(s, size=9, bold=False, x=None, dy=4.5):
        set_font(size, bold)
        c.drawString(x if x is not None else margin_l, state["y"], str(s))
        state["y"] -= dy * mm

    def line_center(s, size=9, bold=False, italic=False, dy=4.5):
        set_font(size, bold, italic)
        text_w = c.stringWidth(str(s), bold_name if bold else font_name, size)
        c.drawString((width - text_w) / 2, state["y"], str(s))
        state["y"] -= dy * mm

    def line_right(label, value, size=9, bold=False, dy=4.5):
        set_font(size, bold)
        c.drawString(margin_l, state["y"], str(label))
        text_w = c.stringWidth(str(value), bold_name if bold else font_name, size)
        c.drawString(margin_r - text_w, state["y"], str(value))
        state["y"] -= dy * mm

    def hr_dashed():
        c.setDash(2, 2)
        c.setLineWidth(0.4)
        c.line(margin_l, state["y"], margin_r, state["y"])
        c.setDash()
        state["y"] -= 3 * mm

    # ── Header ─────────────────────────────────────────────────────────────
    line_center("КАССОВЫЙ ЧЕК", 14, bold=True, dy=5.5)
    line_center("«версия ФФД 1.2»", 9, dy=5)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    line_center(op_word, 11, bold=True, dy=6)

    hr_dashed()

    # ── Items table ────────────────────────────────────────────────────────
    # Header row
    set_font(8, bold=True)
    c.drawString(margin_l, state["y"], "№")
    c.drawString(margin_l + 6 * mm, state["y"], "Название")
    c.drawString(margin_l + 80 * mm, state["y"], "Цена")
    c.drawString(margin_l + 100 * mm, state["y"], "Кол.")
    c.drawString(margin_l + 118 * mm, state["y"], "Сумма")
    state["y"] -= 5 * mm

    if not items_data:
        line("(позиции не указаны)", 8, dy=5)

    for idx, it in enumerate(items_data, start=1):
        if not isinstance(it, dict):
            continue
        try:
            qty = float(it.get('quantity') or 1)
        except Exception:
            qty = 1.0
        try:
            price = float(it.get('price') or 0) / 100.0
        except Exception:
            price = 0.0
        try:
            sm = float(it.get('sum') or 0) / 100.0
        except Exception:
            sm = 0.0
        nds_code = it.get('nds')
        nds_sum_kop = it.get('ndsSum')
        try:
            nds_sum_rub = float(nds_sum_kop) / 100.0 if nds_sum_kop is not None else None
        except Exception:
            nds_sum_rub = None
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()

        # Wrap long names — the name column is ~70mm wide.
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1 — number + first name line + price/qty/sum
        set_font(8)
        c.drawString(margin_l, state["y"], str(idx))
        c.drawString(margin_l + 6 * mm, state["y"], wrapped[0][:42])
        c.drawString(margin_l + 80 * mm, state["y"], f"{price:.2f}")
        c.drawString(margin_l + 100 * mm, state["y"], f"{qty:g}")
        c.drawString(margin_l + 118 * mm, state["y"], f"{sm:.2f}")
        state["y"] -= 4.5 * mm

        # Continuation lines of the name (if wrapped)
        for cont in wrapped[1:]:
            set_font(8)
            c.drawString(margin_l + 6 * mm, state["y"], cont[:42])
            state["y"] -= 4 * mm

        # НДС label
        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        line(f"   {nds_label}", 7, dy=3.8)

        # НДС sum (if non-zero)
        if nds_sum_rub is not None and nds_sum_rub > 0:
            line_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", 7, dy=3.8)

        # Product type
        if product_type:
            line(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", 7, dy=3.8)

        # Payment type
        if payment_type:
            line(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", 7, dy=3.8)

        state["y"] -= 1 * mm

    hr_dashed()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        line_right("ИТОГО:", f"{float(r.total_sum):.2f}", 12, bold=True, dy=6)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        line_right("Безналичные", f"{float(r.ecash_sum):.2f}", 9, dy=4.5)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        line_right("Наличные", f"{float(r.cash_sum):.2f}", 9, dy=4.5)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        line_right("Аванс", f"{float(r.prepaid_sum):.2f}", 9, dy=4.5)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            line_right("НДС", f"{nds_total:.2f}", 9, dy=4.5)
        else:
            line_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", 9, dy=4.5)

    hr_dashed()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        line(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", 8, dy=4.5)
    if r.kkt_reg_id:
        line(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", 8, dy=4.5)
    if r.fiscal_drive_number:
        line(f"ФН: № {r.fiscal_drive_number}", 8, dy=4.5)
    if r.fiscal_document_number:
        line(f"ФД: № {r.fiscal_document_number}", 8, dy=4.5)
    if r.fiscal_sign:
        line(f"ФПД: # {r.fiscal_sign}", 8, dy=4.5)

    hr_dashed()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        line(f"Пользователь: {r.seller_name}", 8, dy=4.5)
    if r.retail_place_address:
        line(f"Адрес расчета: {str(r.retail_place_address)[:90]}", 8, dy=4.5)
    if r.retail_place:
        line(f"Место расчета: {str(r.retail_place)[:90]}", 8, dy=4.5)
    if r.seller_inn:
        line(f"ИНН {r.seller_inn}", 8, dy=4.5)
    if r.receipt_datetime:
        try:
            line(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", 8, dy=4.5)
        except Exception:
            line(f"Дата: {r.receipt_datetime}", 8, dy=4.5)
    request_number = raw.get('requestNumber')
    if request_number:
        line(f"Чек № {request_number}", 8, dy=4.5)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        line(f"Смена № {shift_number}", 8, dy=4.5)
    if r.operator:
        line(f"Кассир {r.operator}", 8, dy=4.5)
    if r.operator_inn:
        line(f"ИНН кассира: {r.operator_inn}", 8, dy=4.5)

    state["y"] -= 4 * mm

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_buf = _make_qr_image_buf(qr_str)
        qr_size = 40 * mm
        qr_x = (width - qr_size) / 2
        qr_y = max(state["y"] - qr_size, 8 * mm)
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
    except Exception:
        pass

    c.showPage()
    c.save()
    return buf.getvalue()


def _render_receipt_png(r) -> bytes:
    """Render a fiscal receipt as PNG (Pillow). Same layout as PDF.

    Returns raw PNG bytes ready to send back as image/png.
    """
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    import qrcode

    raw = _get_raw_receipt(r)
    items_data = [it for it in (raw.get('items') or []) if isinstance(it, dict)]
    # Phase 26-EE: fallback на _extract_items для proverkacheka HTML
    if not items_data:
        items_data = _extract_items(r.raw_json or {})

    width = 600

    # ── Font loading ───────────────────────────────────────────────────────
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    bold_paths = [p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") for p in font_paths]
    font_path = next((p for p in font_paths if os.path.exists(p)), None)
    bold_path = next((p for p in bold_paths if os.path.exists(p)), font_path)

    def f(size, bold=False):
        try:
            return ImageFont.truetype(bold_path if bold else font_path, size) \
                if (bold_path if bold else font_path) else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    F_TITLE = f(20, bold=True)
    F_SUB = f(13)
    F_OP = f(16, bold=True)
    F_TBL_HEAD = f(12, bold=True)
    F_TXT = f(12)
    F_SMALL = f(11)
    F_TOTAL = f(20, bold=True)
    F_TOTAL_NUM = f(20, bold=True)
    F_LINE = f(13)

    line_h = 18

    # ── Pre-compute height ─────────────────────────────────────────────────
    title_h = 28 + 22 + 28 + 12  # title + sub + op + spacing
    items_h = 28  # table header
    for it in items_data:
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']
        items_h += line_h * len(wrapped)  # name lines
        items_h += line_h  # nds label
        if it.get('ndsSum'):
            items_h += line_h
        if it.get('productType'):
            items_h += line_h
        if it.get('paymentType'):
            items_h += line_h
        items_h += 6
    if not items_data:
        items_h += line_h

    totals_h = 60 + line_h * 5
    fiscal_h = line_h * 6
    seller_h = line_h * 10
    qr_h = 220
    height = title_h + items_h + totals_h + fiscal_h + seller_h + qr_h + 60

    img = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(img)

    margin_l = 20
    margin_r = width - 20

    state = {"y": 16}

    def hr():
        # Dashed
        x = margin_l
        while x < margin_r:
            d.line([(x, state["y"]), (min(x + 4, margin_r), state["y"])], fill='black', width=1)
            x += 8
        state["y"] += 10

    def text(s, font=F_TXT, x=None, dy=None, fill='black'):
        d.text((x if x is not None else margin_l, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_center(s, font=F_TXT, dy=None, fill='black'):
        try:
            tw = d.textlength(str(s), font=font)
        except Exception:
            tw = len(str(s)) * 7
        d.text(((width - tw) / 2, state["y"]), str(s), font=font, fill=fill)
        state["y"] += dy if dy is not None else line_h

    def text_right(label, value, font=F_TXT, value_font=None, dy=None, fill='black'):
        vfont = value_font or font
        d.text((margin_l, state["y"]), str(label), font=font, fill=fill)
        try:
            vw = d.textlength(str(value), font=vfont)
        except Exception:
            vw = len(str(value)) * 7
        d.text((margin_r - vw, state["y"]), str(value), font=vfont, fill=fill)
        state["y"] += dy if dy is not None else line_h

    # ── Header ─────────────────────────────────────────────────────────────
    text_center("КАССОВЫЙ ЧЕК", F_TITLE, dy=28)
    text_center("«версия ФФД 1.2»", F_SUB, dy=22)
    op_code = raw.get('operationType') or 1
    op_word = OPERATION_TYPE_RU.get(op_code, "Приход")
    text_center(op_word, F_OP, dy=28)
    state["y"] += 4
    hr()

    # ── Items table ────────────────────────────────────────────────────────
    # Column header
    d.text((margin_l, state["y"]), "№", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 30, state["y"]), "Название", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 340, state["y"]), "Цена", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 420, state["y"]), "Кол.", font=F_TBL_HEAD, fill='black')
    d.text((margin_l + 480, state["y"]), "Сумма", font=F_TBL_HEAD, fill='black')
    state["y"] += line_h + 4

    if not items_data:
        text("(позиции не указаны)", F_SMALL)

    for idx, it in enumerate(items_data, start=1):
        try:
            qty = float(it.get('quantity') or 1)
        except Exception:
            qty = 1.0
        try:
            price = float(it.get('price') or 0) / 100.0
        except Exception:
            price = 0.0
        try:
            sm = float(it.get('sum') or 0) / 100.0
        except Exception:
            sm = 0.0
        nds_code = it.get('nds')
        nds_sum_kop = it.get('ndsSum')
        try:
            nds_sum_rub = float(nds_sum_kop) / 100.0 if nds_sum_kop is not None else None
        except Exception:
            nds_sum_rub = None
        product_type = it.get('productType')
        payment_type = it.get('paymentType')
        name = (it.get('name') or '').strip()
        wrapped = textwrap.wrap(name, width=42) or ['']

        # Row 1
        d.text((margin_l, state["y"]), str(idx), font=F_TXT, fill='black')
        d.text((margin_l + 30, state["y"]), wrapped[0][:42], font=F_TXT, fill='black')
        d.text((margin_l + 340, state["y"]), f"{price:.2f}", font=F_TXT, fill='black')
        d.text((margin_l + 420, state["y"]), f"{qty:g}", font=F_TXT, fill='black')
        d.text((margin_l + 480, state["y"]), f"{sm:.2f}", font=F_TXT, fill='black')
        state["y"] += line_h

        # Wrapped name continuation
        for cont in wrapped[1:]:
            d.text((margin_l + 30, state["y"]), cont[:42], font=F_TXT, fill='black')
            state["y"] += line_h

        nds_label = NDS_LABEL_RU.get(nds_code, "НДС не облагается")
        text(f"   {nds_label}", F_SMALL)

        if nds_sum_rub is not None and nds_sum_rub > 0:
            text_right("   сумма НДС за товар", f"{nds_sum_rub:.2f}", F_SMALL)

        if product_type:
            text(f"   {PRODUCT_TYPE_RU.get(product_type, '')}", F_SMALL)

        if payment_type:
            text(f"   {PAYMENT_TYPE_RU.get(payment_type, '')}", F_SMALL)

        state["y"] += 4

    hr()

    # ── Totals ─────────────────────────────────────────────────────────────
    if r.total_sum is not None:
        text_right("ИТОГО:", f"{float(r.total_sum):.2f}", F_TOTAL, F_TOTAL_NUM, dy=30)
    if r.ecash_sum is not None and float(r.ecash_sum) > 0:
        text_right("Безналичные", f"{float(r.ecash_sum):.2f}", F_LINE)
    if r.cash_sum is not None and float(r.cash_sum) > 0:
        text_right("Наличные", f"{float(r.cash_sum):.2f}", F_LINE)
    if r.prepaid_sum is not None and float(r.prepaid_sum) > 0:
        text_right("Аванс", f"{float(r.prepaid_sum):.2f}", F_LINE)
    if r.nds_sum is not None:
        try:
            nds_total = float(r.nds_sum)
        except Exception:
            nds_total = None
        if nds_total and nds_total > 0:
            text_right("НДС", f"{nds_total:.2f}", F_LINE)
        else:
            text_right("НДС не облагается", f"{float(r.total_sum or 0):.2f}", F_LINE)

    hr()

    # ── Fiscal block ───────────────────────────────────────────────────────
    if r.taxation_type is not None:
        sno = TAXATION_RU.get(r.taxation_type, str(r.taxation_type))
        text(f"ВИД НАЛОГООБЛОЖЕНИЯ {sno}", F_LINE)
    if r.kkt_reg_id:
        text(f"РЕГ. НОМЕР ККТ: {r.kkt_reg_id}", F_LINE)
    if r.fiscal_drive_number:
        text(f"ФН: № {r.fiscal_drive_number}", F_LINE)
    if r.fiscal_document_number:
        text(f"ФД: № {r.fiscal_document_number}", F_LINE)
    if r.fiscal_sign:
        text(f"ФПД: # {r.fiscal_sign}", F_LINE)

    hr()

    # ── Seller block ───────────────────────────────────────────────────────
    if r.seller_name:
        text(f"Пользователь: {r.seller_name}", F_LINE)
    if r.retail_place_address:
        text(f"Адрес расчета: {str(r.retail_place_address)[:90]}", F_LINE)
    if r.retail_place:
        text(f"Место расчета: {str(r.retail_place)[:90]}", F_LINE)
    if r.seller_inn:
        text(f"ИНН {r.seller_inn}", F_LINE)
    if r.receipt_datetime:
        try:
            text(f"Дата: {r.receipt_datetime.strftime('%d.%m.%Y %H.%M')}", F_LINE)
        except Exception:
            text(f"Дата: {r.receipt_datetime}", F_LINE)
    request_number = raw.get('requestNumber')
    if request_number:
        text(f"Чек № {request_number}", F_LINE)
    shift_number = raw.get('shiftNumber')
    if shift_number:
        text(f"Смена № {shift_number}", F_LINE)
    if r.operator:
        text(f"Кассир {r.operator}", F_LINE)
    if r.operator_inn:
        text(f"ИНН кассира: {r.operator_inn}", F_LINE)

    state["y"] += 12

    # ── QR code ────────────────────────────────────────────────────────────
    try:
        qr_str = _build_qr_string(r)
        qr_img = qrcode.make(qr_str, box_size=5, border=2).get_image().convert('RGB')
        qr_size = 200
        qr_resized = qr_img.resize((qr_size, qr_size))
        img.paste(qr_resized, ((width - qr_size) // 2, state["y"]))
    except Exception:
        pass

    out = BytesIO()
    img.save(out, format='PNG', optimize=True)
    return out.getvalue()
