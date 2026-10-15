"""purchase_drill_text.py — ОДИН общий хелпер «что поискать/показать по
закупке» для drill-окон карточек (план abstract-noodling-pelican.md,
15.10.2026, п.6 техчасти: «Всем строкам-закупкам — items_text и supplier
(общий хелпер с п.1, один)»).

items_text — наименования, описания (tz_description позиции, либо, если его
нет, описание товара каталога Product.description) и наименование товара
каталога ВСЕХ позиций закупки, одной строкой через « · » — та же информация,
по которой уже умеет искать `ordersSearch.ts::purchaseMatchesSearch` на
фронте (owner, план п.6/7: «логика уже есть в поиске заявок и закупок, её
копируем») — здесь только СБОР текста на бэке, сам поиск (разбор слов,
сравнение) остаётся на фронте (`utils/textSearch.ts`/`useDrillSearch.ts`).

supplier — наименование поставщика закупки: Purchase.contractor_id → Contractor.name,
фолбэк — PurchaseItem.contractor_name первой позиции закупки (бывает заполнен
у позиций без привязки к карточке контрагента).

Один запрос на ВЕСЬ список purchase_id (без N+1) — используется
dashboard_type_drill.py (п.1) и dashboard_metric_drill.py/metric_drill_rows.py
(п.2) — ПРАВИЛО №6, вторая реализация сбора текста закупки не заводится."""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


async def purchase_drill_texts(db: AsyncSession, purchase_ids: Iterable[int]) -> dict[int, dict]:
    """{purchase_id: {"items_text": str, "supplier": Optional[str]}} — см.
    докстринг модуля. Отсутствующий purchase_id в ответе — закупка без
    позиций и без поставщика (вызывающий код использует .get(pid, {})."""
    purchase_ids = [pid for pid in dict.fromkeys(purchase_ids) if pid is not None]
    if not purchase_ids:
        return {}

    purchases = (await db.execute(
        select(Purchase.id, Purchase.contractor_id).where(Purchase.id.in_(purchase_ids))
    )).all()
    contractor_ids = {r.contractor_id for r in purchases if r.contractor_id is not None}
    contractor_names: dict[int, str] = {}
    if contractor_ids:
        contractor_names = {
            c.id: c.name for c in (await db.execute(
                select(Contractor).where(Contractor.id.in_(contractor_ids))
            )).scalars().all()
        }

    items = (await db.execute(
        select(
            PurchaseItem.purchase_id, PurchaseItem.item_name, PurchaseItem.tz_description,
            PurchaseItem.contractor_name, PurchaseItem.product_id,
        ).where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).all()
    product_ids = {r.product_id for r in items if r.product_id is not None}
    product_names: dict[int, str] = {}
    product_descriptions: dict[int, str] = {}
    if product_ids:
        for p in (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all():
            product_names[p.id] = p.name
            if p.description:
                product_descriptions[p.id] = p.description

    items_by_purchase: dict[int, list] = {}
    fallback_contractor_name: dict[int, str] = {}
    for r in items:
        items_by_purchase.setdefault(r.purchase_id, []).append(r)
        if r.contractor_name and r.purchase_id not in fallback_contractor_name:
            fallback_contractor_name[r.purchase_id] = r.contractor_name

    result: dict[int, dict] = {}
    for pid, contractor_id in ((r.id, r.contractor_id) for r in purchases):
        supplier: Optional[str] = contractor_names.get(contractor_id) if contractor_id else None
        if not supplier:
            supplier = fallback_contractor_name.get(pid)

        parts: list[str] = []
        for it in items_by_purchase.get(pid, []):
            if it.item_name:
                parts.append(it.item_name)
            description = it.tz_description or (product_descriptions.get(it.product_id) if it.product_id else None)
            if description:
                parts.append(description)
            if it.product_id and product_names.get(it.product_id):
                parts.append(product_names[it.product_id])
        result[pid] = {
            "items_text": " · ".join(dict.fromkeys(p.strip() for p in parts if p and p.strip())),
            "supplier": supplier,
        }
    return result
