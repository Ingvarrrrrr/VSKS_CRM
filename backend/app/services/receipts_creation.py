"""Receipt creation core: insert PurchaseReceipt + auto-create PurchaseItem rows.

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).
DB logic shared by every receipt-creation entry point (JSON import, QR scan,
QR fetch via proverkacheka.com, manual entry) — kept together because the
advance-purchase auto-contract/auto-ContractItem logic here is interleaved
with the shared duplicate-detection and item-matching code, not a separable
concern (ПРАВИЛО №6: not splitting further avoids a second half-copy of this
flow).

Historical import path app.routers.purchase_receipts re-exports
_create_receipt_with_items, _create_or_enrich_contractor_from_receipt
(also used directly by contractors.py and purchase_items_import.py).
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_receipt import PurchaseReceipt
from app.product_matcher import find_matching_product
from app.services import acceptance_docs as _acc_docs
from app.services.item_amounts import line_total
from app.services.item_contractor import set_item_contractor
from app.services.receipts_parsing import _items_match_score
from app.services.receipts_render import _render_receipt_png


async def _raise_receipt_duplicate_detail(
    other_purchase_id: int,
    current_purchase_id: int,
    receipt_id,
    db: AsyncSession,
):
    """Поднять structured 409: чек уже есть в другом документе.

    Формулировка зависит от того, авансовый ли это отчёт (Purchase.purchase_method
    == 'advance') — раньше сообщение всегда говорило «закупка», из-за чего
    пользователь пытался найти авансовый отчёт в реестре закупок. Признак
    is_advance отдаётся в detail, чтобы фронт не угадывал вид документа по тексту.
    """
    other = await db.get(Purchase, other_purchase_id)
    ref = (other and (other.registry_number or other.purchase_number)) or f"#{other_purchase_id}"
    is_advance = bool(other and other.purchase_method == 'advance')
    same = other_purchase_id == current_purchase_id
    if same:
        message = (
            "Этот чек уже добавлен в текущий авансовый отчёт." if is_advance
            else "Этот чек уже добавлен в текущую закупку."
        )
    elif is_advance:
        message = f"Такой авансовый отчёт уже есть — № {ref}. Этот чек уже был загружен в него."
    else:
        message = f"Чек был загружен ранее в закупку № {ref}."
    raise HTTPException(409, detail={
        "code": "RECEIPT_DUPLICATE",
        "message": message,
        "purchase_id": other_purchase_id,
        "purchase_ref": ref,
        "receipt_id": receipt_id,
        "same_purchase": same,
        "is_advance": is_advance,
    })


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
            await _raise_receipt_duplicate_detail(existing.purchase_id, purchase_id, existing.id, db)

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
            await _raise_receipt_duplicate_detail(dup.purchase_id, purchase_id, dup.id, db)

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
            # Phase 26-CCC: auto-enrich через ЕГРЮЛ (короткое name + full_name + ...)
            new_c = await _create_or_enrich_contractor_from_receipt(seller_inn, seller_name, db)
            db.add(new_c)
            await db.flush()
            contractor_id_for_items = new_c.id

    # Phase 27.1.4: auto-create Contract row для авансовой закупки
    # чтобы /api/contracts отображал contractor_name без NULL (красная плашка).
    # Только если у закупки нет contract_id, но есть contractor.
    if contractor_id_for_items:
        purchase_for_contract = await db.get(Purchase, purchase_id)
        if purchase_for_contract and not purchase_for_contract.contract_id:
            from app.models.contract import Contract as _Contract
            expected_number = (
                str(purchase_for_contract.purchase_number)
                if purchase_for_contract.purchase_number
                else f"AVANS-{purchase_id}"
            )
            existing_contract_q = await db.execute(
                select(_Contract).where(
                    _Contract.number == expected_number,
                    _Contract.contractor_id == contractor_id_for_items,
                ).limit(1)
            )
            if not existing_contract_q.scalar_one_or_none():
                # ПРАВИЛО №6 (волна 4b-2d): тот же паттерн, что и
                # app.routers.contracts._enrich_contract_from_purchases —
                # contract_amount() (цена договора ?? Σ ContractItem.total ПО
                # ЭТОЙ закупке) с фолбэком на purchase_amounts().plan, а не
                # truthy-цепочка `total_nmck or contract_price or planned_total_price`
                # (0 в любом из полей молча проваливался дальше по цепочке).
                from app.models.contract_item import ContractItem as _CIAvans
                from app.services.purchase_amounts import contract_amount as _contract_amount_avans, purchase_amounts as _purchase_amounts_avans
                _ci_total_avans = (await db.execute(
                    select(func.sum(_CIAvans.total)).where(_CIAvans.purchase_id == purchase_for_contract.id)
                )).scalar_one_or_none()
                _avans_contract_max_amount = _contract_amount_avans(purchase_for_contract, contract_items_total=_ci_total_avans)
                if _avans_contract_max_amount is None:
                    _avans_contract_max_amount = _purchase_amounts_avans(purchase_for_contract).plan
                new_contract = _Contract(
                    contractor_id=contractor_id_for_items,
                    subsidy_id=purchase_for_contract.subsidy_id,
                    contract_type='single',
                    number=expected_number,
                    date=purchase_for_contract.contract_date,
                    status='active',
                    # Phase 27.1.5: заполнить ВСЕ доступные поля из Purchase
                    subject=purchase_for_contract.subject or str(purchase_for_contract.purchase_number or ''),
                    max_amount=_avans_contract_max_amount,
                    start_date=purchase_for_contract.contract_date,
                    end_date=purchase_for_contract.execution_term,
                    purchase_method=purchase_for_contract.purchase_method if purchase_for_contract.purchase_method in ('single', 'competitive') else 'single',
                    item_type=purchase_for_contract.item_type or 'товар',
                )
                db.add(new_contract)
                await db.flush()
                purchase_for_contract.contract_id = new_contract.id

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
                total = line_total(qty, price)
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
            # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
            set_item_contractor(matched_existing, contractor_id=contractor_id_for_items, inn=seller_inn, name=seller_name)
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
        _new_receipt_item = PurchaseItem(
            purchase_id=purchase_id,
            product_id=matched_id,
            item_name=raw_name,
            quantity=qty,
            unit='шт.',
            unit_price=price,
            total_price=total,
            match_confirmed=False,
            receipt_id=receipt.id,  # Phase 26-BB
            vat_rate=it.get('vat_rate'),
        )
        # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
        set_item_contractor(_new_receipt_item, contractor_id=contractor_id_for_items, inn=seller_inn, name=seller_name)
        db.add(_new_receipt_item)

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
                    extra_attrs=getattr(pi, 'extra_attrs', None) or {},
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

        # U-4: auto-add чек в acceptance_docs (только для авансовых)
        # Phase 26-ooo: усиленный дедуп — раньше дедуп был только по receipt_id,
        # но в acceptance_docs могли быть legacy/manual записи того же чека без
        # receipt_id (после ручного импорта/migration), и они дублировались.
        # Теперь дедуп также по (type='Чек' + number=fiscal_document_number + amount).
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

        def _is_same_receipt_doc(d, rcpt_id, fd_num, amt):
            if d.get("receipt_id") == rcpt_id:
                return True
            # Phase 27.1.12: учесть legacy format где type отсутствует но name="Чек"
            is_check_doc = (
                d.get("type") == "Чек"
                or (d.get("type") is None and d.get("name") == "Чек")
            )
            # Fallback: совпадение по (type/name)="Чек"+number+amount (legacy без receipt_id)
            if (
                is_check_doc
                and str(d.get("number") or "") == str(fd_num or "")
                and fd_num
            ):
                try:
                    return abs(float(d.get("amount") or 0) - float(amt or 0)) < 0.01
                except (TypeError, ValueError):
                    return True  # number совпал — считаем дубликатом
            return False

        rcpt_id = receipt.id
        fd_num = receipt.fiscal_document_number
        amt = float(receipt.total_sum) if receipt.total_sum is not None else 0

        if not any(_is_same_receipt_doc(d, rcpt_id, fd_num, amt) for d in existing_docs):
            # ПРАВИЛО №6: единственный писатель acceptance_docs —
            # app.services.acceptance_docs (add_doc делает append + dedup + flag_modified).
            _acc_docs.add_doc(p, new_doc)
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
                _acc_docs.replace_docs(p, updated_docs)

        if changed:
            await db.commit()

    return receipt


# ── core helper (Phase 26-Z-bootstrap) ───────────────────────────────────────

async def _create_or_enrich_contractor_from_receipt(seller_inn: str, seller_name: str, db: AsyncSession):
    """Phase 26-CCC: создаёт новый Contractor из данных чека.

    Сначала пытается обогатить через ЕГРЮЛ (короткое name из поля c +
    full_name из поля n + ОГРН/КПП/адрес/форма/подписант).
    При ошибке/timeout — fallback на seller_name из чека.

    Возвращает Contractor (НЕ flushed — вызывающий делает db.add + flush).
    Никогда не raise: ЕГРЮЛ-вызов завёрнут в try/except.
    """
    from app.models.contractor import Contractor as _Ctr
    import logging as _lg_egrul
    _log = _lg_egrul.getLogger(__name__)

    egrul_data = None
    try:
        import httpx as _httpx_egrul
        import asyncio as _asyncio_egrul
        async with _httpx_egrul.AsyncClient(timeout=8, verify=False) as client:
            resp1 = await client.post(
                "https://egrul.nalog.ru/",
                json={"query": seller_inn, "region": "", "page": ""},
            )
            token = resp1.json().get("t")
            if token:
                for _ in range(3):
                    await _asyncio_egrul.sleep(0.8)
                    resp2 = await client.get(f"https://egrul.nalog.ru/search-result/{token}")
                    rows = resp2.json().get("rows", [])
                    if rows:
                        row = rows[0]
                        egrul_data = {
                            "name": row.get("c") or row.get("n"),
                            "full_name": row.get("n"),
                            "ogrn": row.get("o"),
                            "kpp": row.get("p"),
                            "address": row.get("a"),
                            "org_type": (
                                "ИП" if len(seller_inn) == 12
                                else ("Юр.лицо" if row.get("o") else None)
                            ),
                            "signatory": row.get("g"),
                        }
                        break
    except Exception as e:
        _log.warning(
            f"ЕГРЮЛ lookup для ИНН {seller_inn} не удался ({e}); "
            f"fallback на seller_name из чека"
        )

    if egrul_data and egrul_data.get("name"):
        return _Ctr(
            inn=seller_inn,
            name=egrul_data["name"],
            full_name=egrul_data.get("full_name"),
            ogrn=egrul_data.get("ogrn"),
            kpp=egrul_data.get("kpp"),
            address=egrul_data.get("address"),
            org_type=egrul_data.get("org_type"),
            signatory=egrul_data.get("signatory"),
        )
    return _Ctr(inn=seller_inn, name=seller_name or f"ИНН {seller_inn}")
