"""«Рамочная голова» для договоров, созданных прямо в реестре «Договоры».

Вынесено из app/routers/contracts.py (Правило №5, резка волны 2026-09-08).
Тот же префикс /api/contracts, путь POST "/{contract_id}/approval-purchase"
на сегмент длиннее catch-all PUT/DELETE "/{cid}" ядра — порядок регистрации
относительно contracts.router не важен (см. комментарий в routes.py).

_build_approval_purchase_fields ре-экспортируется из app.routers.contracts —
tests/test_contract_approval_purchase.py импортирует его оттуда напрямую.
"""
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.routers.purchase_budget import FRAMEWORK_TYPES, _assign_framework_seq

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def _build_approval_purchase_fields(
    contract: Contract, assigned_user_id: int, responsible_person: Optional[str] = None
) -> dict:
    """Собирает kwargs для Purchase() — «рамочная голова» из уже сохранённого
    Contract. Чистая функция без обращений к БД — вынесена отдельно, чтобы
    маппинг полей был юнит-тестируем без живой сессии
    (см. tests/test_contract_approval_purchase.py).

    Пустой contract.number (falsy) сознательно передаётся как None, а не
    подменяется — при первом формировании документа сработает уже готовая
    логика присвоения временного номера «ВРЕМ-…»
    (is_framework_head + _generate_temp_contract_number в purchases.py).

    responsible_person — ФИО текущего пользователя (если не пусто):
    предзаполняет «Ответственного исполнителя» листа согласования, чтобы у
    свежесозданной рамочной головы клетка не оставалась пустой.
    """
    fields = dict(
        contract_id=contract.id,
        contractor_id=contract.contractor_id,
        subsidy_id=contract.subsidy_id,
        subject=contract.subject,
        contract_number=(contract.number or None),
        contract_date=contract.date,
        contract_price=contract.max_amount,
        purchase_contract_type=contract.contract_type,
        purchase_method=contract.purchase_method,
        parent_purchase_id=None,
        # Начальный статус — как у обычной новой закупки (Purchase.status /
        # PurchaseCreate.status default в purchases.py).
        status="wishes",
        # Без явного владельца закупка невидима для рядового автора в списке
        # (list_purchases фильтрует по visible_user_ids) — как в create_purchase.
        assigned_user_id=assigned_user_id,
    )
    if responsible_person:
        fields["responsible_person"] = responsible_person
    return fields


@router.post("/{contract_id}/approval-purchase")
async def get_or_create_approval_purchase(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('contracts')),
):
    """Найти или создать «рамочную голову» — Purchase, привязанную к этому
    рамочному договору — через которую уже доступны согласование
    необходимости, печать договора и листа согласования.

    Диагноз (2026-09-01): реестр «Договоры» (Contract) — отдельная сущность
    без своего согласования/документооборота; вся эта машинерия живёт на
    Purchase (см. /api/purchases/{pid}/documents/{doc_type},
    purchase_transitions.py). У РАМОЧНЫХ договоров, созданных прямо в реестре
    «Договоры», закупка не заводится автоматически — поэтому кнопок
    согласования/печати у них нет. Этот эндпоинт закрывает разрыв, не
    дублируя генерацию документов здесь.

    Идемпотентно: если у договора уже есть привязанная рамочная голова —
    возвращает её id, ничего не создавая. Проверка «голова ли это» —
    is_framework_head() (purchases.py), единый источник истины, чтобы эта
    проверка не разъехалась с documents.py / purchase_transitions.py.
    """
    # Локальный импорт: purchases.py импортирует ensure_contract_linked ИЗ
    # app.routers.contracts на уровне модуля — импорт is_framework_head сверху
    # дал бы циклический импорт при старте приложения.
    from app.routers.purchases import is_framework_head

    contract = (await db.execute(select(Contract).where(Contract.id == contract_id))).scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Договор не найден")
    if contract.contract_type not in FRAMEWORK_TYPES:
        raise HTTPException(400, "Согласование и документы через договор доступны только для рамочных договоров")

    linked = (await db.execute(
        select(Purchase).where(Purchase.contract_id == contract_id).order_by(Purchase.id.asc())
    )).scalars().all()
    existing = next((p for p in linked if is_framework_head(p)), None)
    if existing:
        return {"purchase_id": existing.id, "created": False}

    p = Purchase(**_build_approval_purchase_fields(
        contract, current_user.id, responsible_person=(current_user.full_name or None)
    ))
    db.add(p)
    await db.flush()  # get p.id

    if not p.registry_number:
        p.registry_number = f"РЕЕ-{date_type.today().year}-{p.id:05d}"
    if not p.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        p.purchase_number = max_result.scalar() + 1

    await _assign_framework_seq(p, db)

    # Владелец (2026-09-03), дословно: «просил же сделать по аналогии с
    # Заявкой. То есть выбирают при создании рамочного договора, надо
    # выбрать, кто будет согласовывать то, что этот договор вообще нужен» —
    # раньше здесь (2026-09-02) цепочка согласующих строилась АВТОМАТИЧЕСКИ от
    # руководителя организации, никого не спрашивая. Теперь голова заводится
    # БЕЗ согласующих (approval_status остаётся None) — автор сам добавляет их
    # вручную (POST /purchases/{pid}/approvals/add — доступно всем ролям, как
    # у заявки) или явно жмёт «Построить цепочку»
    # (POST /purchases/{pid}/approvers/cascade, см. purchases.py::
    # _build_framework_chain_approvals — функция осталась, вызывается только
    # по явному действию).
    await db.commit()
    return {"purchase_id": p.id, "created": True}
