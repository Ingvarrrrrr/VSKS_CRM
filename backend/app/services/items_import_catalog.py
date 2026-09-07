"""Item-import catalog/DB-write helpers — extracted from purchase_items_import.py
(Правило №5, разрезание сессии 2026-09-08).

_upsert_product_to_catalog is imported directly by app/routers/products.py
(`from app.routers.purchase_items_import import _upsert_product_to_catalog`);
purchase_items_import.py re-exports the name from here so that import keeps
working unchanged. Both helpers write to the DB (product catalog / PurchaseItem
rows) but have no HTTP-layer concerns of their own — used by the legacy excel
import (purchase_items_import.py), the mapped import
(purchase_items_import_mapped.py) and the smart import
(purchase_items_import_smart.py) endpoints.
"""
from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.purchase_item import PurchaseItem
from app.auth.jwt import get_single_org_id
from app.services.product_matcher import score as _fuzzy_score, SCORE_AUTO as _SCORE_AUTO
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.product_unit import backfill_product_unit

# ---------------------------------------------------------------------------
# Product-catalog upsert helper
# ---------------------------------------------------------------------------

async def _upsert_product_to_catalog(
    db, item_name: str, item_type: str, unit_price, description: str = "",
    category: str | None = None, product_type: str | None = None,
    import_note: str | None = None, updated_by: str | None = None,
    unit: str | None = None,
) -> int:
    """Find or create a product in the global catalog. Returns product.id.

    Правила конфликтов при импорте из файла:
    - цена: обновляется из файла (файл — источник актуальной цены);
    - категория/вид: БД главнее — из файла берём только если в БД пусто
      (для категории дефолт «Прочее» считается пустым);
    - import_note: кто/как/когда загрузил — перезаписывается свежим импортом;
    - ед. измерения (владелец, 2026-09-01): БД главнее — уже заполненную не
      трогаем; иначе берём из САМОГО импорта (параметр `unit`, БЕЗ дефолтов
      вида 'шт' — их проставляют вызывающие для PurchaseItem.unit отдельно);
      если импорт её тоже не принёс — из истории закупок этого товара
      (единственная встречавшаяся), см. app/services/product_unit.py.
    """
    from datetime import datetime as _dt
    norm = item_name.strip().lower()
    existing = (await db.execute(
        select(Product).where(func.lower(Product.name) == norm)
    )).scalar_one_or_none()
    if existing:
        new_price = Decimal(str(unit_price)) if unit_price else None
        if new_price and existing.price != new_price:
            existing.price = new_price
        if category and (not existing.category or existing.category == 'Прочее'):
            existing.category = category
        if product_type and not existing.product_type:
            existing.product_type = product_type
        if import_note:
            existing.import_note = import_note
            existing.updated_at = _dt.utcnow()
            if updated_by:
                existing.updated_by = updated_by
        await backfill_product_unit(db, existing, import_unit=unit)
        return existing.id
    p = Product(
        name=item_name.strip(),
        description=description or "",
        category=category or 'Прочее',
        product_type=product_type or item_type or "товар",
        item_kind=item_type or "товар",
        unit=(unit or "").strip() or None,  # брэнд-новый товар — истории покупок ещё нет
        price=Decimal(str(unit_price)) if unit_price else Decimal("0"),
        is_active=True,
        import_note=import_note,
        updated_at=_dt.utcnow() if import_note else None,
        updated_by=updated_by if import_note else None,
    )
    db.add(p)
    await db.flush()
    return p.id

async def _save_smart_preview_to_purchase(
    pid: int,
    preview: list[dict],
    purchase,
    db: AsyncSession,
    current_user,
    skip_catalog: bool = False,
) -> dict:
    """Сохраняет preview-строки в БД как PurchaseItem'ы.
    Переиспользуется как из xlsx-ветки, так и (потенциально) из markitdown-ветки.
    skip_catalog=True: не вызывать _upsert для несматченных → product_id=None.
    """
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    products = (await db.execute(prod_q)).scalars().all()
    product_by_name = {(p.name or "").lower().strip(): p for p in products}

    added = matched_catalog = new_in_catalog = 0
    errors_list: list[str] = []
    for row_idx, row_data in enumerate(preview, start=1):
        item_name = (row_data["item_name"] or "")[:500]
        qty = Decimal(str(row_data["quantity"])) if row_data["quantity"] else Decimal("1")
        unit_price = Decimal(str(row_data["unit_price"])) if row_data["unit_price"] else None
        total_price = Decimal(str(row_data["total_price"])) if row_data["total_price"] else None
        # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): позиция смарт-
        # импорта наследует ФЭО-категорию закупки (feo_planned_item_id импорт не
        # проставляет). Аггрегация ошибок по строкам — строка пропускается, импорт
        # остальных продолжается.
        try:
            await assert_tz_not_over_plan(
                db,
                feo_planned_item_id=None,
                feo_category_id=getattr(purchase, "feo_category_id", None),
                quantity=qty,
                unit_price=unit_price,
                total_price=total_price if total_price is not None else (qty * unit_price if unit_price else None),
                item_name=item_name,
            )
        except HTTPException as _tz_exc:
            errors_list.append(f"Строка {row_idx}: {_tz_exc.detail}")
            continue
        if skip_catalog:
            # «Не добавлять в каталог» (напр. авансовые платежи): позиции должны быть
            # один-в-один как в чеке, без какой-либо привязки к каталогу. Не матчим вовсе.
            product_id = None
            matched = None
        else:
            # 1) exact match (fast path)
            matched = product_by_name.get(item_name.lower().strip())
            if not matched:
                # 2) fuzzy fallback
                best_score = 0.0
                best_candidate = None
                for _key, _p in product_by_name.items():
                    _s = _fuzzy_score(item_name, _p.name if hasattr(_p, 'name') else _key)
                    if _s > best_score:
                        best_score = _s
                        best_candidate = _p
                if best_score >= _SCORE_AUTO and best_candidate is not None:
                    matched = best_candidate
            if matched:
                product_id = matched.id
                matched_catalog += 1
                if not unit_price and matched.price:
                    unit_price = matched.price
                    total_price = qty * unit_price
                if isinstance(matched, Product):
                    await backfill_product_unit(db, matched, import_unit=row_data.get("unit_raw"))
            else:
                _uname = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
                product_id = await _upsert_product_to_catalog(
                    db, item_name, row_data["item_type"], unit_price,
                    import_note=f"Смарт-импорт из файла, {_uname}, {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    updated_by=_uname,
                    unit=row_data.get("unit_raw"),
                )
                new_in_catalog += 1
        if total_price is None and unit_price:
            total_price = qty * unit_price
        db.add(PurchaseItem(
            purchase_id=pid, product_id=product_id,
            item_name=item_name, item_type=row_data["item_type"],
            quantity=qty, unit=row_data["unit"],
            unit_price=unit_price, total_price=total_price,
        ))
        added += 1
    await db.commit()
    return {"ok": True, "added": added, "matched_catalog": matched_catalog, "new_in_catalog": new_in_catalog, "errors": errors_list}


