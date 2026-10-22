"""ПРАВИЛО №6 (один источник): «договор относится к субсидии/её организации».

Жалоба владельца (заявка №209, 22.10.2026): согласующий открывает заявку по
субсидии ХРО_2026 (организация «ХРО ВСКС») — в поле «Договор (рамочный)»
видны ВСЕ рамочные договоры аккаунта, включая договоры других организаций.
Должны быть видны (и доступны к сохранению) только рамочные договоры
субсидии заявки и других субсидий ТОЙ ЖЕ организации.

Единственный источник формулы группы договора (1/2/3) — contract_group()
ниже. app/routers/contracts.py::list_contracts использует её же (раньше
логика была инлайн там, вынесена без изменения поведения). Единственная
точка проверки «можно ли записать этот договор в заявку конкретной субсидии»
— ensure_wish_contract_allowed(); вызывается из трёх мест записи
Wish.contract_id (app/routers/wishes.py::create_wish/update_wish,
app/routers/wish_transitions.py::patch_wish_execution) — не копировать.

Окно выбора рамочного договора в ЗАКУПКЕ (владелец, 2026-09-30) намеренно
показывает ВСЕ 3 группы — это другое решение, этот модуль его не трогает.
"""
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException


def contract_group(
    contract_id: int,
    contract_subsidy_id: Optional[int],
    contract_subsidy_org_id: Optional[int],
    prefer_subsidy_id: Optional[int],
    prefer_org_id: Optional[int],
    extra_linked_contract_ids: Iterable[int],
) -> int:
    """1 — субсидия prefer_subsidy_id (свой subsidy_id ИЛИ доп. привязка
    ContractSubsidy), 2 — другая субсидия ТОЙ ЖЕ организации, 3 — остальное.

    Ровно формула, что была инлайн в contracts.py::list_contracts (строки
    293-299 до вынесения) — поведение не меняется.
    """
    if contract_subsidy_id == prefer_subsidy_id or contract_id in extra_linked_contract_ids:
        return 1
    if prefer_org_id is not None and contract_subsidy_org_id == prefer_org_id:
        return 2
    return 3


MSG_CONTRACT_NOT_FOUND = "Договор не найден"
MSG_CONTRACT_NOT_FRAMEWORK = (
    "Договор {number} не рамочный — в заявке можно выбрать только рамочный договор"
)
MSG_NO_SUBSIDY = "Сначала выберите субсидию заявки"
MSG_WRONG_ORG = (
    "Договор {number} заключён по другой организации — в заявке по субсидии "
    "«{subsidy_name}» можно выбрать только рамочные договоры её организации"
)


async def ensure_wish_contract_allowed(
    db: AsyncSession,
    contract_id: Optional[int],
    subsidy_id: Optional[int],
) -> None:
    """Бросает HTTPException(400/404), если contract_id нельзя записать в
    Wish.contract_id заявки с данной субсидией. contract_id=None — пропуск
    (снятие договора всегда разрешено)."""
    if contract_id is None:
        return

    from app.models.contract import Contract
    from app.models.contract_subsidy import ContractSubsidy
    from app.models.subsidy import Subsidy
    from app.routers.purchase_budget import FRAMEWORK_TYPES
    from sqlalchemy import select

    contract = await db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=MSG_CONTRACT_NOT_FOUND)

    if contract.contract_type not in FRAMEWORK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=MSG_CONTRACT_NOT_FRAMEWORK.format(number=contract.number or contract.id),
        )

    if subsidy_id is None:
        raise HTTPException(status_code=400, detail=MSG_NO_SUBSIDY)

    prefer_subsidy = await db.get(Subsidy, subsidy_id)
    prefer_org_id = prefer_subsidy.org_id if prefer_subsidy else None

    contract_subsidy_org_id: Optional[int] = None
    if contract.subsidy_id is not None:
        contract_subsidy = await db.get(Subsidy, contract.subsidy_id)
        contract_subsidy_org_id = contract_subsidy.org_id if contract_subsidy else None

    extra_linked_contract_ids = set((await db.execute(
        select(ContractSubsidy.contract_id).where(ContractSubsidy.subsidy_id == subsidy_id)
    )).scalars().all())

    group = contract_group(
        contract_id=contract.id,
        contract_subsidy_id=contract.subsidy_id,
        contract_subsidy_org_id=contract_subsidy_org_id,
        prefer_subsidy_id=subsidy_id,
        prefer_org_id=prefer_org_id,
        extra_linked_contract_ids=extra_linked_contract_ids,
    )
    if group == 3:
        raise HTTPException(
            status_code=400,
            detail=MSG_WRONG_ORG.format(
                number=contract.number or contract.id,
                subsidy_name=prefer_subsidy.name if prefer_subsidy else subsidy_id,
            ),
        )
