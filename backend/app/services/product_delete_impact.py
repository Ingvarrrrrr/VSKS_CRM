"""Единственный источник подсчёта зависимостей товара перед удалением
(Правило №6) — используется DELETE /api/products/{id} для гейта на 409.
Строится по образцу app/services/subsidy_delete_impact.py (та же форма
ответа: группа -> {count, items[]}, счётчик всегда точный, items обрезаны
MAX_LISTED_ITEMS).

Повод (жалоба владельца, 2026-09-29): DELETE /api/products/4280 падал 500
ForeignKeyViolationError — товар стоял в позиции закупки РЕЕ-2026-00921
(purchase_items.product_id, FK без ondelete — единственный FK на products,
который реально блокирует на уровне БД). У остальных FK на products стоит
ON DELETE SET NULL/CASCADE, но для бизнес-документов (позиция закупки,
заявки, договора, КП) это означает тихую потерю связи с товаром при
удалении — тоже нежелательно, поэтому блокируем на уровне приложения ДО
удаления, не полагаясь на поведение БД.

Классификация FK на products (проверено `pg_constraint` в БД, 2026-09-29):
  - purchase_items.product_id              (confdeltype='a', NO ACTION)   -> бизнес-документ, БЛОКИРУЕТ
  - contract_items.product_id              (confdeltype='n', SET NULL)    -> бизнес-документ, БЛОКИРУЕТ (в приложении)
  - wish_items.product_id                  (confdeltype='n', SET NULL)    -> бизнес-документ, БЛОКИРУЕТ (в приложении)
  - commercial_request_offers.product_id   (confdeltype='n', SET NULL)    -> бизнес-документ (КП), БЛОКИРУЕТ (в приложении)
  - product_price_history.product_id       (confdeltype='c', CASCADE)     -> собственные данные товара, удаляются вместе с ним
  - supplier_products.product_id           (confdeltype='c', CASCADE)     -> собственные данные товара (привязка к поставщику), удаляются вместе с ним
  - product_purchase_categories.product_id (confdeltype='c', CASCADE)     -> собственные данные товара (категории), удаляются вместе с ним
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_request import CommercialRequest, CommercialRequestOffer
from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem

MAX_LISTED_ITEMS = 50

GROUP_LABELS: dict[str, str] = {
    "purchases": "позициях закупок",
    "wishes": "позициях заявок",
    "contracts": "позициях договоров",
    "commercial_requests": "коммерческих предложениях",
}


async def get_product_delete_impact(db: AsyncSession, product_id: int) -> dict:
    """Возвращает счётчики бизнес-документов, ссылающихся на товар, разбитые
    на группы purchases/wishes/contracts/commercial_requests. Каждая группа —
    {"count": int, "items": [{id, number, name, status, route}, ...]}
    (items ограничен MAX_LISTED_ITEMS, count — точный, считает КОЛИЧЕСТВО
    РОДИТЕЛЬСКИХ ДОКУМЕНТОВ, а не позиций — если товар стоит в двух позициях
    одной закупки, это одна строка списка с полем item_count)."""

    purchase_rows = (await db.execute(
        select(
            Purchase.id, Purchase.purchase_number, Purchase.order_number,
            Purchase.item_name, Purchase.subject, Purchase.status,
            func.count(PurchaseItem.id).label("item_count"),
        )
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.product_id == product_id)
        .group_by(Purchase.id)
        .order_by(Purchase.id.desc())
    )).all()

    wish_rows = (await db.execute(
        select(
            Wish.id, Wish.title, Wish.status,
            func.count(WishItem.id).label("item_count"),
        )
        .join(WishItem, WishItem.wish_id == Wish.id)
        .where(WishItem.product_id == product_id)
        .group_by(Wish.id)
        .order_by(Wish.id.desc())
    )).all()

    contract_rows = (await db.execute(
        select(
            Contract.id, Contract.number, Contract.subject, Contract.status,
            func.count(ContractItem.id).label("item_count"),
        )
        .join(ContractItem, ContractItem.contract_id == Contract.id)
        .where(ContractItem.product_id == product_id)
        .group_by(Contract.id)
        .order_by(Contract.id.desc())
    )).all()

    cr_rows = (await db.execute(
        select(
            CommercialRequest.id, CommercialRequest.purchase_id, CommercialRequest.subject,
            CommercialRequest.status,
            func.count(CommercialRequestOffer.id).label("item_count"),
        )
        .join(CommercialRequestOffer, CommercialRequestOffer.request_id == CommercialRequest.id)
        .where(CommercialRequestOffer.product_id == product_id)
        .group_by(CommercialRequest.id)
        .order_by(CommercialRequest.id.desc())
    )).all()

    buckets: dict[str, list[dict]] = {
        "purchases": [], "wishes": [], "contracts": [], "commercial_requests": [],
    }
    for p in purchase_rows:
        number = p.purchase_number if p.purchase_number is not None else p.order_number
        buckets["purchases"].append({
            "id": p.id,
            "number": number,
            "name": p.item_name or p.subject,
            "status": p.status,
            "item_count": p.item_count,
            "route": f"/orders/{p.id}",
        })
    for w in wish_rows:
        buckets["wishes"].append({
            "id": w.id,
            "number": w.id,
            "name": w.title,
            "status": w.status,
            "item_count": w.item_count,
            "route": f"/wishes?open={w.id}",
        })
    for c in contract_rows:
        buckets["contracts"].append({
            "id": c.id,
            "number": c.number,
            "name": c.subject,
            "status": c.status,
            "item_count": c.item_count,
            "route": "/contracts",
        })
    for r in cr_rows:
        buckets["commercial_requests"].append({
            "id": r.id,
            "number": r.id,
            "name": r.subject,
            "status": r.status,
            "item_count": r.item_count,
            # КП живёт на карточке своей закупки — открываем её.
            "route": f"/orders/{r.purchase_id}" if r.purchase_id else "/commercial-requests",
        })

    result: dict = {}
    for key, rows in buckets.items():
        result[key] = {"count": len(rows), "items": rows[:MAX_LISTED_ITEMS]}
    return result


def has_blocking_dependents(impact: dict) -> bool:
    return any(impact[key]["count"] > 0 for key in GROUP_LABELS)


def _describe_item(key: str, item: dict) -> str:
    if key == "purchases":
        return f"закупка {item['number'] or ('№' + str(item['id']))} («{item['name'] or '—'}»)"
    if key == "wishes":
        return f"заявка №{item['id']} («{item['name'] or '—'}»)"
    if key == "contracts":
        return f"договор №{item['number'] or item['id']} («{item['name'] or '—'}»)"
    if key == "commercial_requests":
        return f"КП №{item['id']} («{item['name'] or '—'}»)"
    return f"{key} #{item['id']}"


def format_delete_block_message(product_name: str, impact: dict) -> Optional[str]:
    """Единственный источник текста 409 при удалении товара — фронт (диалог
    удаления товара) строит сообщение из этих же данных, не дублирует
    формулировку (Правило №6)."""
    total_positions = sum(
        sum(it["item_count"] for it in impact[key]["items"]) for key in GROUP_LABELS
    )
    if total_positions == 0:
        return None
    examples = []
    for key in GROUP_LABELS:
        for it in impact[key]["items"][:5]:
            examples.append(_describe_item(key, it))
    examples_text = ", ".join(examples[:5])
    more = len(examples) - 5
    suffix = f" и ещё {more}" if more > 0 else ""
    word = "позиции" if total_positions == 1 else "позициях"
    return (
        f"Товар «{product_name}» нельзя удалить: он указан в {total_positions} {word} — "
        f"{examples_text}{suffix}. Уберите товар из этих позиций или замените другим, затем удалите."
    )
