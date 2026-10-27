"""Единая точка входа для актуализации цены товара — владелец, 2026-08-29.

Владелец: «Цена может актуализироваться по запросу КП или по уже совершённым
контрактам». Все места кода, которые меняют product.price по «настоящему»
основанию (не черновой ввод), обязаны звать actualize_product_price — иначе
price_updated_at/price_source рассинхронизируются с фактической ценой и
контроль устаревания (app/services/price_freshness.py) начнёт врать.

Вызывающие точки (см. TASKS для этой сессии):
  1. app/routers/purchase_transitions.py — переход в 'contracted'
  2. app/routers/products.py — update_product/patch_product (ручной ввод / пересчёт из price_links)
  3. app/routers/products.py — импорт каталога (существующий товар)
  4. app/routers/products.py — POST /{id}/price-actualization
  5. app/routers/commercial_requests.py — POST /offers/{offer_id}/accept
"""
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory

VALID_PRICE_SOURCES = ("contract", "kp", "manual", "import", "monitoring")


def _parse_collected_date(collected_at) -> Optional[_date]:
    """Единый парсер даты точки (datetime/date/ISO-строка/None) — используют
    и actualize_product_price, и actualize_contract_item_prices (ПРАВИЛО №6,
    не два парсинга одной и той же даты)."""
    if isinstance(collected_at, datetime):
        return collected_at.date()
    if isinstance(collected_at, _date):
        return collected_at
    if isinstance(collected_at, str) and collected_at:
        try:
            return _date.fromisoformat(collected_at[:10])
        except ValueError:
            return None
    return None


def _is_stale_against_product(collected_at, product: Product) -> bool:
    """True, если дата точки `collected_at` СТАРШЕ текущей product.
    price_updated_at — значит, эта точка не должна подменять уже более
    свежую цену/контрактные поля товара (план clever-bouncing-lantern.md,
    часть 2, п.1). Нет даты точки или даты текущей цены — не стейл (по
    умолчанию применяем, как и раньше)."""
    collected_date = _parse_collected_date(collected_at)
    if collected_date is None or product.price_updated_at is None:
        return False
    return collected_date < product.price_updated_at.date()


async def actualize_product_price(
    db: AsyncSession,
    product: Product,
    *,
    price,
    source: str,
    source_ref: Optional[str] = None,
    contractor_id: Optional[int] = None,
    collected_at=None,
    note: Optional[str] = None,
    user=None,
    write_history: bool = True,
    region: Optional[str] = None,
    quantity=None,
    unit: Optional[str] = None,
    purchase_item_id: Optional[int] = None,
    skip_if_older: bool = False,
    update_product_price: bool = True,
    store_article: Optional[str] = None,
) -> Optional[_date]:
    """Проставляет цену + метаданные актуализации на product и (по умолчанию)
    пишет строку в product_price_history. Не коммитит — вызывающий код
    управляет транзакцией (как и остальные мутации в этих роутерах).

    `skip_if_older` (план clever-bouncing-lantern.md, часть 2, п.1): если True
    и `collected_at` этой точки СТАРШЕ текущей product.price_updated_at —
    Product.price/price_source* не трогаем (история всё равно пишется, если
    write_history=True) — иначе загрузка факта со старыми договорами затирала
    бы свежую цену старой. Используется только вызовами из контрактного пути
    (actualize_contract_item_prices); остальные вызывающие (ручная
    актуализация, КП, импорт) явного решения владельца о дате не содержат —
    для них параметр остаётся False (поведение не меняется).

    `update_product_price` (план, часть 1, п.2 products_price.py): False —
    запись идёт ТОЛЬКО в историю, Product.price/price_source* не трогаем
    вообще (используется POST /price-history без галочки «Редактировать
    каталог» для товара, у которого цена уже есть).

    Возвращает collected_date (распарсенную дату точки) — чтобы вызывающий
    код мог залогировать/проверить решение, без второго парсинга даты.

    `store_article` (владелец, 27.10.2026, manufacturer_article/store_article)
    — номер товара в КОНКРЕТНОМ магазине этой строки (contractor_id), пишется
    в строку истории как есть (не на Product — там только производительский
    manufacturer_article, см. Product.article/products_import_apply.py).
    """
    if price is not None and not isinstance(price, Decimal):
        price = Decimal(str(price))
    if quantity is not None and not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))

    collected_date = _parse_collected_date(collected_at)

    apply_to_product = update_product_price
    if apply_to_product and skip_if_older and _is_stale_against_product(collected_at, product):
        apply_to_product = False

    if apply_to_product:
        product.price = price
        product.price_updated_at = datetime.utcnow()
        product.price_source = source
        product.price_source_ref = source_ref
        product.price_source_contractor_id = contractor_id

    if write_history:
        db.add(ProductPriceHistory(
            product_id=product.id,
            price=price,
            source=source,
            source_ref=source_ref,
            contractor_id=contractor_id,
            collected_at=collected_date,
            note=note,
            created_by=getattr(user, "id", None) if user is not None else None,
            region=region,
            quantity=quantity,
            unit=unit,
            purchase_item_id=purchase_item_id,
            store_article=store_article,
        ))

    return collected_date


async def record_price_point(
    db: AsyncSession,
    product: Product,
    *,
    price,
    source: str,
    source_ref: Optional[str] = None,
    contractor_id: Optional[int] = None,
    collected_at=None,
    user=None,
    region: Optional[str] = None,
    quantity=None,
    unit: Optional[str] = None,
    store_article: Optional[str] = None,
) -> bool:
    """Пишет ТОЛЬКО точку истории цены — product.price/price_source* не
    трогает (= actualize_product_price(update_product_price=False), тот же
    единственный INSERT в ProductPriceHistory, ПРАВИЛО №6, второй такой
    вставки в проекте не заводить).

    Нужна там, где за один импорт у товара несколько магазинов и у каждого
    должна остаться СВОЯ строка истории, даже если его цена не стала
    "текущей" ценой товара (владелец, 27.10.2026, задача product_merge п.2,
    app/services/products_import_apply.py). Требует persisted product.id —
    для ещё не сохранённых (unflushed) товаров дедуп/откладывание до flush
    делает вызывающий код сам.

    Защита от точного повтора (тот же product_id+contractor_id+price+
    collected_at+store_article уже есть в истории) — не пишет вторую
    одинаковую строку, возвращает False. store_article включён в дедуп-ключ
    (владелец, 27.10.2026): разные store_article у одного магазина/цены/даты
    считаются РАЗНЫМИ строками (например, перевыгрузка с измененившимся
    номером товара в магазине не должна молча проглатываться как дубль).
    Иначе пишет строку и возвращает True."""
    collected_date = _parse_collected_date(collected_at)
    if product.id is not None and contractor_id is not None:
        dup = (await db.execute(
            select(ProductPriceHistory.id).where(
                ProductPriceHistory.product_id == product.id,
                ProductPriceHistory.contractor_id == contractor_id,
                ProductPriceHistory.price == price,
                ProductPriceHistory.collected_at == collected_date,
                ProductPriceHistory.store_article == store_article,
            ).limit(1)
        )).scalar_one_or_none()
        if dup is not None:
            return False
    await actualize_product_price(
        db, product, price=price, source=source, source_ref=source_ref,
        contractor_id=contractor_id, collected_at=collected_at, user=user,
        region=region, quantity=quantity, unit=unit,
        update_product_price=False,
        store_article=store_article,
    )
    return True


async def actualize_contract_item_prices(
    db: AsyncSession,
    purchase,
    items: Iterable,
    *,
    contract_org_id: Optional[int] = None,
    user=None,
) -> None:
    """Пишет точку истории цены (source='contract') ПО КАЖДОЙ позиции закупки
    с product_id — единственный цикл такого рода (ПРАВИЛО №6): переиспользуют
    его и переход в статус «заключён договор» (app.services.
    purchase_transition_core), и материализация договора при загрузке факта
    (app.services.historical_fact_import.existing_update.materialize_contract
    — раньше этот путь НЕ писал историю/product.contract_price для позиций
    вовсе, план clever-bouncing-lantern.md «подключить тот же писатель»).

    Цена за единицу — final_unit_price (уточнённая после заключения), если
    проставлена, иначе unit_price. Регион точки — Purchase.delivery_region
    (место поставки ЭТОЙ закупки), нормализованный к каноническому имени
    субъекта РФ; нет места поставки → region=None (точка идёт только в расчёт
    без фильтра). Защита от дубля при повторном вызове (повторный импорт,
    повторный проход миграции) — по purchase_item_id (уникальный индекс),
    НЕ по product+source_ref+collected_at — так несколько позиций одного
    товара в одном договоре каждая получает свою точку, а не считаются
    дублями друг друга.

    Владелец (план, часть 2, п.1): точка в историю пишется ВСЕГДА (если не
    дубль); а Product.price/contract_price/contract_number/contract_date
    договор меняет только если дата ЭТОГО договора НЕ старше текущей
    price_updated_at товара — иначе загрузка факта со старыми договорами
    затирала бы свежую цену более старой (_is_stale_against_product, тот же
    helper, что и внутри actualize_product_price — ПРАВИЛО №6).
    """
    from app.services.ru_regions import canonical_region_name

    region = canonical_region_name(getattr(purchase, "delivery_region", None))
    for item in items:
        if not getattr(item, "product_id", None):
            continue
        product = await db.get(Product, item.product_id)
        if not product:
            continue
        item_price = item.final_unit_price if item.final_unit_price is not None else item.unit_price
        if not _is_stale_against_product(purchase.contract_date, product):
            product.contract_price = item_price
            product.contract_number = purchase.contract_number
            product.contract_date = purchase.contract_date
            if contract_org_id is not None:
                product.contract_org_id = contract_org_id
        dup = (await db.execute(
            select(ProductPriceHistory.id).where(
                ProductPriceHistory.purchase_item_id == item.id,
            ).limit(1)
        )).scalar_one_or_none()
        await actualize_product_price(
            db, product,
            price=item_price,
            source="contract",
            source_ref=purchase.contract_number,
            contractor_id=getattr(purchase, "contractor_id", None),
            collected_at=purchase.contract_date,
            user=user,
            write_history=dup is None,
            region=region,
            quantity=item.quantity,
            unit=item.unit,
            purchase_item_id=item.id,
            skip_if_older=True,
        )
