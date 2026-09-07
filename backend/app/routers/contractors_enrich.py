"""Массовое обогащение контрагентов из ЕГРЮЛ/чеков + синхронизация денормализованных имён.

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Тот же префикс
/api/contractors, регистрируется рядом с contractors.router.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contractor import Contractor
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


@router.post("/enrich-all-from-egrul")
async def enrich_all_contractors_from_egrul(
    limit: int = Query(50, ge=1, le=500, description="Сколько контрагентов обработать за один запуск"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Phase 26-CCC: bulk backfill.

    Для всех Contractor где name длиннее 80 символов И full_name пустое
    И ИНН задан → попытка ЕГРЮЛ enrich (короткое name в Contractor.name,
    длинное в Contractor.full_name + ОГРН/КПП/адрес/форма/подписант).

    Идемпотентно: не перезаписывает уже заполненные поля.
    Запускать batch'ами через ?limit=N (max 500). Возвращает stats.
    """
    from app.routers.purchase_receipts import _create_or_enrich_contractor_from_receipt

    rows = (await db.execute(
        select(Contractor)
        .where(func.length(Contractor.name) > 80)
        .where(Contractor.full_name.is_(None))
        .where(Contractor.inn.is_not(None))
        .limit(limit)
    )).scalars().all()

    enriched = 0
    skipped = 0
    failed = 0
    for c in rows:
        try:
            new_c = await _create_or_enrich_contractor_from_receipt(c.inn, c.name, db)
            # Применяем только если ЕГРЮЛ реально дал более короткое имя
            if new_c.name and new_c.name != c.name and len(new_c.name) < len(c.name):
                # Сохраняем старое длинное в full_name если оно ещё пустое
                if not c.full_name:
                    c.full_name = c.name
                c.name = new_c.name
                # Если ЕГРЮЛ вернул более точное full_name — используем его
                if new_c.full_name:
                    c.full_name = new_c.full_name
                if not c.ogrn and new_c.ogrn:
                    c.ogrn = new_c.ogrn
                if not c.kpp and new_c.kpp:
                    c.kpp = new_c.kpp
                if not c.address and new_c.address:
                    c.address = new_c.address
                if not c.org_type and new_c.org_type:
                    c.org_type = new_c.org_type
                if not c.signatory and new_c.signatory:
                    c.signatory = new_c.signatory
                enriched += 1
            else:
                skipped += 1
        except Exception:
            failed += 1

    await db.commit()
    return {
        "ok": True,
        "enriched": enriched,
        "skipped_no_change": skipped,
        "failed": failed,
        "total_processed": len(rows),
    }


@router.post("/enrich-from-receipts")
async def enrich_contractors_from_receipts(
    limit: int = Query(50, ge=1, le=500, description="Сколько ИНН из чеков обработать за один запуск"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Phase 26-CCC-2: обогащение через ЕГРЮЛ для ВСЕХ контрагентов,
    которые встречаются в PurchaseReceipt.seller_inn.

    Отличия от /enrich-all-from-egrul:
    - Берёт ИНН не из Contractor.inn, а из уникальных PurchaseReceipt.seller_inn.
    - ПЕРЕЗАПИСЫВАЕТ Contractor.name на короткое из ЕГРЮЛ (даже если текущее
      короткое — синхронизируем с актуальным ЕГРЮЛ-значением).
    - Заполняет full_name и остальные пустые поля.
    """
    from app.routers.purchase_receipts import _create_or_enrich_contractor_from_receipt
    from app.models.purchase_receipt import PurchaseReceipt

    # Уникальные ИНН продавцов из чеков
    inns_q = await db.execute(
        select(PurchaseReceipt.seller_inn)
        .where(PurchaseReceipt.seller_inn.is_not(None))
        .distinct()
        .limit(limit)
    )
    inns = [r[0] for r in inns_q.all() if r[0]]

    enriched = 0
    name_shortened = 0
    not_found = 0
    failed = 0
    for inn in inns:
        try:
            c_row = (await db.execute(
                select(Contractor).where(Contractor.inn == inn).limit(1)
            )).scalar_one_or_none()
            if not c_row:
                not_found += 1
                continue
            new_c = await _create_or_enrich_contractor_from_receipt(inn, c_row.name, db)
            if not new_c.name:
                failed += 1
                continue
            # ПЕРЕЗАПИСЫВАЕМ name на короткое из ЕГРЮЛ (Phase 26-CCC-2)
            if new_c.name != c_row.name:
                # Сохраняем длинное в full_name если оно ещё пустое
                if not c_row.full_name and len(c_row.name) > len(new_c.name):
                    c_row.full_name = c_row.name
                c_row.name = new_c.name
                name_shortened += 1
            # full_name обновляем если ЕГРЮЛ дал более полное
            if new_c.full_name and (not c_row.full_name or len(new_c.full_name) > len(c_row.full_name or '')):
                c_row.full_name = new_c.full_name
            # Прочие поля — только если пусты
            if not c_row.ogrn and new_c.ogrn:
                c_row.ogrn = new_c.ogrn
            if not c_row.kpp and new_c.kpp:
                c_row.kpp = new_c.kpp
            if not c_row.address and new_c.address:
                c_row.address = new_c.address
            if not c_row.org_type and new_c.org_type:
                c_row.org_type = new_c.org_type
            if not c_row.signatory and new_c.signatory:
                c_row.signatory = new_c.signatory
            enriched += 1
        except Exception:
            failed += 1

    await db.commit()
    return {
        "ok": True,
        "total_inns_from_receipts": len(inns),
        "enriched": enriched,
        "name_shortened": name_shortened,
        "contractor_not_found": not_found,
        "failed": failed,
    }


@router.post("/sync-denormalized-names")
async def sync_denormalized_contractor_names(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Phase 26-CCC-3: синхронизировать PurchaseItem.contractor_name
    (denormalized snapshot из чека) с актуальным Contractor.name по contractor_id.

    Нужно после обогащения Contractor.name через ЕГРЮЛ — иначе в UI реестров
    остаются длинные старые имена из чеков, хотя в Contractor уже короткое.
    """
    result = await db.execute(_text("""
        UPDATE purchase_items
        SET contractor_name = c.name
        FROM contractors c
        WHERE purchase_items.contractor_id = c.id
          AND (purchase_items.contractor_name IS DISTINCT FROM c.name)
    """))
    await db.commit()
    return {"ok": True, "updated_rows": result.rowcount}
