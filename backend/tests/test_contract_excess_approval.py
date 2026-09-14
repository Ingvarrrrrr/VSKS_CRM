"""Волна 4 п.18 (владелец, дословно): «если цена в договоре и количество, либо
цена, либо количество в договоре больше, чем того, что было в первоначальной
заявке, потом в закупке... не должны пропускать большую цену без
дополнительного согласования, иначе будут проблемы».

Проверяет app.services.contract_excess_approval — сравнение ОДНОЙ договорной
позиции (ContractItem-подобный check-объект, см. contract_items.py) с её
позицией закупки/ТЗ (PurchaseItem) по количеству/цене за единицу/сумме
ОТДЕЛЬНО, и переиспользование СУЩЕСТВУЮЩЕГО механизма согласования
PlanExcessApproval (та же таблица/уполномоченные, что и у превышения плана
ФЭО — см. app.routers.plan_excess).

Фикстуры/стиль — по образцу test_tz_over_plan_goes_to_approval.py
(_make_subsidy/_make_category/_make_plan_excess_approver) и
test_planned_item_unit_price.py (прямой вызов сервисной функции с реальной
db_session, без HTTP-клиента — избегаем сложностей auth/require_tab там, где
дело не в роутере, а в самой формуле сравнения и согласовании).

Известный флейк (см. tests/conftest.py, НЕ чинить здесь): async-тесты падают
«attached to a different loop» при запуске пачкой — гонять файл по ОДНОМУ
тесту (pytest tests/test_contract_excess_approval.py::<name>).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.plan_excess_approval import PlanExcessApproval
from app.schemas.schemas import ContractItemCreate
from app.services.contract_excess_approval import enforce_contract_excess_approval


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"Contract-Excess-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=Decimal("1000000")):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name="Тестовая категория (превышение договора над закупкой)",
        budget=budget,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase_item(db_session, purchase_id, feo_category_id,
                               quantity=Decimal("2"), unit_price=Decimal("100"),
                               total_price=Decimal("200"), name="Товар А"):
    from app.models.purchase_item import PurchaseItem
    pi = PurchaseItem(
        purchase_id=purchase_id,
        item_name=name,
        quantity=quantity,
        unit="шт",
        unit_price=unit_price,
        total_price=total_price,
        feo_category_id=feo_category_id,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(pi)
    return pi


async def _make_plan_excess_approver(db_session, test_org, make_user):
    """Пользователь с реальным правом 'plan_excess.decide' в test_org —
    точечный грант (UserOrgPermissionOverride), не общая RolePermission (см.
    ту же оговорку в test_tz_over_plan_goes_to_approval.py — дев-БД уже
    содержит RolePermission('manager', 'plan_excess.decide', granted=False),
    вторая строка той же роли упала бы в unique-constraint)."""
    from app.models.user_org_access import UserOrgAccess
    from app.models.permission import UserOrgPermissionOverride

    approver = await make_user(role="manager", org_id=test_org.id)
    uoa = UserOrgAccess(user_id=approver.id, org_id=test_org.id, role="manager")
    db_session.add(uoa)
    await db_session.commit()
    await db_session.refresh(uoa)
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="plan_excess.decide", granted=True,
    ))
    await db_session.commit()
    return approver


async def _get_409(coro):
    from fastapi import HTTPException
    try:
        await coro
    except HTTPException as e:
        return e
    raise AssertionError("Ожидался HTTPException(409), исключение не брошено")


@pytest.mark.asyncio
async def test_price_higher_requires_approval(
    db_session, test_org, test_admin_user, make_user, make_purchase,
):
    """Цена за единицу в договоре выше, чем в закупке — 409, регистрируется
    pending PlanExcessApproval по категории."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    p = await make_purchase(subsidy_id=subsidy.id, feo_category_id=cat.id)
    pi = await _make_purchase_item(
        db_session, p.id, cat.id,
        quantity=Decimal("2"), unit_price=Decimal("100"), total_price=Decimal("200"),
    )
    contract_item = ContractItemCreate(
        source_item_id=pi.id, name="Товар А",
        quantity=Decimal("2"), unit_price=Decimal("150"), total=Decimal("300"),
    )

    e = await _get_409(enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: цена выше",
    ))
    detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
    assert detail.get("code") == "CONTRACT_EXCESS_OVER_PURCHASE_PENDING", detail
    assert "цена за единицу" in detail.get("message", "")

    approvals = (await db_session.execute(
        select(PlanExcessApproval).where(PlanExcessApproval.feo_category_id == cat.id)
    )).scalars().all()
    assert approvals, "Запрос на согласование превышения договора над закупкой не создан"
    assert any(a.status == "pending" for a in approvals)


@pytest.mark.asyncio
async def test_quantity_higher_requires_approval(
    db_session, test_org, test_admin_user, make_user, make_purchase,
):
    """Количество в договоре выше, чем в закупке — 409."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    p = await make_purchase(subsidy_id=subsidy.id, feo_category_id=cat.id)
    pi = await _make_purchase_item(
        db_session, p.id, cat.id,
        quantity=Decimal("2"), unit_price=Decimal("100"), total_price=Decimal("200"),
    )
    contract_item = ContractItemCreate(
        source_item_id=pi.id, name="Товар А",
        quantity=Decimal("3"), unit_price=Decimal("100"), total=Decimal("300"),
    )

    e = await _get_409(enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: количество выше",
    ))
    detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
    assert detail.get("code") == "CONTRACT_EXCESS_OVER_PURCHASE_PENDING", detail
    assert "количество" in detail.get("message", "")


@pytest.mark.asyncio
async def test_sum_higher_requires_approval(
    db_session, test_org, test_admin_user, make_user, make_purchase,
):
    """Сумма в договоре выше, чем в закупке, ХОТЯ количество и цена за единицу
    номинально совпадают (сумма введена независимо, напр. с округлением) — 409."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    p = await make_purchase(subsidy_id=subsidy.id, feo_category_id=cat.id)
    pi = await _make_purchase_item(
        db_session, p.id, cat.id,
        quantity=Decimal("2"), unit_price=Decimal("100"), total_price=Decimal("200"),
    )
    contract_item = ContractItemCreate(
        source_item_id=pi.id, name="Товар А",
        quantity=Decimal("2"), unit_price=Decimal("100"), total=Decimal("250"),
    )

    e = await _get_409(enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: сумма выше",
    ))
    detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
    assert detail.get("code") == "CONTRACT_EXCESS_OVER_PURCHASE_PENDING", detail
    assert "сумма" in detail.get("message", "")


@pytest.mark.asyncio
async def test_within_limits_passes_silently(
    db_session, test_org, test_admin_user, make_user, make_purchase,
):
    """Договор дешевле/не больше закупки по всем трём величинам — проходит
    молча, ни одного PlanExcessApproval не создаётся."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    p = await make_purchase(subsidy_id=subsidy.id, feo_category_id=cat.id)
    pi = await _make_purchase_item(
        db_session, p.id, cat.id,
        quantity=Decimal("2"), unit_price=Decimal("100"), total_price=Decimal("200"),
    )
    contract_item = ContractItemCreate(
        source_item_id=pi.id, name="Товар А",
        quantity=Decimal("2"), unit_price=Decimal("90"), total=Decimal("180"),
    )

    # Не должно бросить исключение.
    await enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: в пределах",
    )

    approvals = (await db_session.execute(
        select(PlanExcessApproval).where(PlanExcessApproval.feo_category_id == cat.id)
    )).scalars().all()
    assert not approvals, f"В пределах закупки — согласование не должно было создаваться: {approvals}"


@pytest.mark.asyncio
async def test_approved_passes(
    db_session, test_org, test_admin_user, make_user, make_purchase,
):
    """После согласования уполномоченным (право plan_excess.decide) та же
    превышающая позиция договора проходит без 409."""
    approver = await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    p = await make_purchase(subsidy_id=subsidy.id, feo_category_id=cat.id)
    pi = await _make_purchase_item(
        db_session, p.id, cat.id,
        quantity=Decimal("2"), unit_price=Decimal("100"), total_price=Decimal("200"),
    )
    contract_item = ContractItemCreate(
        source_item_id=pi.id, name="Товар А",
        quantity=Decimal("2"), unit_price=Decimal("150"), total=Decimal("300"),
    )

    # Сначала — заблокировано (как в test_price_higher_requires_approval).
    await _get_409(enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: согласовано",
    ))

    pending = (await db_session.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.feo_category_id == cat.id,
            PlanExcessApproval.status == "pending",
        )
    )).scalar_one_or_none()
    assert pending is not None, "Запрос на согласование не найден"

    # Реальный путь одобрения — тот же эндпоинт, что использует финансист на
    # фронте (POST /api/plan-excess/{id}/decide), вызванный напрямую как
    # обычная async-функция (без HTTP-слоя — избегаем настройки auth headers
    # для второстепенной для этого теста части сценария).
    from app.routers.plan_excess import decide_plan_excess_step
    decide_result = await decide_plan_excess_step(
        approval_id=pending.id,
        body={"decision": "approved"},
        db=db_session,
        current_user=approver,
    )
    assert decide_result["status"] == "approved", decide_result

    # Теперь та же самая превышающая позиция проходит без исключения.
    await enforce_contract_excess_approval(
        db_session, [contract_item], {pi.id: pi},
        subsidy_id=subsidy.id, current_user=test_admin_user,
        context_label="тест: согласовано (повтор)",
    )
