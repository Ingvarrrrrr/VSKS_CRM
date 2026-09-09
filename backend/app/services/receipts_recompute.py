"""Recompute PurchaseItem/ContractItem/acceptance_docs state from a purchase's
receipts, plus the exact-duplicate cleanup it depends on.

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).

Historical import path app.routers.purchase_receipts re-exports
_recompute_from_receipts_core (used by purchases.py and diag.py).
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_receipt import PurchaseReceipt
from app.services import acceptance_docs as _acc_docs
from app.services.item_contractor import set_item_contractor
from app.services.item_amounts import line_total
from app.services.receipts_creation import _create_or_enrich_contractor_from_receipt
from app.services.receipts_parsing import _extract_items, _items_match_score, _nds_code_to_rate_str
from app.services.receipts_render import _render_receipt_png


async def _compute_purchase_snapshot_hash(purchase_id: int, db: AsyncSession) -> str:
    """Phase 26-YY: SHA-1 от состояния items+receipts закупки.

    Используется как cheap-gate перед запуском fuzzy/autocreate/dedup в
    _recompute_from_receipts_core. Если hash не изменился — пропускаем O(N×M×K).
    """
    import hashlib
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase_receipt import PurchaseReceipt as _PR
    items_q = await db.execute(
        select(_PI.id, _PI.item_name, _PI.total_price, _PI.receipt_id, _PI.contractor_id, _PI.match_confirmed)
        .where(_PI.purchase_id == purchase_id)
        .order_by(_PI.id.asc())
    )
    items_parts = [
        f"i:{r[0]}:{r[1] or ''}:{r[2] or 0}:{r[3] or 0}:{r[4] or 0}:{int(bool(r[5]))}"
        for r in items_q.all()
    ]
    receipts_q = await db.execute(
        select(_PR.id, _PR.fiscal_document_number, _PR.total_sum, _PR.seller_inn)
        .where(_PR.purchase_id == purchase_id)
        .order_by(_PR.id.asc())
    )
    receipts_parts = [
        f"r:{r[0]}:{r[1] or ''}:{r[2] or 0}:{r[3] or ''}"
        for r in receipts_q.all()
    ]
    payload = "|".join(items_parts + receipts_parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


async def _recompute_from_receipts_core(purchase_id: int, db: AsyncSession, force: bool = False) -> dict:
    """Idempotent recompute. Returns stats dict. Не кидает HTTPException.

    force=True — байпасит snapshot-hash gate (нужно когда меняется внешняя
    логика парсинга, например НДС-маппинг в phase26-aaa-2, и старые позиции
    нужно перезаполнить из raw_json несмотря на неизменный hash items)."""
    p = await db.get(Purchase, purchase_id)
    if not p:
        return {"ok": False, "reason": "not_found", "items_updated": 0, "files_attached": 0, "acceptance_docs_added": 0}

    # Phase 26-YY: snapshot-hash gate — skip если состояние items+receipts не
    # изменилось с прошлого прогона. Это резко удешевляет повторный GET карточки
    # (без новых чеков/правок) — O(1) SELECT'ов вместо O(N×M×K) fuzzy.
    # При force=True пропускаем проверку (см. docstring выше).
    try:
        current_hash = await _compute_purchase_snapshot_hash(purchase_id, db)
        if not force and p.recompute_snapshot_hash and p.recompute_snapshot_hash == current_hash:
            return {
                "ok": True,
                "skipped": True,
                "reason": "snapshot_unchanged",
                "items_updated": 0,
                "items_autocreated": 0,
                "items_deduplicated": 0,
                "files_attached": 0,
                "acceptance_docs_added": 0,
            }
    except Exception as _hash_e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"snapshot hash compute failed: {_hash_e}")

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
            # Phase 26-CCC: auto-enrich через ЕГРЮЛ
            c_row = await _create_or_enrich_contractor_from_receipt(
                first_receipt.seller_inn, first_receipt.seller_name, db
            )
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
            # Phase 26-CCC: auto-enrich через ЕГРЮЛ
            c_row = await _create_or_enrich_contractor_from_receipt(r.seller_inn, r.seller_name, db)
            db.add(c_row)
            await db.flush()
        receipt_to_contractor[r.id] = (c_row.id, r.seller_inn, r.seller_name)

    # Phase 26-WW-2 dedup: вынесено в helper _dedup_purchase_items_core (см. ниже).
    # Ключ нормализуется через float+round чтобы Decimal('392') и Decimal('392.00')
    # совпадали.
    _dedup_res = await _dedup_purchase_items_core(purchase_id, db)
    items_deduplicated = _dedup_res.get("deduplicated", 0)

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
                    _sum_or_total = ri.get('sum') or ri.get('total')
                    total = _Dec(str(_sum_or_total)) if _sum_or_total is not None else line_total(qty, price)
                except Exception:
                    total = _Dec('0')
                raw_name = (str(ri.get('name') or f"Позиция {idx}"))[:5000]
                _auto_item = _PI(
                    purchase_id=purchase_id,
                    item_name=raw_name,
                    quantity=qty,
                    unit='шт.',
                    unit_price=price,
                    total_price=total,
                    match_confirmed=False,
                    receipt_id=r.id,
                    # Phase 26-fff: fallback на nds-код если vat_rate отсутствует
                    # в raw_json (старые чеки, импортированные ДО маппинга)
                    vat_rate=ri.get('vat_rate') or _nds_code_to_rate_str(ri.get('nds')),
                )
                # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
                set_item_contractor(_auto_item, contractor_id=cid, inn=c_inn, name=c_name)
                db.add(_auto_item)
                items_autocreated += 1
        if items_autocreated:
            await db.flush()

    # Шаг A: items с receipt_id → overwrite contractor если mismatch +
    # backfill vat_rate из nds-кода raw_json (Phase 26-fff)
    linked_items_q = await db.execute(
        select(_PI).where(
            _PI.purchase_id == purchase_id,
            _PI.receipt_id.is_not(None),
        )
    )
    receipt_by_id = {r.id: r for r in receipts}
    for it in linked_items_q.scalars().all():
        pack = receipt_to_contractor.get(it.receipt_id)
        if pack:
            cid, c_inn, c_name = pack
            if it.contractor_id != cid:
                # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
                set_item_contractor(it, contractor_id=cid, inn=c_inn, name=c_name)
                items_updated += 1
        # vat_rate fallback: если NULL — найти соответствующий ri по name fuzzy
        # и поставить из nds-кода
        if not it.vat_rate:
            r = receipt_by_id.get(it.receipt_id)
            if r:
                raw_items = _extract_items(r.raw_json or {})
                best_ri = None
                best_score = 0
                for ri in raw_items:
                    s = _items_match_score(it, ri)
                    if s >= 2 and s > best_score:
                        best_score = s
                        best_ri = ri
                if best_ri:
                    new_rate = best_ri.get('vat_rate') or _nds_code_to_rate_str(best_ri.get('nds'))
                    if new_rate:
                        it.vat_rate = new_rate
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
                # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
                set_item_contractor(it, contractor_id=cid, inn=c_inn, name=c_name)
            items_updated += 1
            items_linked_by_fuzzy += 1

    # 3. acceptance_docs + PurchaseFile для каждого receipt
    import os as _os, hashlib as _hashlib
    from app.models.purchase_file import PurchaseFile as _PF
    UPLOAD_DIR = _os.environ.get('UPLOAD_DIR', '/data/uploads')
    existing_docs = list(p.acceptance_docs or [])
    docs_changed = False

    # Phase 27.1.11 / Phase 27.1.12: cleanup pre-existing duplicates в acceptance_docs
    # (по type+number+amount), включая legacy format где type=None но name="Чек"
    # ПРАВИЛО №6 (2026-09-07): дедуп — та же функция, что и backfill 26-ooo
    # (app.services.acceptance_docs.dedup), не собственная копия ключа.
    _deduped_docs = _acc_docs.dedup(existing_docs)
    if len(_deduped_docs) != len(existing_docs):
        docs_changed = True
    existing_docs = _deduped_docs

    # Phase 27.1.11 / Phase 27.1.12: helper — dedup не только по receipt_id,
    # но и по (type/name='Чек'+number+amount), включая legacy format без type
    def _is_existing_doc_for_receipt(rcpt, existing_list):
        fd_num = rcpt.fiscal_document_number
        amt = float(rcpt.total_sum) if rcpt.total_sum is not None else 0
        for d in existing_list:
            # Exact match по receipt_id
            if d.get("receipt_id") == rcpt.id:
                return d
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
                    if abs(float(d.get("amount") or 0) - float(amt or 0)) < 0.01:
                        return d
                except (TypeError, ValueError):
                    return d
        return None

    for r in receipts:
        existing_doc = _is_existing_doc_for_receipt(r, existing_docs)
        if existing_doc is not None:
            # Запись уже есть — обновить receipt_id если нужно
            if not existing_doc.get("receipt_id"):
                existing_doc["receipt_id"] = r.id
                docs_changed = True
            # Проверим file_id
            if not existing_doc.get("file_id"):
                # Попробовать прикрепить файл
                try:
                    png_bytes = _render_receipt_png(r)
                    content_hash = _hashlib.sha256(png_bytes).hexdigest()
                    existing_pf = (await db.execute(
                        select(_PF).where(_PF.purchase_id == purchase_id, _PF.content_hash == content_hash).limit(1)
                    )).scalar_one_or_none()
                    if existing_pf:
                        existing_doc["file_id"] = existing_pf.id
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
                        existing_doc["file_id"] = pf.id
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
        _acc_docs.replace_docs(p, existing_docs)

    # Phase 26-II / Phase 27.1.12: ContractItem find-or-update вместо create-always
    # (устранение дублей для advance-закупок при повторном recompute)
    contract_items_created = 0
    try:
        if p.purchase_method == 'advance':
            from app.models.contract_item import ContractItem as _CI
            all_items = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)
            )).scalars().all()
            # Загрузить все существующие CI для этой закупки (один запрос)
            all_existing_ci = (await db.execute(
                select(_CI).where(_CI.purchase_id == purchase_id)
            )).scalars().all()
            for pi in all_items:
                existing_ci = None
                # Pass 1: exact match по source_item_id
                for ci in all_existing_ci:
                    if ci.source_item_id == pi.id:
                        existing_ci = ci
                        break
                # Pass 2: fallback по name (orphan source_item_id)
                if not existing_ci and pi.item_name:
                    for ci in all_existing_ci:
                        if (ci.source_item_id is None or ci.source_item_id not in {x.id for x in all_items}):
                            if ci.name and ci.name.strip().lower() == pi.item_name.strip().lower():
                                existing_ci = ci
                                break
                if existing_ci:
                    # Update — link к актуальному PI + sync contract_id если NULL
                    if existing_ci.source_item_id != pi.id:
                        existing_ci.source_item_id = pi.id
                    if existing_ci.contract_id is None and p.contract_id is not None:
                        existing_ci.contract_id = p.contract_id
                    # NEW Phase 27.1.17: auto-fill vat_rate если пустое
                    if existing_ci.vat_rate is None and pi.vat_rate:
                        existing_ci.vat_rate = pi.vat_rate
                    # Не перезаписывать name/qty/price — это могут быть user edits
                else:
                    db.add(_CI(
                        purchase_id=purchase_id,
                        contract_id=p.contract_id,
                        source_item_id=pi.id,
                        name=pi.item_name or "Позиция",
                        quantity=pi.quantity,
                        unit=pi.unit or 'шт.',
                        unit_price=pi.unit_price,
                        total=pi.total_price,
                        vat_rate=pi.vat_rate,  # NEW Phase 27.1.17
                        match_confirmed=True,
                    ))
                    contract_items_created += 1
    except Exception as _ci_exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"recompute contract_items autocreate skipped: {_ci_exc}")

    # Phase 27.1.8: после dedup/recreate PI — relink ContractItem.source_item_id
    # где старые id'шки были обнулены dedup'ером или остались orphan'ами.
    # Inline relink устраняет orphan'ы на корню в той же транзакции.
    try:
        from app.models.contract_item import ContractItem as _CI_
        from sqlalchemy import select as _sel_ci, func as _func_ci

        # Найти все CI этого purchase у которых source_item_id = NULL (обнулены dedup'ером)
        # или указывают на несуществующий PI (orphan после пересоздания)
        all_ci_q = await db.execute(
            _sel_ci(_CI_).where(_CI_.purchase_id == purchase_id)
        )
        all_ci_for_purchase = all_ci_q.scalars().all()

        # Текущие PI для этого purchase (после всех операций выше)
        current_pi_rows = (await db.execute(
            _sel_ci(_PI).where(_PI.purchase_id == purchase_id)
        )).scalars().all()
        current_pi_ids = {pi.id for pi in current_pi_rows}

        ci_to_relink = [
            ci for ci in all_ci_for_purchase
            if ci.source_item_id is None or ci.source_item_id not in current_pi_ids
        ]

        relinked_inline = 0
        for ci in ci_to_relink:
            candidate = None

            # Pass 1: exact name match
            if ci.name:
                for pi in current_pi_rows:
                    if pi.item_name == ci.name:
                        candidate = pi
                        break

            # Pass 2: case-insensitive trimmed match
            if not candidate and ci.name:
                normalized = ci.name.strip().lower()
                for pi in current_pi_rows:
                    if pi.item_name and pi.item_name.strip().lower() == normalized:
                        candidate = pi
                        break

            # Pass 3: 1-to-1 fallback
            if not candidate:
                other_orphans = [c for c in ci_to_relink if c.purchase_id == purchase_id]
                if len(current_pi_rows) == 1 and len(other_orphans) == 1:
                    candidate = current_pi_rows[0]

            # Pass 4: qty + unit_price exact match
            if not candidate and ci.quantity is not None and ci.unit_price is not None:
                for pi in current_pi_rows:
                    if pi.quantity == ci.quantity and pi.unit_price == ci.unit_price:
                        candidate = pi
                        break

            if candidate:
                ci.source_item_id = candidate.id
                relinked_inline += 1
    except Exception as _relink_e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"recompute inline ci relink skipped: {_relink_e}")

    # Phase 26-YY: сохранить новый snapshot hash чтобы следующий GET без изменений
    # данных skip'нул всю эту работу.
    try:
        await db.flush()
        new_hash = await _compute_purchase_snapshot_hash(purchase_id, db)
        p.recompute_snapshot_hash = new_hash
    except Exception as _save_e:
        import logging as _lg
        _lg.getLogger(__name__).warning(f"snapshot hash save failed: {_save_e}")

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


# ── dedup helper (Phase 26-WW-2) ─────────────────────────────────────────────

async def _dedup_purchase_items_core(purchase_id: int, db: AsyncSession) -> dict:
    """Удаляет точные дубликаты PurchaseItem (name+total+receipt_id), оставляя min(id).
    Идемпотентно. НЕ commit — caller отвечает."""
    from sqlalchemy import select as _sel, update as _sa_upd, delete as _sa_del
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.contract_item import ContractItem as _CI

    def _norm_total(v):
        try:
            return round(float(v or 0), 2)
        except Exception:
            return 0.0

    rows = (await db.execute(
        _sel(_PI.id, _PI.item_name, _PI.total_price, _PI.receipt_id)
        .where(_PI.purchase_id == purchase_id)
        .order_by(_PI.id.asc())
    )).all()
    seen = {}
    ids_to_delete = []
    for r in rows:
        iid, name, total, rid = r
        key = (str(name or '').strip().lower(), _norm_total(total), rid)
        if key in seen:
            ids_to_delete.append(iid)
        else:
            seen[key] = iid
    if not ids_to_delete:
        return {"ok": True, "deduplicated": 0, "kept": len(seen)}
    # Снять FK ContractItem.source_item_id → SET NULL
    try:
        await db.execute(
            _sa_upd(_CI).where(_CI.source_item_id.in_(ids_to_delete)).values(source_item_id=None)
        )
    except Exception:
        pass
    await db.execute(_sa_del(_PI).where(_PI.id.in_(ids_to_delete)))
    await db.flush()
    return {"ok": True, "deduplicated": len(ids_to_delete), "kept": len(seen)}
