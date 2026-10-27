"""Слияние дублей каталога товаров БЕЗ ПОТЕРЬ (владелец, 27.10.2026, повод —
один и тот же товар лежит разными карточками у разных магазинов,
app/services/products_import_match.py сопоставляет только точное название и
это НЕ меняется; «один товар = одна карточка» достигается РУЧНЫМ слиянием).

ЕДИНСТВЕННАЯ функция слияния (ПРАВИЛО №6) — POST /api/products/merge
(app/routers/products_merge.py) и POST /api/products/deduplicate
(app/routers/products_match.py::deduplicate_products) оба вызывают
merge_products, не заводят вторую реализацию переноса.

Переносит на `winner` ВСЁ, что ссылается на `products.id` (проверено grep по
app/models — см. докстринг app/services/product_delete_impact.py, тот же
список FK):
  - purchase_items.product_id            (NO ACTION)      -> перенос
  - contract_items.product_id            (SET NULL)       -> перенос
  - wish_items.product_id                (SET NULL)       -> перенос
  - commercial_request_offers.product_id (SET NULL)       -> перенос
  - product_price_history.product_id     (CASCADE)        -> перенос (своя история)
  - supplier_products.product_id         (CASCADE, уник. supplier_id+product_id) -> перенос, дубль по supplier_id — удаляется
  - product_purchase_categories          (CASCADE, PK product_id+purchase_category_id) -> объединение множеств без дублей
  - product_photos.product_id            (CASCADE, PK product_id) -> перенос, только если у winner фото нет
  - product_description_history.product_id    (CASCADE) -> перенос (история остаётся читаемой)
  - product_description_proposals.product_id  (CASCADE) -> перенос
  - product_barcodes.product_id          (CASCADE, уник. product_id+barcode) -> перенос, дубль по barcode — удаляется (владелец, 27.10.2026)

Пустые поля winner'а дозаполняются из loser'ов — ТОЛЬКО через
product_description_history.set_product_description (ПРАВИЛО №6, единственный
писатель). description: winner пуст → берём loser'а; оба непустые и разные →
ВСЕГДА merge_missing_lines (winner целиком + недостающие строки loser'а,
никогда не заменяем — выбор winner'а в UI человеком делает его текст главным).
description_44fz: только заполнение пустого, непустое НЕ трогаем (может быть
верифицировано, Product.tz_44fz_verified_at) — см. _merge_description_field.
После переноса истории цен текущая цена winner'а пересчитывается
через app.services.price_actualization.actualize_product_price (write_history
=False) — тот же единственный писатель Product.price/price_source*, что и
везде в проекте.

Ничего не коммитит — вызывающий код (роутер) управляет транзакцией."""
from datetime import datetime as _dt
from typing import Optional

from sqlalchemy import select, update as sa_update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.commercial_request import CommercialRequestOffer
from app.models.contract_item import ContractItem
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_description_history import ProductDescriptionHistory
from app.models.product_description_proposal import ProductDescriptionProposal
from app.models.product_photo import ProductPhoto
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase_category import product_purchase_categories
from app.models.purchase_item import PurchaseItem
from app.models.supplier import SupplierProduct
from app.models.wish_item import WishItem
from app.services.price_actualization import actualize_product_price
from app.services.product_description_merge import merge_missing_lines
from app.services.product_description_history import set_product_description

MAX_LOSER_IDS = 50

# Простые скалярные поля winner'а, которые дозаполняются первым непустым
# значением из loser'ов (description/description_44fz — отдельно, через
# set_product_description, см. _merge_descriptions ниже; characteristics —
# отдельно, JSONB-список, см. ниже).
_FILL_SCALAR_FIELDS = (
    "manufacturer", "article", "unit", "clarification_link",
    "photo_url", "photo_link", "product_type", "pack_quantity", "pack_unit",
)


def _is_empty_country_origin(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("", "рф")


async def _merge_description_field(
    db: AsyncSession, winner: Product, loser: Product, field: str, user,
) -> bool:
    """Переносит `field` ('description'|'description_44fz') loser'а в winner.
    Человек сам выбирает, какую карточку оставить (winner), в UI слияния —
    её текст ГЛАВНЫЙ, loser не подменяет его целиком (владелец, 27.10.2026,
    правка: раньше ветка "loser не короче" заменяла весь текст winner'а, из
    текущей версии пропадали строки, которых не было у loser'а; то же самое
    стирало проверенное description_44fz — tz_44fz_verified_at).

    - winner пуст → берём loser'а целиком (заполнение пустого).
    - winner и loser совпадают → ничего не меняем.
    - field='description', тексты РАЗНЫЕ → ВСЕГДА merge_missing_lines(winner,
      loser) — winner целиком + недостающие строки loser'а, никакой замены
      (та же сборка, что и products_import_apply.py, ПРАВИЛО №6 — не вторая
      формула, просто больше не решаем "кто короче" — результат такой же
      merge, но без ветки полной замены). Если merge_missing_lines ничего не
      добавил (все строки loser'а по смыслу уже есть у winner) — история не
      пишется.
    - field='description_44fz', тексты РАЗНЫЕ → winner НЕ трогаем (его могли
      верифицировать — Product.tz_44fz_verified_at, это не формула "короче/
      длиннее", а прямой запрет трогать непустое 44-ФЗ описание при слиянии).

    Пишет через set_product_description (ПРАВИЛО №6 — единственный писатель),
    значит и история не теряется. True, если что-то изменилось."""
    loser_val = (getattr(loser, field, None) or "").strip()
    if not loser_val:
        return False
    winner_val = (getattr(winner, field, None) or "").strip()
    if not winner_val:
        history = await set_product_description(
            db, winner, field, getattr(loser, field), user, source="fill_empty",
        )
        return history is not None
    if winner_val == loser_val:
        return False
    if field == "description_44fz":
        return False
    final = merge_missing_lines(winner_val, loser_val)
    if final == winner_val:
        return False
    history = await set_product_description(db, winner, field, final, user, source="edit")
    return history is not None


async def merge_products(
    db: AsyncSession, winner_id: int, loser_ids: list[int], user,
) -> dict:
    """Переносит на winner_id всё от loser_ids (см. докстринг модуля), затем
    удаляет loser'ов. Возвращает отчёт {winner_id, losers: [...], transferred:
    {таблица: count}, filled_fields: [...]}. Поднимает ValueError на плохих
    id (вызывающий роутер превращает в 400/404/422)."""
    if winner_id in loser_ids:
        raise ValueError("winner_id не может быть среди loser_ids")
    if len(loser_ids) == 0:
        raise ValueError("loser_ids пуст")
    if len(loser_ids) > MAX_LOSER_IDS:
        raise ValueError(f"loser_ids: не более {MAX_LOSER_IDS} за один вызов")
    if len(set(loser_ids)) != len(loser_ids):
        raise ValueError("loser_ids содержит повторы")

    winner = await db.get(Product, winner_id)
    if winner is None:
        raise ValueError(f"Товар-получатель №{winner_id} не найден")
    losers: list[Product] = []
    for lid in loser_ids:
        loser = await db.get(Product, lid)
        if loser is None:
            raise ValueError(f"Товар-дубль №{lid} не найден")
        losers.append(loser)

    transferred: dict[str, int] = {
        "purchase_items": 0, "contract_items": 0, "wish_items": 0,
        "commercial_request_offers": 0, "product_price_history": 0,
        "supplier_products": 0, "product_purchase_categories": 0,
        "product_photo": 0, "product_description_history": 0,
        "product_description_proposals": 0, "product_barcodes": 0,
    }
    filled_fields: list[str] = []

    # Категории закупки winner'а — для объединения множеств без дублей PK.
    winner_category_ids = set((await db.execute(
        select(product_purchase_categories.c.purchase_category_id)
        .where(product_purchase_categories.c.product_id == winner_id)
    )).scalars().all())

    winner_has_photo = (await db.execute(
        select(ProductPhoto.product_id).where(ProductPhoto.product_id == winner_id)
    )).scalar_one_or_none() is not None

    # Штрихкоды winner'а (владелец, 27.10.2026) — для объединения без дублей
    # по UNIQUE(product_id, barcode), тот же приём, что у winner_category_ids.
    winner_barcodes = set((await db.execute(
        select(ProductBarcode.barcode).where(ProductBarcode.product_id == winner_id)
    )).scalars().all())

    for loser in losers:
        loser_id = loser.id

        # --- бизнес-документы: простой перенос FK ---
        r = await db.execute(
            sa_update(PurchaseItem).where(PurchaseItem.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["purchase_items"] += r.rowcount or 0

        r = await db.execute(
            sa_update(ContractItem).where(ContractItem.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["contract_items"] += r.rowcount or 0

        r = await db.execute(
            sa_update(WishItem).where(WishItem.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["wish_items"] += r.rowcount or 0

        r = await db.execute(
            sa_update(CommercialRequestOffer).where(CommercialRequestOffer.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["commercial_request_offers"] += r.rowcount or 0

        # --- собственная история товара: перенос, ничего не теряется ---
        r = await db.execute(
            sa_update(ProductPriceHistory).where(ProductPriceHistory.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["product_price_history"] += r.rowcount or 0

        r = await db.execute(
            sa_update(ProductDescriptionHistory).where(ProductDescriptionHistory.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["product_description_history"] += r.rowcount or 0

        r = await db.execute(
            sa_update(ProductDescriptionProposal).where(ProductDescriptionProposal.product_id == loser_id)
            .values(product_id=winner_id)
        )
        transferred["product_description_proposals"] += r.rowcount or 0

        # --- supplier_products: уникальный (supplier_id, product_id) —
        # дубль с winner'ом удаляется, остальное переносится ---
        loser_supplier_rows = (await db.execute(
            select(SupplierProduct.id, SupplierProduct.supplier_id)
            .where(SupplierProduct.product_id == loser_id)
        )).all()
        if loser_supplier_rows:
            winner_supplier_ids = set((await db.execute(
                select(SupplierProduct.supplier_id).where(SupplierProduct.product_id == winner_id)
            )).scalars().all())
            for sp_id, supplier_id in loser_supplier_rows:
                if supplier_id in winner_supplier_ids:
                    await db.execute(sa_delete(SupplierProduct).where(SupplierProduct.id == sp_id))
                else:
                    await db.execute(
                        sa_update(SupplierProduct).where(SupplierProduct.id == sp_id)
                        .values(product_id=winner_id)
                    )
                    winner_supplier_ids.add(supplier_id)
                    transferred["supplier_products"] += 1

        # --- product_purchase_categories: объединение множеств без дублей PK ---
        loser_category_ids = set((await db.execute(
            select(product_purchase_categories.c.purchase_category_id)
            .where(product_purchase_categories.c.product_id == loser_id)
        )).scalars().all())
        new_category_ids = loser_category_ids - winner_category_ids
        for cat_id in new_category_ids:
            await db.execute(
                product_purchase_categories.insert().values(
                    product_id=winner_id, purchase_category_id=cat_id,
                )
            )
            winner_category_ids.add(cat_id)
            transferred["product_purchase_categories"] += 1
        await db.execute(
            sa_delete(product_purchase_categories)
            .where(product_purchase_categories.c.product_id == loser_id)
        )

        # --- штрихкоды: UNIQUE(product_id, barcode) — дубль по barcode
        # удаляется, остальное переносится (владелец, 27.10.2026) ---
        loser_barcode_rows = (await db.execute(
            select(ProductBarcode.id, ProductBarcode.barcode)
            .where(ProductBarcode.product_id == loser_id)
        )).all()
        for bc_id, barcode in loser_barcode_rows:
            if barcode in winner_barcodes:
                await db.execute(sa_delete(ProductBarcode).where(ProductBarcode.id == bc_id))
            else:
                await db.execute(
                    sa_update(ProductBarcode).where(ProductBarcode.id == bc_id)
                    .values(product_id=winner_id)
                )
                winner_barcodes.add(barcode)
                transferred["product_barcodes"] += 1

        # --- фото: PK=product_id, переносим только если у winner его нет ---
        loser_photo = (await db.execute(
            select(ProductPhoto.product_id).where(ProductPhoto.product_id == loser_id)
        )).scalar_one_or_none() is not None
        if loser_photo:
            if winner_has_photo:
                await db.execute(sa_delete(ProductPhoto).where(ProductPhoto.product_id == loser_id))
            else:
                await db.execute(
                    sa_update(ProductPhoto).where(ProductPhoto.product_id == loser_id)
                    .values(product_id=winner_id)
                )
                winner.photo_mime = loser.photo_mime
                winner.photo_size = loser.photo_size
                winner_has_photo = True
                transferred["product_photo"] += 1

        # --- описание / описание 44-ФЗ: не короче, с историей ---
        if await _merge_description_field(db, winner, loser, "description", user):
            filled_fields.append(f"description (от №{loser_id})")
        if await _merge_description_field(db, winner, loser, "description_44fz", user):
            filled_fields.append(f"description_44fz (от №{loser_id})")

        # --- характеристики (JSONB-список) — заполняем, если у winner пусто ---
        if not (winner.characteristics or []) and (loser.characteristics or []):
            winner.characteristics = loser.characteristics
            flag_modified(winner, "characteristics")
            filled_fields.append(f"characteristics (от №{loser_id})")

        # --- простые скалярные поля ---
        for field in _FILL_SCALAR_FIELDS:
            if not getattr(winner, field, None) and getattr(loser, field, None):
                setattr(winner, field, getattr(loser, field))
                filled_fields.append(f"{field} (от №{loser_id})")

        if _is_empty_country_origin(winner.country_origin) and not _is_empty_country_origin(loser.country_origin):
            winner.country_origin = loser.country_origin
            filled_fields.append(f"country_origin (от №{loser_id})")

        # --- price_links: объединение по url, winner в приоритете ---
        if loser.price_links:
            existing_urls = {pl.get("url") for pl in (winner.price_links or []) if pl.get("url")}
            merged_links = list(winner.price_links or [])
            for pl in loser.price_links:
                if pl.get("url") and pl["url"] not in existing_urls:
                    merged_links.append(pl)
                    existing_urls.add(pl["url"])
            if merged_links != (winner.price_links or []):
                winner.price_links = merged_links
                flag_modified(winner, "price_links")

        # --- import_note: дописываем строку об объединении ---
        user_name = getattr(user, "full_name", None) or getattr(user, "username", None) or ""
        note_line = (
            f"Объединена с №{loser_id} «{loser.name}», {user_name}, "
            f"{_dt.now().strftime('%d.%m.%Y %H:%M')}"
        )
        winner.import_note = (
            f"{winner.import_note}\n{note_line}" if winner.import_note else note_line
        )

    winner.updated_at = _dt.utcnow()
    if user is not None:
        winner.updated_by = getattr(user, "full_name", None) or getattr(user, "username", None)

    await db.flush()

    # Текущая цена winner'а = самая свежая точка его (теперь объединённой)
    # истории — через единственный писатель Product.price/price_source*
    # (app.services.price_actualization.actualize_product_price,
    # write_history=False, чтобы не продублировать уже перенесённую строку).
    freshest = (await db.execute(
        select(ProductPriceHistory)
        .where(ProductPriceHistory.product_id == winner_id)
        .order_by(
            ProductPriceHistory.collected_at.desc().nulls_last(),
            ProductPriceHistory.id.desc(),
        )
        .limit(1)
    )).scalar_one_or_none()
    if freshest is not None:
        await actualize_product_price(
            db, winner,
            price=freshest.price,
            source=freshest.source or "import",
            source_ref=freshest.source_ref,
            contractor_id=freshest.contractor_id,
            collected_at=freshest.collected_at,
            user=user,
            write_history=False,
        )

    # Удаляем loser'ов — всё остальное (product_price_history, product_photos,
    # product_purchase_categories, supplier_products), что НЕ было явно
    # перенесено выше, уже либо перенесено, либо пусто; CASCADE подчищает
    # любые оставшиеся собственные строки loser'а.
    await db.execute(Product.__table__.delete().where(Product.id.in_([l.id for l in losers])))

    return {
        "winner_id": winner_id,
        "loser_ids": loser_ids,
        "transferred": transferred,
        "filled_fields": filled_fields,
    }
