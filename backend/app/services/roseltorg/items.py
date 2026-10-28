"""Сборка позиций лота для POST /notice/lot/{noticeLotId}/items.

ПРАВИЛО №6: строки берём ИЗ ТОГО ЖЕ расчёта, что и xlsx «Позиции по лоту»
(documents/roseltorg_package.py) — build_tz_rows + _purchase_item_doc_values
(documents/contexts.py). Здесь нет второго параллельного набора сырых
quantity/unit_price/description/name/unit, только маппинг готовых значений
в тело API площадки (okeiId/isArbitraryUnit/commodityItemPrice и т.п.).
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.documents.contexts import _require_tz_duplicates_resolved_for_doc, _purchase_item_doc_values
from app.services.tz_items import build_tz_rows

from .okei import okei_for_unit

NAME_MAX_LEN = 250
DESCRIPTION_MAX_LEN = 1000


async def load_purchase_item_rows(db: AsyncSession, purchase_id: int) -> tuple[Purchase | None, list[dict]]:
    """Возвращает (purchase, raw_rows) — raw_rows — те же сырые значения, что
    кладутся в xlsx (name/quantity/unit/unit_price/description), без API-обвязки.
    """
    result = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items).selectinload(PurchaseItem.product))
        .where(Purchase.id == purchase_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        return None, []

    _require_tz_duplicates_resolved_for_doc(p)

    _tz = build_tz_rows(getattr(p, "items", None) or [], getattr(p, "tz_duplicate_decisions", None))

    rows: list[dict] = []
    for row in _tz["rows"]:
        item = row["item"]
        raw = _purchase_item_doc_values(p, item, row)
        rows.append(raw)
    return p, rows


def build_roseltorg_item_payloads(
    rows: list[dict],
    okpd2_code: str | None = None,
    okpd2_name: str | None = None,
    no_nmcd: bool = False,
) -> list[dict]:
    """Сырые строки (см. load_purchase_item_rows) → тела POST items API.

    okpd2_code/okpd2_name — ЕДИНЫЙ на всю закупку код (payload["okpd2_code"],
    как у Фабриканта, ОКПД2 на уровне позиции в системе не хранится, см.
    roseltorg_package.py docstring) — тот же источник, не второй расчёт.

    Живая проверка владельцем на черновике 303879 (28.10.2026): ключ
    okpd2Code ОБЯЗАН присутствовать в теле — с "" или null позиция создаётся
    (200, success:true); ошибка «код … не найден» была ТОЛЬКО когда ключа
    не было вовсе (площадка подставляла свой дефолт). Поэтому ключ шлём
    ВСЕГДА, значение — код закупки, иначе пустая строка (не выдумываем ОКПД2,
    владелец: в кабинете его вручную тоже не ставят).

    `no_nmcd` — то же поле, что у Фабриканта (payload["no_nmcd"], ПРАВИЛО
    №6) — при «Без НМЦД» цены позиций тоже не публикуются: commodityItemPrice
    не шлём вовсе (не "0" — по аналогии с initialSum лота, живая проверка).
    """
    items_payload: list[dict] = []
    for idx, raw in enumerate(rows, start=1):
        name = str(raw.get("name") or "").strip()[:NAME_MAX_LEN]
        if not name:
            continue
        description = str(raw.get("description") or "").strip()[:DESCRIPTION_MAX_LEN]
        unit_name = str(raw.get("unit") or "").strip()
        okei_id = okei_for_unit(unit_name)

        quantity = raw.get("quantity") or 0
        unit_price = raw.get("unit_price") or 0

        data: dict = {
            "name": name,
            "quantity": str(quantity),
            "description": description,
            "ordinalNumber": idx,
        }
        if not no_nmcd:
            data["commodityItemPrice"] = str(unit_price)
        if okei_id:
            data["okeiId"] = okei_id
            data["unit"] = unit_name or "шт"
            data["isArbitraryUnit"] = False
        else:
            data["isArbitraryUnit"] = True
            data["arbitraryUnit"] = unit_name or "усл. ед."
            data["unit"] = unit_name or "усл. ед."

        # Ключ присутствует всегда (см. докстринг выше) — пустая строка,
        # если код закупки не задан.
        data["okpd2Code"] = okpd2_code or ""
        data["okpd2Name"] = okpd2_name or ""

        items_payload.append(data)
    return items_payload
