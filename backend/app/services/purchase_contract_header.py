"""Единый источник истины для «шапки договора» закупки (ПРАВИЛО №6, группа D7).

Контекст: `purchases.contract_number/contract_date/purchase_contract_type/
contractor_id` — денормализованный кэш договора на закупке (нужен для
закупок БЕЗ contract_id — чек/авансовый/ручной ввод номера — и как
исторический fallback). Пока это были единственные значения, читатели и
писатель (app.routers.purchases._sync_purchase_from_contract) регулярно
расходились — четыре фазы бэкфилла (26-j-1, 26-k-2, 26-lll, 26-mmm) чинили
одно и то же расхождение.

Решение координатора (2026-09-07, группа D7): когда у закупки ЕСТЬ
contract_id и связанный Contract загружен — действующее значение ЧИТАЕТСЯ
из Contract, а не из кэша на закупке. Кэш остаётся только (а) источником для
закупок без contract_id и (б) fallback'ом на отдельное поле, если у самого
Contract это поле почему-то пусто (лог warning — сигнал, что бэкфилл ещё не
прошёл или Contract создан вручную без этого поля).

Единственный писатель кэша — app.routers.purchases._sync_purchase_from_contract
(и миграция-бэкфилл на нём же основанная). Этот модуль НИЧЕГО не пишет —
только читает и решает, какое значение действующее.
"""
from dataclasses import dataclass
from datetime import date as date_type
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# Поля шапки договора закупки: при заданном contract_id источник — Contract.
# Единый список для читателя (contract_header ниже) И для писателей
# (PUT/PATCH /api/purchases/{id} в routers/purchases.py игнорируют эти поля
# во входящем payload, когда contract_id уже задан — см. contract_fields_ignored).
CONTRACT_HEADER_FIELDS: tuple[str, ...] = (
    "contract_number", "contract_date", "purchase_contract_type", "contractor_id",
)


@dataclass(frozen=True)
class PurchaseContractHeader:
    contract_number: Optional[str]
    contract_date: Optional[date_type]
    purchase_contract_type: Optional[str]
    contractor_id: Optional[int]
    # "contract" — значения взяты из связанного Contract (с возможным
    # fallback на кэш по отдельным пустым полям); "purchase" — у закупки нет
    # contract_id (или Contract не передан вызывающим) — значения из кэша.
    source: str


def contract_header(p, contract=None) -> PurchaseContractHeader:
    """Действующая шапка договора закупки `p`.

    `contract` — уже загруженный `app.models.contract.Contract` с
    `contract.id == p.contract_id` (см. Purchase.contract relationship,
    selectinload на вызывающей стороне — без N+1). Если он не передан или не
    соответствует p.contract_id — считаем как закупку без договора (кэш).
    """
    if p.contract_id and contract is not None and contract.id == p.contract_id:
        number = contract.number
        if not number and p.contract_number:
            logger.warning(
                "purchase %s: contract %s has empty number, falling back to cached contract_number",
                p.id, contract.id,
            )
            number = p.contract_number

        c_date = contract.date
        if not c_date and p.contract_date:
            logger.warning(
                "purchase %s: contract %s has empty date, falling back to cached contract_date",
                p.id, contract.id,
            )
            c_date = p.contract_date

        c_type = contract.contract_type
        if not c_type and p.purchase_contract_type:
            logger.warning(
                "purchase %s: contract %s has empty contract_type, falling back to cached purchase_contract_type",
                p.id, contract.id,
            )
            c_type = p.purchase_contract_type

        contractor_id = contract.contractor_id
        if contractor_id is None:
            contractor_id = p.contractor_id

        return PurchaseContractHeader(number, c_date, c_type, contractor_id, "contract")

    return PurchaseContractHeader(
        p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id, "purchase",
    )
