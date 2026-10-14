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

ПРАВИЛО ВЛАДЕЛЬЦА (14.10.2026): цена позиции из загружаемого файла (план
закупок / ТЗ закупки / позиции закупки) — это цена ЭТОЙ субсидии/закупки, она
живёт в самой позиции (purchase_items.unit_price / плановой позиции). В
Product.price / ProductPriceHistory эта цена НЕ пишется — отменяет прежнее
поведение _apply_import_to_existing_product и _upsert_product_to_catalog
(писали через actualize_product_price(source='import')). Обратное
направление (подстановка цены каталога в позицию, если позиция цены не
принесла) не трогается — см. ниже по файлу "if not unit_price and
matched.price".
"""
from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.purchase_item import PurchaseItem
from app.auth.jwt import get_single_org_id
from app.services.item_amounts import line_total
from app.services.feo_plan import assert_tz_not_over_plan
from app.services.product_unit import backfill_product_unit
from app.services.product_catalog_match import (
    find_exact_product, index_products_by_name,
)
from app.services.qty_price_check import resolve_qty_price_choice
from app.services.items_import_tz_choice import match_catalog_product, resolve_tz_description

# ---------------------------------------------------------------------------
# Product-catalog upsert helper
# ---------------------------------------------------------------------------

async def _apply_import_to_existing_product(
    db, existing: Product, *, unit_price=None, description: str | None = None,
    category: str | None = None, product_type: str | None = None,
    unit: str | None = None, import_note: str | None = None,
    updated_by: str | None = None, user=None,
) -> None:
    """Дополняет уже найденный товар данными из импорта (владелец, 2026-09-14:
    «загрузка ДОПОЛНЯЕТ существующий товар... заполняет пустые поля значениями
    из файла и НЕ затирает уже заполненные»). Единая точка входа — вызывается
    и из _upsert_product_to_catalog (fallback, когда fast-path вызывающего
    кода сам не нашёл товар), и напрямую роутерами импорта позиций закупки в
    ветке «уже сматчено по имени», чтобы не дублировать это же правило по
    каждому роутеру (Правило №6).

    Правила конфликтов:
    - цена: НЕ пишем в каталог (решение владельца, 14.10.2026 — отменяет
      прежнее поведение, описанное здесь раньше: «добавляет ещё одну запись
      по цене к уже имеющимся, чтобы правильнее считалась средняя»). Цена из
      загружаемого файла (план закупок / ТЗ закупки / позиции закупки) —
      цена ЭТОЙ закупки/субсидии, она живёт в самой позиции
      (purchase_items.unit_price / плановой позиции), в products.price и
      product_price_history НЕ попадает. unit_price здесь принимается и
      игнорируется для совместимости вызывающего кода (preview-импорт шлёт
      цену по каждой строке независимо от того, матчится товар или нет);
    - описание: НЕ пишем в каталог СУЩЕСТВУЮЩЕГО товара вообще — ни поверх
      заполненного, ни в пустое (решение владельца, 14.10.2026, план
      item-tz-description.md: «плохое ТЗ одного не должно испортить всем» —
      каталог общий для всего приложения, org_id=NULL). Текст из файла идёт
      в CВОЁ поле позиции (WishItem.tz_description / PurchaseItem.tz_description,
      см. app/services/item_tz.py), не в Product.description. Параметр
      `description` здесь принимается и ИГНОРИРУЕТСЯ для совместимости
      вызывающего кода (роутеры импорта продолжают передавать его по старой
      сигнатуре) — отменяет прежнее поведение «дополняет, если в БД пусто».
      Новый товар, заводимый ЭТИМ ЖЕ импортом (_upsert_product_to_catalog,
      ветка "не найден"), — другое дело, у него описания в БД ещё вообще нет,
      получить его из файла не запрещено (см. там же ниже по файлу);
    - категория/вид: БД главнее — из файла берём только если в БД пусто (для
      категории дефолт «Прочее» тоже считается пустым);
    - import_note: кто/как/когда загрузил — перезаписывается свежим импортом;
    - ед. измерения (владелец, 2026-09-01): БД главнее — уже заполненную не
      трогаем; иначе берём из САМОГО импорта, см. app/services/product_unit.py.
    """
    from datetime import datetime as _dt
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


async def _upsert_product_to_catalog(
    db, item_name: str, item_type: str, unit_price, description: str = "",
    category: str | None = None, product_type: str | None = None,
    import_note: str | None = None, updated_by: str | None = None,
    unit: str | None = None, user=None,
) -> int:
    """Find or create a product in the global catalog. Returns product.id.

    Точный (не fuzzy) поиск существующего товара — через find_exact_product
    (единая нормализация имени, Правило №6, см. app/services/product_catalog_match.py).
    Найден → дополняем через _apply_import_to_existing_product, НЕ заводим
    второй товар. Не найден → создаём новый.
    """
    existing = await find_exact_product(db, item_name)
    if existing:
        await _apply_import_to_existing_product(
            db, existing,
            unit_price=unit_price, description=description,
            category=category, product_type=product_type, unit=unit,
            import_note=import_note, updated_by=updated_by, user=user,
        )
        return existing.id
    from datetime import datetime as _dt
    p = Product(
        name=item_name.strip(),
        description=description or "",
        category=category or 'Прочее',
        product_type=product_type or item_type or "товар",
        item_kind=item_type or "товар",
        unit=(unit or "").strip() or None,  # брэнд-новый товар — истории покупок ещё нет
        # price НЕ задаём (решение владельца 14.10.2026 — цена позиции
        # загружаемого файла в каталог не пишется, см. докстринг модуля выше).
        is_active=True,
        import_note=import_note,
        updated_at=_dt.utcnow() if import_note else None,
        updated_by=updated_by if import_note else None,
    )
    db.add(p)
    await db.flush()  # нужен p.id (используется вызывающим кодом ниже по стеку)
    # price НЕ пишем (решение владельца 14.10.2026, отменяет прежнее поведение
    # этого места — раньше здесь была actualize_product_price(source='import'),
    # заводившая товар сразу с ценой строки импорта). unit_price у нового
    # товара каталога остаётся None — так же, как при создании товара "на
    # лету" из позиции закупки (app/services/purchase_create_core.py,
    # app/routers/purchases.py::update_purchase).
    return p.id

async def _save_smart_preview_to_purchase(
    pid: int,
    preview: list[dict],
    purchase,
    db: AsyncSession,
    current_user,
    skip_catalog: bool = False,
    resolutions: dict | None = None,
    vat_on_top: bool = False,
    tz_choices: dict | None = None,
) -> dict:
    """Сохраняет preview-строки в БД как PurchaseItem'ы.
    Переиспользуется как из xlsx-ветки, так и (потенциально) из markitdown-ветки.
    skip_catalog=True: не вызывать _upsert для несматченных → product_id=None.

    resolutions: {row_num(str): 'recalc_sum'|'recalc_price'|'keep'} — выбор
    пользователя по строкам, где кол-во × цена ≠ сумма из файла (Дефект 2,
    владелец, 2026-09-14; см. app/services/qty_price_check.py). row_num —
    значение row_data['row'], выставленное парсером (номер строки файла), не
    порядковый индекс превью.

    tz_choices: {row_num(str): 'catalog'|'file'} — выбор владельца в окне
    сравнения ТЗ (план item-tz-description.md, 14.10.2026): "catalog" →
    tz_description=NULL (действующее ТЗ подтянется из каталога, см.
    app/services/item_tz.py); иначе/по умолчанию — текст из файла (см.
    app/services/items_import_tz_choice.py::resolve_tz_description).

    vat_on_top (задача «НДС сверху», 02.10.2026) — True, когда импорт
    распознал файл как УПД (_legacy_detect_best_table::is_upd, цена без
    налога + сумма с налогом). Проставляет purchase.contract_vat_on_top и
    row_data['vat_rate'] на каждую созданную позицию — единственное место
    применения результата УПД-детекции к сохранённым данным."""
    org_id = get_single_org_id(current_user)
    prod_q = select(Product)
    if org_id:
        prod_q = prod_q.where((Product.org_id == org_id) | (Product.org_id.is_(None)))
    products = (await db.execute(prod_q)).scalars().all()
    product_by_name = index_products_by_name(products)

    added = matched_catalog = new_in_catalog = 0
    errors_list: list[str] = []
    if vat_on_top and preview and not getattr(purchase, "contract_vat_on_top", False):
        purchase.contract_vat_on_top = True
    for row_idx, row_data in enumerate(preview, start=1):
        item_name = (row_data["item_name"] or "")[:500]
        qty = Decimal(str(row_data["quantity"])) if row_data["quantity"] else Decimal("1")
        unit_price = Decimal(str(row_data["unit_price"])) if row_data["unit_price"] else None
        total_price = Decimal(str(row_data["total_price"])) if row_data["total_price"] else None
        _choice = (resolutions or {}).get(str(row_data.get("row"))) if row_data.get("row") is not None else None
        if _choice and _choice != "keep":
            unit_price, total_price = resolve_qty_price_choice(qty, unit_price, total_price, _choice)
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
                total_price=total_price if total_price is not None else (line_total(qty, unit_price) if unit_price else None),
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
            # 1) exact match (fast path) — normalize_product_name (Правило №6,
            # см. product_catalog_match.py): обрезка + схлопывание пробелов + lower()
            _uname = getattr(current_user, 'full_name', None) or getattr(current_user, 'username', '') or ''
            # Exact + fuzzy — match_catalog_product (Правило №6, см.
            # app/services/items_import_tz_choice.py): та же функция, которой
            # preview-ветки роутеров строят "catalog_description" — чтобы
            # окно сравнения показывало ровно тот товар, который здесь же и
            # сматчится при сохранении.
            matched = match_catalog_product(item_name, product_by_name)
            if matched:
                product_id = matched.id
                matched_catalog += 1
                if not unit_price and matched.price:
                    unit_price = matched.price
                    total_price = line_total(qty, unit_price)
                if isinstance(matched, Product):
                    await _apply_import_to_existing_product(
                        db, matched,
                        unit_price=unit_price,
                        import_note=f"Смарт-импорт из файла, {_uname}, {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                        updated_by=_uname,
                        unit=row_data.get("unit_raw"),
                        user=current_user,
                    )
            else:
                product_id = await _upsert_product_to_catalog(
                    db, item_name, row_data["item_type"], unit_price,
                    import_note=f"Смарт-импорт из файла, {_uname}, {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    updated_by=_uname,
                    unit=row_data.get("unit_raw"),
                    user=current_user,
                )
                new_in_catalog += 1
        if total_price is None and unit_price:
            total_price = line_total(qty, unit_price)
        db.add(PurchaseItem(
            purchase_id=pid, product_id=product_id,
            item_name=item_name, item_type=row_data["item_type"],
            quantity=qty, unit=row_data["unit"],
            unit_price=unit_price, total_price=total_price,
            vat_rate=row_data.get("vat_rate") if vat_on_top else None,
            # Своё ТЗ позиции (владелец, 14.10.2026, план item-tz-description.md) —
            # текст характеристик ИЗ ФАЙЛА (row_data["description"], см.
            # app/services/items_import_parsing.py::_smart_import_xlsx_direct) —
            # НИКОГДА не в каталог, только в саму позицию закупки. Выбор
            # владельца в окне сравнения (tz_choices) может переключить на
            # NULL → возьмётся каталожное (resolve_tz_description, Правило №6).
            tz_description=resolve_tz_description(row_data.get("description"), row_data.get("row"), tz_choices),
        ))
        added += 1
    await db.commit()
    return {"ok": True, "added": added, "matched_catalog": matched_catalog, "new_in_catalog": new_in_catalog, "errors": errors_list}


