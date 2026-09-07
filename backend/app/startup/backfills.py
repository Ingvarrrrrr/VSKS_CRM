"""Идемпотентные бэкфиллы данных, выполняемые при каждом старте приложения.
Перенесено 1:1 из app/__init__.py.lifespan при разрезании файла на модули
(Правило №5). Каждый блок — отдельная функция с исходным
комментарием-заголовком; run() вызывает их в исходном порядке.

Зависимости порядка (сохранены — эта категория запускается ПОСЛЕ
startup.legacy_ddl.run(), которая создаёт нужные колонки/таблицы —
в частности `_ensure_purchase_items_receipt_id` до fuzzy-link ниже):
внутри самой этой категории backfill_cbr_history идёт до refresh_cbr_rates.
"""
import logging

from app.database import async_session


async def _phase22_bank_payments_hash_backfill():
    # Phase 22: backfill source_row_hash для legacy записей + удаление дубликатов
    try:
        from sqlalchemy import select as _sel, text as _text
        from app.models.bank_statement import BankPayment
        from app.services.bank_statement_parser import compute_row_hash

        async with async_session() as db:
            # 1. Заполнить hash для legacy записей с NULL
            q = await db.execute(_sel(BankPayment).where(BankPayment.source_row_hash.is_(None)))
            legacy = q.scalars().all()
            backfilled = 0
            for bp in legacy:
                if bp.raw_json:
                    try:
                        bp.source_row_hash = compute_row_hash(bp.raw_json)
                        backfilled += 1
                    except Exception:
                        pass
            if backfilled:
                await db.commit()

            # 2. Удалить дубликаты — оставляем MIN(id) на каждый hash
            await db.execute(_text("""
                DELETE FROM bank_payments
                WHERE id NOT IN (
                    SELECT MIN(id) FROM bank_payments
                    WHERE source_row_hash IS NOT NULL
                    GROUP BY source_row_hash
                )
                AND source_row_hash IS NOT NULL
            """))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 22 hash backfill skipped (non-fatal): {e}")


# Phase 26-QQ (dedup контрагентов по ИНН) перенесено в
# scripts/merge_duplicates_by_inn.py (D8/D9, волна 4b, Правило №6) — это
# разовый data-fix, не часть старта приложения. Логика теперь живёт в
# app/services/contractor_dedup.py::merge_duplicate_contractors_by_inn.


async def _phase22_restore_bank_payments_typed_backfill():
    # Phase 22 RESTORE: backfill typed-fields для legacy bank_payments c payment_date IS NULL
    # Идемпотентно — skip если все строки уже типизированы. Запускается на каждом старте.
    try:
        from sqlalchemy import select as _sel, func as _func
        from app.models.bank_statement import BankPayment
        from app.services.bank_statement_parser import reparse_bank_payment_typed
        async with async_session() as db:
            null_count = (await db.execute(
                _sel(_func.count()).select_from(BankPayment).where(BankPayment.payment_date.is_(None))
            )).scalar() or 0
            if null_count > 0:
                q = await db.execute(_sel(BankPayment).where(BankPayment.payment_date.is_(None)))
                rows = q.scalars().all()
                fixed = 0
                for bp in rows:
                    if not bp.raw_json:
                        continue
                    reparse_bank_payment_typed(bp)
                    if bp.payment_date is not None or bp.purpose_text is not None:
                        fixed += 1
                if fixed:
                    await db.commit()
                logging.getLogger(__name__).info(
                    f"Phase 22 backfill: {fixed}/{null_count} bank_payments re-typed from raw_json"
                )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 22 bank_payments backfill skipped (non-fatal): {e}")


async def _phase26_mmm_sync_purchase_from_contract():
    # Phase 26-mmm: sync денорм-полей purchases ← contracts при старте.
    # Чинит исторические рассинхронизации (contract_number/date/contractor_id
    # из соседних контрактов после ручных правок до Phase 26-j-1, когда
    # _sync_purchase_from_contract либо не вызывался, либо не копировал
    # contractor_id — это явно наблюдалось в проде: purchase #802 имел
    # contract_number='51802 ОП/КОР' но contract_date='27.05.2021' от
    # соседнего договора 110677/КОР, в реестре «Контрагент» = пусто).
    # Идемпотентно: вызывает _sync_purchase_from_contract который перезаписывает
    # только если значения отличаются от contract.*. Non-fatal (Phase 22 pattern).
    try:
        from sqlalchemy import select as _sel
        from app.database import async_session as _async_session
        from app.models.purchase import Purchase as _Purchase
        from app.routers.purchases import _sync_purchase_from_contract as _sync_pc
        async with _async_session() as _db:
            _rows = (await _db.execute(
                _sel(_Purchase).where(_Purchase.contract_id.is_not(None))
            )).scalars().all()
            _updated = 0
            for _p in _rows:
                _before = (_p.contract_number, _p.contract_date, _p.purchase_contract_type, _p.contractor_id)
                await _sync_pc(_p, _db)
                _after = (_p.contract_number, _p.contract_date, _p.purchase_contract_type, _p.contractor_id)
                if _before != _after:
                    _updated += 1
            if _updated:
                await _db.commit()
            logging.getLogger(__name__).info(
                f"Phase 26-mmm backfill: {_updated}/{len(_rows)} purchases sync'нуты из contracts"
            )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 26-mmm purchase←contract sync skipped (non-fatal): {e}"
        )


async def _phase26_ooo_acceptance_docs_dedup():
    # Phase 26-ooo: дедуп existing acceptance_docs[] от исторических дублей.
    # Видимый симптом: «Документ 1: Чек 83287 5034» + «Документ 2: Чек 83287 5034»
    # одно и то же. Источник: legacy записи без receipt_id + auto-add с
    # receipt_id давали 2 строки на один чек. Phase 26-ooo backend-фикс
    # усилил дедуп при auto-add, но исторические дубли уже в БД.
    # Идемпотентно: убирает дубли по ключу (type, number, amount).
    #
    # ПРАВИЛО №6 (2026-09-07, группа D4): алгоритм дедупа переехал в
    # app.services.acceptance_docs.dedup — единственный писатель acceptance_docs
    # (используется также purchase_receipts.py/purchases.py/purchase_import_parser.py).
    # Этот backfill теперь просто зовёт его на исторических данных.
    try:
        from sqlalchemy import select as _sel
        from sqlalchemy.orm.attributes import flag_modified as _flag_mod
        from app.database import async_session as _async_session
        from app.models.purchase import Purchase as _Purchase
        from app.services.acceptance_docs import dedup as _dedup_docs, sync_scalars as _sync_scalars
        async with _async_session() as _db:
            _q = await _db.execute(
                _sel(_Purchase).where(_Purchase.acceptance_docs.is_not(None))
            )
            _purchases = _q.scalars().all()
            _dedup_total = 0
            for _p in _purchases:
                _docs = list(_p.acceptance_docs or [])
                if len(_docs) <= 1:
                    continue
                _kept = _dedup_docs(_docs)
                if len(_kept) != len(_docs):
                    _p.acceptance_docs = _kept
                    _flag_mod(_p, "acceptance_docs")
                    # ПРАВИЛО №6: дедуп мог поменять docs[0] — синхронизируем
                    # кэш-скаляры (единственный писатель — sync_scalars).
                    _sync_scalars(_p)
                    _dedup_total += len(_docs) - len(_kept)
            if _dedup_total:
                await _db.commit()
            logging.getLogger(__name__).info(
                f"Phase 26-ooo acceptance_docs dedup: removed {_dedup_total} duplicates across {len(_purchases)} purchases"
            )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 26-ooo acceptance_docs dedup skipped (non-fatal): {e}"
        )


async def _phase24_restore_advance_contract_date_backfill():
    # Phase 24 RESTORE: backfill contract_date/number для advance purchases
    # с receipts но без основания. Идемпотентно — skip если 0 строк нуждаются.
    try:
        from sqlalchemy import select as _sel, or_
        from app.models.purchase import Purchase as _Purchase
        from app.models.purchase_receipt import PurchaseReceipt as _PurchaseReceipt
        async with async_session() as db:
            q = await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    or_(_Purchase.contract_date.is_(None), _Purchase.contract_number.is_(None))
                )
            )
            advances = q.scalars().all()
            fixed = 0
            for p in advances:
                rq = await db.execute(
                    _sel(_PurchaseReceipt)
                    .where(_PurchaseReceipt.purchase_id == p.id)
                    .order_by(_PurchaseReceipt.receipt_datetime.asc())
                    .limit(1)
                )
                receipt = rq.scalar_one_or_none()
                if not receipt:
                    continue
                changed = False
                if receipt.receipt_datetime and not p.contract_date:
                    rd = receipt.receipt_datetime
                    p.contract_date = rd.date() if hasattr(rd, 'date') else rd
                    changed = True
                if receipt.fiscal_document_number and not p.contract_number:
                    p.contract_number = str(receipt.fiscal_document_number)
                    changed = True
                if changed:
                    fixed += 1
            if fixed:
                await db.commit()
                logging.getLogger(__name__).info(
                    f"Phase 24 backfill: {fixed} advance purchases получили contract_date/number из receipts"
                )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 24 advance backfill skipped (non-fatal): {e}")


async def _phase26_bbb_registry_number_backfill():
    # Phase 26-BBB: backfill purchases.registry_number для записей без него.
    # Формат «РЕЕ-{year}-{id:05d}» — тот же что и для новых (purchases.py auto-gen,
    # ~стр. 590-592). В модели Purchase нет created_at → year берётся из NOW().
    try:
        from sqlalchemy import text as _text_bbb
        from app.database import engine as _engine_bbb
        async with _engine_bbb.begin() as conn:
            await conn.execute(_text_bbb("""
                UPDATE purchases
                SET registry_number = 'РЕЕ-' || EXTRACT(YEAR FROM NOW())::int || '-' || LPAD(id::text, 5, '0')
                WHERE registry_number IS NULL OR registry_number = ''
            """))
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-BBB registry_number backfill skipped (non-fatal): {e}")


async def _phase26_cc_propagate_contractor_to_items():
    # Phase 26-CC: propagate purchase.contractor_id → items.contractor_id для advance.
    # Если на уровне закупки контрагент проставлен вручную, items без contractor_id
    # должны его наследовать. Самый дешёвый backfill — без чтения raw_json.
    try:
        from sqlalchemy import select as _sel
        from app.models.purchase import Purchase as _Purchase
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.contractor import Contractor as _Ctr
        async with async_session() as db:
            advances_with_c = (await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    _Purchase.contractor_id.is_not(None),
                )
            )).scalars().all()
            propagated_total = 0
            for p in advances_with_c:
                c_row = await db.get(_Ctr, p.contractor_id)
                if not c_row:
                    continue
                null_items = (await db.execute(
                    _sel(_PI).where(
                        _PI.purchase_id == p.id,
                        _PI.contractor_id.is_(None),
                    )
                )).scalars().all()
                for it in null_items:
                    # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
                    from app.services.item_contractor import set_item_contractor as _set_ic
                    _set_ic(it, contractor=c_row)
                    propagated_total += 1
            if propagated_total:
                await db.commit()
                logging.getLogger(__name__).info(f"Phase 26-CC propagated: {propagated_total} items inherited contractor from purchase")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-CC propagate skipped (non-fatal): {e}")


async def _phase26_bb_fuzzy_link_items_to_receipts():
    # Phase 26-BB: per-receipt привязка через fuzzy match по 4 полям
    # (name + quantity + unit_price + total_price)
    try:
        from sqlalchemy import select as _sel
        from app.models.purchase import Purchase as _Purchase
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.purchase_receipt import PurchaseReceipt as _PR
        from app.models.contractor import Contractor as _Ctr
        from app.routers.purchase_receipts import _items_match_score as _fuzzy
        from app.routers.purchase_receipts import _extract_items as _ext_items
        async with async_session() as db:
            advances = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            linked_total = 0
            for (pid,) in advances:
                unlinked = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.receipt_id.is_(None))
                )).scalars().all()
                if not unlinked:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid)
                )).scalars().all()
                if not receipts:
                    continue
                for it in unlinked:
                    best_r = None
                    best_score = 0
                    for r in receipts:
                        items_list = _ext_items(r.raw_json or {})
                        for ri in items_list:
                            s = _fuzzy(it, ri)
                            if s >= 2 and s > best_score:
                                best_score = s
                                best_r = r
                    if best_r:
                        it.receipt_id = best_r.id
                        if best_r.seller_inn:
                            c_row = (await db.execute(
                                _sel(_Ctr).where(_Ctr.inn == best_r.seller_inn)
                            )).scalar_one_or_none()
                            if not c_row:
                                c_row = _Ctr(inn=best_r.seller_inn, name=best_r.seller_name or f"ИНН {best_r.seller_inn}")
                                db.add(c_row)
                                await db.flush()
                            # ПРАВИЛО №6 (группа D5): единственный писатель — item_contractor.set_item_contractor.
                            from app.services.item_contractor import set_item_contractor as _set_ic
                            _set_ic(it, contractor=c_row)
                        linked_total += 1
            if linked_total:
                await db.commit()
                logging.getLogger(__name__).info(f"Phase 26-BB backfill: {linked_total} purchase_items linked to receipts via fuzzy")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-BB backfill skipped (non-fatal): {e}")


async def _phase26_w_backfill_contractor_from_receipts():
    # Phase 26-W: backfill PurchaseItem.contractor_id для авансовых закупок,
    # где контрагент создан из чека, но item.contractor_id остался NULL
    # (deploy до Phase 26-V не заполнял contractor_id из seller_inn чека).
    try:
        from sqlalchemy import select as _sel, update as _upd
        from app.models.purchase import Purchase as _Purchase
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.purchase_receipt import PurchaseReceipt as _PR
        from app.models.contractor import Contractor as _Ctr
        async with async_session() as db:
            # Находим все advance-закупки с item.contractor_id IS NULL
            q = await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )
            advance_ids = [row[0] for row in q.all()]
            backfilled = 0
            for pid in advance_ids:
                # Получаем seller_inn из первого по дате PurchaseReceipt
                rq = await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc()).limit(1)
                )
                receipt = rq.scalar_one_or_none()
                if not receipt or not receipt.seller_inn:
                    continue
                # Resolve contractor по ИНН (или создаём)
                cq = await db.execute(
                    _sel(_Ctr).where(_Ctr.inn == receipt.seller_inn)
                )
                contractor = cq.scalar_one_or_none()
                if not contractor:
                    contractor = _Ctr(
                        inn=receipt.seller_inn,
                        name=receipt.seller_name or f"ИНН {receipt.seller_inn}",
                    )
                    db.add(contractor)
                    await db.flush()
                # Update PurchaseItem (only NULL ones). ПРАВИЛО №6 (группа D5):
                # FK задаётся — текст обнуляется, см. item_contractor.item_contractor_fk_values
                # (Core update(), не ORM-объекты — та же логика, что у set_item_contractor).
                from app.services.item_contractor import item_contractor_fk_values as _fk_values
                res = await db.execute(
                    _upd(_PI).where(
                        _PI.purchase_id == pid,
                        _PI.contractor_id.is_(None),
                    ).values(**_fk_values(contractor.id))
                )
                backfilled += res.rowcount or 0
            if backfilled:
                await db.commit()
                logging.getLogger(__name__).info(
                    f"Phase 26-W backfill: {backfilled} purchase_items got contractor_id from receipts"
                )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-W backfill skipped (non-fatal): {e}")


async def _subsidy_org_materialize_backfill():
    # subsidy-org-materialize: backfill зеркальных организаций для субсидий,
    # привязанных к контрагентам (получатель субсидии должен попадать в Персонал/Иерархию)
    try:
        from app.routers.subsidies import _materialize_org_from_contractor
        from app.models.subsidy import Subsidy as _SubMat
        from app.models.contractor import Contractor as _CtrMat
        from sqlalchemy import select as _select_mat
        async with async_session() as _db_mat:
            _cids = (await _db_mat.execute(
                _select_mat(_SubMat.contractor_id)
                .where(_SubMat.contractor_id.isnot(None))
                .distinct()
            )).scalars().all()
            for _cid in _cids:
                _ctr = await _db_mat.get(_CtrMat, _cid)
                if _ctr is None:
                    continue
                try:
                    # 2026-09-01: нет current_user (фон, не HTTP-запрос) — берём
                    # аккаунт из org_id уже существующей субсидии этого
                    # контрагента, чтобы новая org не осталась без root_org_id
                    # (см. app/services/org_account_resolution.py).
                    _sub_row = (await _db_mat.execute(
                        _select_mat(_SubMat.org_id)
                        .where(_SubMat.contractor_id == _cid, _SubMat.org_id.isnot(None))
                        .limit(1)
                    )).scalar_one_or_none()
                    await _materialize_org_from_contractor(_db_mat, _ctr, _sub_row)
                except Exception as _e_ctr:
                    logging.getLogger(__name__).warning(
                        f"subsidy-org materialize backfill: contractor_id={_cid} skipped ({_e_ctr})"
                    )
        logging.getLogger(__name__).info(
            f"subsidy-org materialize backfill: {len(_cids)} контрагент(ов) обработано"
        )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"subsidy-org materialize backfill skipped (non-fatal): {e}"
        )


# org-dedup (мерж дублей organizations по ИНН) перенесено в
# scripts/merge_duplicates_by_inn.py (D8/D9, волна 4b, Правило №6) — это
# разовый data-fix, не часть старта приложения. Логика (не менялась) — в
# app/services/org_dedup.py::_merge_duplicate_orgs_by_inn.


async def _price_freshness_fx_rates_refresh():
    # price-freshness: разовый бэкафилл истории курса USD + обновление на
    # сегодня с cbr.ru при старте (владелец, 2026-08-29 + ревью 2026-08-29).
    # backfill ПЕРЕД refresh: без истории курсовой триггер в
    # app/services/price_freshness.py никогда не срабатывает (в fx_rates
    # была бы только «сегодняшняя» строка). Non-fatal — если ЦБ недоступен,
    # актуализация цены просто не учитывает курсовой триггер до следующего
    # рестарта/деплоя. Обе функции сами пропускают сетевой запрос, если
    # данных уже достаточно — никакого бесконечного цикла здесь не заводим.
    try:
        from app.services.fx_rates import backfill_cbr_history, refresh_cbr_rates
        async with async_session() as _db_fx:
            await backfill_cbr_history(_db_fx)
            await refresh_cbr_rates(_db_fx)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"fx_rates refresh skipped (non-fatal): {e}"
        )


async def run():
    """Вызывает все idempotent бэкфиллы в исходном порядке (см. app/__init__.py.lifespan до разрезания)."""
    await _phase22_bank_payments_hash_backfill()
    await _phase22_restore_bank_payments_typed_backfill()
    await _phase26_mmm_sync_purchase_from_contract()
    await _phase26_ooo_acceptance_docs_dedup()
    await _phase24_restore_advance_contract_date_backfill()
    await _phase26_bbb_registry_number_backfill()
    await _phase26_cc_propagate_contractor_to_items()
    await _phase26_bb_fuzzy_link_items_to_receipts()
    await _phase26_w_backfill_contractor_from_receipts()
    await _subsidy_org_materialize_backfill()
    await _price_freshness_fx_rates_refresh()
