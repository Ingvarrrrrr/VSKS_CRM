"""Единый источник контрагента позиции закупки (PurchaseItem) и заявки (Wish).

ПРАВИЛО №6 (один показатель — один источник истины). Контрагент позиции
хранился ТРОЙНО: contractor_id (FK на Contractor) + contractor_inn +
contractor_name (текст, для случая «контрагента ещё нет в справочнике»).
Текст жил независимо от FK — писался и читался в куче мест по отдельности
(purchases.py PUT/PATCH, purchase_items_edit split, wish_distribution,
purchase_receipts, purchase_import_parser, backfills 26-CC/26-BB/26-W),
из-за чего FK и текст расходились (текст от старого/чужого контрагента
оставался висеть рядом с новой привязкой).

Инвариант группы D5 (план утверждён 2026-09-07):
    - contractor_id задан  → contractor_id/inn/name ВСЕГДА читаются из
      Contractor; текстовые колонки на самой сущности ОЧИЩАЮТСЯ (NULL) —
      это только FK, копии рядом не хранится.
    - contractor_id не задан → текстовые колонки — единственный источник
      (контрагента ещё нет в справочнике).

item_contractor() — единственная точка ЧТЕНИЯ (используется и для
PurchaseItem, и для Wish — у Wish нет колонки contractor_inn, функция это
учитывает через hasattr и просто не кладёт ключ 'contractor_inn' в результат).

set_item_contractor() — единственная точка ЗАПИСИ. Все писатели (роутеры,
сервисы, бэкфиллы) обязаны обновлять contractor_id/contractor_inn/
contractor_name ТОЛЬКО через неё — второй копии логики не заводить.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def item_contractor(
    entity: Any,
    contractor: Any = None,
    *,
    name_map: Optional[dict] = None,
    inn_map: Optional[dict] = None,
) -> dict:
    """Читает контрагента `entity` (PurchaseItem или Wish) по инварианту D5.

    entity — ORM-объект с колонками contractor_id/contractor_name (и, для
    PurchaseItem, contractor_inn).

    Для bulk-путей (список закупок/позиций) не делать SELECT на каждую
    строку — передавать ЛИБО уже загруженный `contractor` (когда он и так
    под рукой, например relationship уже selectinload'нута и entity.contractor_id
    совпадает с contractor.id), ЛИБО заранее одним запросом собранные карты
    `name_map`/`inn_map` ({contractor_id: name}/{contractor_id: inn}) — тот же
    приём, что уже применяется для шапки закупки (app.routers.purchases:
    `contractors`/`contractor_inns`, один SELECT на всю страницу).

    Возвращает dict с ключами contractor_id, contractor_name, source
    ('fk'|'fk_unloaded'|'text') и, если у entity есть колонка contractor_inn,
    ключом contractor_inn.
    """
    has_inn_col = hasattr(entity, "contractor_inn")
    cid = entity.contractor_id

    if cid:
        name = None
        inn = None
        source = "fk_unloaded"
        if contractor is not None and getattr(contractor, "id", None) == cid:
            name = contractor.name
            inn = getattr(contractor, "inn", None)
            source = "fk"
        else:
            if name_map is not None and cid in name_map:
                name = name_map.get(cid)
                source = "fk"
            if inn_map is not None and cid in inn_map:
                inn = inn_map.get(cid)
                source = "fk"
        result = {"contractor_id": cid, "contractor_name": name, "source": source}
        if has_inn_col:
            result["contractor_inn"] = inn
        return result

    result = {
        "contractor_id": None,
        "contractor_name": getattr(entity, "contractor_name", None),
        "source": "text",
    }
    if has_inn_col:
        result["contractor_inn"] = getattr(entity, "contractor_inn", None)
    return result


def set_item_contractor(
    entity: Any,
    *,
    contractor: Any = None,
    contractor_id: Optional[int] = None,
    inn: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """Пишет контрагента `entity` (PurchaseItem или Wish) по инварианту D5.

    Ровно три сценария вызова:
      - `contractor=<Contractor>` передан → FK на него, текстовые колонки
        обнуляются. Если вместе с этим переданы inn/name и они НЕ совпадают
        с контрагентом — текст ИГНОРИРУЕТСЯ (warning в лог), а не молча
        подменяет привязку.
      - `contractor_id=<int>` передан (объект контрагента под рукой нет —
        например bulk-путь, где id уже точно резолвлен по ИНН) → FK на него,
        текстовые колонки обнуляются безусловно (mismatch-проверка невозможна
        без объекта — считается, что вызывающий уже сверил инн сам).
      - ни contractor, ни contractor_id не переданы → FK снимается (NULL),
        пишется голый текст inn/name (единственный источник, «контрагента
        ещё нет в справочнике»).
    """
    has_inn_col = hasattr(entity, "contractor_inn")

    if contractor is not None:
        c_inn = getattr(contractor, "inn", None)
        c_name = getattr(contractor, "name", None)
        if (inn and c_inn and inn != c_inn) or (name and c_name and name != c_name):
            logger.warning(
                "set_item_contractor: переданный текст (inn=%r, name=%r) не совпадает "
                "с контрагентом id=%s (inn=%r, name=%r) — текст проигнорирован, привязка "
                "по FK остаётся источником истины",
                inn, name, contractor.id, c_inn, c_name,
            )
        entity.contractor_id = contractor.id
        if has_inn_col:
            entity.contractor_inn = None
        entity.contractor_name = None
        return

    if contractor_id is not None:
        entity.contractor_id = contractor_id
        if has_inn_col:
            entity.contractor_inn = None
        entity.contractor_name = None
        return

    entity.contractor_id = None
    if has_inn_col:
        entity.contractor_inn = inn
    entity.contractor_name = name


def item_contractor_fk_values(contractor_id: int) -> dict:
    """То же самое обнуление текста, что и set_item_contractor(contractor_id=...),
    но в виде dict колонок — для Core `update().values(...)` (bulk-путь без
    загрузки ORM-объектов, см. startup/backfills.py Phase 26-W). Единственная
    вторая форма записи — держать её здесь же, не дублировать в бэкфилле.
    """
    return {"contractor_id": contractor_id, "contractor_inn": None, "contractor_name": None}
