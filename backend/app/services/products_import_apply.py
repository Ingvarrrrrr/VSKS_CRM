"""Применение явного маппинга колонок Excel-файла к каталогу товаров
(создание/обновление `Product`). Единственный цикл создания/обновления
товаров из импорта — им пользуются POST /api/products/import (обратная
совместимость со старым угадыванием колонок — угадывание теперь только
подсказка, см. services/products_import_map.py) и POST
/api/products/import-mapped (ручной маппинг с предпросмотром), чтобы
поведение импорта не расходилось между двумя входами (ПРАВИЛО №6).

Перенесено из routers/products_import.py:214-384 (план
dreamy-booping-piglet.md, задача B, п.3) — сама бизнес-логика (дедуп по
name+description, актуализация цены, докидывание пустых полей, создание
PurchaseItem при purchase_id) НЕ менялась. Новое: явные индексы колонок вместо
модуля-глобального `col_idx`, `dry_run` (flush без commit + rollback), и
подробный построчный отчёт `rows` с причиной пропуска/действия — раньше
пустые имена молча пропускались без счётчика и без номера строки, из-за чего
дефект №2 (1022 «товара»-категории) не был виден в самом отчёте импорта.
"""
from datetime import datetime as _dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.product import Product
from app.services.price_actualization import actualize_product_price
from app.services.product_unit import backfill_product_unit


def _cell(row, col_idx: dict, field: str):
    idx = col_idx.get(field)
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    return str(v).strip() if v is not None else None


def _to_bool(v) -> bool:
    if v is None:
        return True
    return str(v).lower().strip() in ("да", "yes", "true", "1", "+")


def _to_dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _norm_key(s) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip().lower()


async def apply_products_import(
    db: AsyncSession,
    data_rows: list,
    col_idx: dict,
    *,
    filename: str,
    current_user,
    purchase_id: Optional[int] = None,
    dry_run: bool = False,
    first_row_num: int = 2,
) -> dict:
    """data_rows — строки данных БЕЗ строки заголовка. col_idx —
    {field: индекс колонки в data_rows} (name/description/category/
    product_type/price/photo_link/is_reusable/is_active/feo_category_name/
    quantity/unit/link_url_N/link_price_N). first_row_num — номер строки
    Excel (1-based, как видит пользователь), соответствующий data_rows[0] —
    нужен, чтобы номера строк в отчёте указывали на реальную строку файла, а
    не на индекс внутри урезанного списка.

    dry_run=True — цикл выполняется по-настоящему (включая flush, чтобы
    поймать реальные ошибки БД), но транзакция откатывается перед выходом:
    ничего не сохраняется, product_ids не возвращаются.

    Возвращает {created, updated, skipped, errors, product_ids,
    rows: [{row, action, name, reason}]}, action ∈
    created | updated | skipped | error. КАЖДАЯ строка данных (включая
    полностью пустые строки листа — они тоже попадают в отчёт как
    action=skipped/«нет наименования») учтена и видна в отчёте: раньше
    (routers/products_import.py, до правки) строка без имени просто
    молчаливо пропускалась через `continue` без счётчика и без номера —
    именно поэтому дефект №2 плана dreamy-booping-piglet.md (1022
    «товара»-категории) не был виден в самом отчёте импорта. Владелец на
    боевом файле («ТЗ для АПИ (4).xlsx», лист «ТЗ») подтвердил именно такую
    сквозную нумерацию: 1018 создано + 220 пропущено «нет наименования» =
    1238 из 1239 строк данных, первая пропущенная — строка 1019.
    """
    from app.models.feo_category import FeoCategory
    feo_rows = (await db.execute(select(FeoCategory))).scalars().all()
    feo_by_name = {f.name.lower().strip(): f.id for f in feo_rows}

    existing_result = await db.execute(select(Product))
    existing_by_key: dict = {}
    for ep in existing_result.scalars().all():
        k = _norm_key(ep.name) + "|" + _norm_key(ep.description)
        existing_by_key[k] = ep

    created = 0
    updated = 0
    skipped = 0
    errors: list = []
    report_rows: list = []
    all_products: list = []
    product_row_data: list = []

    _user_name = getattr(current_user, "full_name", None) or getattr(current_user, "username", "") or ""
    _import_note = (
        f"Импорт каталога из файла «{filename}», "
        f"{_user_name}, {_dt.now().strftime('%d.%m.%Y %H:%M')}"
    )

    try:
        for i, row in enumerate(data_rows):
            row_num = first_row_num + i
            name = None
            try:
                name = _cell(row, col_idx, "name")
                if not name:
                    skipped += 1
                    report_rows.append({"row": row_num, "action": "skipped", "name": None, "reason": "нет наименования"})
                    continue

                desc_val = _cell(row, col_idx, "description")
                dedup_key = _norm_key(name) + "|" + _norm_key(desc_val)

                price_links = []
                for n in range(1, 10):
                    url = _cell(row, col_idx, f"link_url_{n}")
                    if not url:
                        break
                    price_val = _to_dec(_cell(row, col_idx, f"link_price_{n}"))
                    price_links.append({"url": url, "price": float(price_val) if price_val else None})

                feo_name = _cell(row, col_idx, "feo_category_name")
                feo_id = feo_by_name.get(feo_name.lower().strip()) if feo_name else None

                price = _to_dec(_cell(row, col_idx, "price"))
                if not price and price_links:
                    prices = [l["price"] for l in price_links if l["price"]]
                    if prices:
                        price = Decimal(str(round(sum(prices) / len(prices), 2)))

                qty_str = _cell(row, col_idx, "quantity")
                unit_raw = _cell(row, col_idx, "unit")  # без дефолта — для бэкфилла Product.unit
                unit_str = unit_raw or "шт."
                row_qty = None
                if qty_str:
                    try:
                        row_qty = Decimal(str(qty_str).replace(",", ".").replace(" ", ""))
                    except Exception:
                        pass

                if dedup_key in existing_by_key:
                    ep = existing_by_key[dedup_key]
                    if price and ep.price != price:
                        # Актуализация цены (владелец, 2026-08-29): цена пришла из
                        # импортируемого Excel-файла — source='import'.
                        await actualize_product_price(
                            db, ep, price=price, source="import",
                            source_ref=filename, user=current_user,
                        )

                    def _fill(attr, val):
                        if val and not getattr(ep, attr):
                            setattr(ep, attr, val)

                    # Категория: «Прочее» — дефолт, считаем пустым; заполненную в БД не трогаем (БД главнее)
                    cat_val = _cell(row, col_idx, "category")
                    if cat_val and (not ep.category or ep.category == "Прочее"):
                        ep.category = cat_val
                    _fill("product_type", _cell(row, col_idx, "product_type"))
                    _fill("photo_link", _cell(row, col_idx, "photo_link"))
                    _fill("description", desc_val)

                    ep.import_note = _import_note
                    ep.updated_at = _dt.utcnow()
                    ep.updated_by = _user_name

                    if feo_id and not ep.feo_category_id:
                        ep.feo_category_id = feo_id

                    if price_links and not ep.price_links:
                        ep.price_links = price_links
                        flag_modified(ep, "price_links")

                    # Единица измерения (владелец, 2026-09-01): не трогаем уже
                    # заполненную; иначе — из самого импорта, иначе — из истории
                    # закупок этого товара (единственная встречавшаяся).
                    await backfill_product_unit(db, ep, import_unit=unit_raw)

                    all_products.append(ep)
                    product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price or ep.price})
                    updated += 1
                    report_rows.append({"row": row_num, "action": "updated", "name": name, "reason": "уже в каталоге — обновлён"})
                    continue

                p = Product(
                    name=name,
                    description=desc_val,
                    category=_cell(row, col_idx, "category") or "Прочее",
                    product_type=_cell(row, col_idx, "product_type"),
                    unit=(unit_raw or "").strip() or None,  # брэнд-новый товар — истории покупок ещё нет
                    price=price,
                    photo_link=_cell(row, col_idx, "photo_link"),
                    is_reusable=_to_bool(_cell(row, col_idx, "is_reusable")),
                    is_active=_to_bool(_cell(row, col_idx, "is_active")),
                    feo_category_id=feo_id,
                    price_links=price_links or [],
                    import_note=_import_note,
                    updated_at=_dt.utcnow(),
                    updated_by=_user_name,
                )
                db.add(p)
                all_products.append(p)
                product_row_data.append({"qty": row_qty, "unit": unit_str, "price": price})
                created += 1
                report_rows.append({"row": row_num, "action": "created", "name": name, "reason": None})
            except Exception as e:
                errors.append({"row": row_num, "name": name or "?", "message": str(e)})
                report_rows.append({"row": row_num, "action": "error", "name": name, "reason": str(e)})

        # Flush to get product IDs (и поймать реальные ошибки БД до commit/rollback)
        await db.flush()

        product_ids = [p.id for p in all_products]

        # Если purchase_id передан — добавить ВСЕ товары (новые + существующие)
        # позициями закупки. В dry_run закупку не трогаем — она может быть
        # реальной и уже содержать позиции, которые нельзя откатывать вместе с
        # пробным прогоном каталога.
        if purchase_id and all_products and not dry_run:
            from app.models.purchase_item import PurchaseItem
            from app.services.item_amounts import line_total
            for idx_p, p in enumerate(all_products):
                rd = product_row_data[idx_p] if idx_p < len(product_row_data) else {}
                qty = rd.get("qty") or Decimal("1")
                unit = rd.get("unit") or "шт."
                unit_price = rd.get("price") or p.price
                total = line_total(qty, unit_price) if unit_price else None
                db.add(PurchaseItem(
                    purchase_id=purchase_id,
                    product_id=p.id,
                    item_name=p.name[:500],
                    item_type=p.product_type or "товар",
                    quantity=qty,
                    unit=unit,
                    unit_price=unit_price,
                    total_price=total,
                ))
            await db.flush()

        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "product_ids": [] if dry_run else product_ids,
        "rows": report_rows,
    }
