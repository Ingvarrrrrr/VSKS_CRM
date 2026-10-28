# -*- coding: utf-8 -*-
"""Регрессия двух жалоб владельца (28.10.2026, субсидия «ЗО_актуальная»/
орг «ЗРО ВСКС» на проде, id=111/69):

1) GET /api/subsidies/?scope=wishes прятал субсидию, которая уже видна
   пользователю через видимую закупку (routers/subsidies.py::list_subsidies,
   фолбэк переиспользован из auth/object_visibility.py::ensure_subsidy_visible).
2) Руководитель/подписант из ЕГРЮЛ не попадал в штат организации, если у
   организации уже БЫЛ какой-то штат, не включающий его
   (services/signatory_staff.py::ensure_signatory_staff_for_org).
"""
import pytest
from sqlalchemy import select

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User


@pytest.mark.asyncio
async def test_subsidies_picker_includes_subsidy_visible_via_purchase(
    client, db_session, test_org, make_user,
):
    """Пользователь не состоит в организации субсидии и не имеет персонального
    гранта, но назначен исполнителем закупки этой субсидии — она должна
    появиться в пикере /subsidies/?scope=wishes, а не только проходить
    бэкенд-проверку при сохранении заявки (иначе фронт не даёт её выбрать
    и показывает raw id вместо имени — ровно баг с прода)."""
    from app.auth.jwt import create_access_token

    other_org = Organization(contractor_id=None)
    other_contractor = Contractor(name="ЗРО ВСКС (тест)")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org.contractor_id = other_contractor.id
    db_session.add(other_org)
    await db_session.flush()

    subsidy = Subsidy(name="ЗО_актуальная (тест)", year=2026, org_id=other_org.id, status="approved")
    db_session.add(subsidy)
    await db_session.flush()

    assignee = await make_user(role="admin")  # не состоит в other_org

    purchase = Purchase(subsidy_id=subsidy.id, status="plan_schedule", assigned_user_id=assignee.id)
    db_session.add(purchase)
    await db_session.commit()

    token = create_access_token({"sub": assignee.username})
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/subsidies/?scope=wishes", headers=headers)
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert subsidy.id in ids, (
        "Субсидия с видимой закупкой пользователя отсутствует в пикере заявки"
    )


@pytest.mark.asyncio
async def test_ensure_signatory_staff_adds_director_even_with_existing_staff(
    db_session, test_org,
):
    """Организация уже имеет штат (как ЗРО ВСКС: Копылова, Титов), но среди
    него нет руководителя по ЕГРЮЛ (Юрченкова) — ensure_signatory_staff_for_org
    обязан завести её сотрудником, а не молчать из-за того, что штат не пуст."""
    from app.services.signatory_staff import ensure_signatory_staff_for_org

    contractor = await db_session.get(Contractor, test_org.contractor_id)
    contractor.signatory_last_name = "Юрченкова"
    contractor.signatory_first_name = "Анастасия"
    contractor.signatory_middle_name = "Евгеньевна"
    contractor.signatory_position = "ПРЕДСЕДАТЕЛЬ СОВЕТА"

    existing_staff = User(
        username="existing_staffer_zro",
        password_hash="x",
        role="employee",
        org_id=test_org.id,
        full_name="Копылова Ольга Владимировна",
    )
    db_session.add(existing_staff)
    await db_session.commit()

    user = await ensure_signatory_staff_for_org(db_session, test_org)
    await db_session.commit()

    assert user is not None
    assert user.full_name == "Юрченкова Анастасия Евгеньевна"
    assert user.org_id == test_org.id
    assert user.position == "ПРЕДСЕДАТЕЛЬ СОВЕТА"

    # Идемпотентность: повторный вызов находит уже созданного, не дублирует
    # (scope — ЭТА организация; полное ФИО не гарантированно уникально
    # глобально по БД, формула дедупа — org_staff_user_ids(org_id) ∩ ФИО).
    user2 = await ensure_signatory_staff_for_org(db_session, test_org)
    assert user2.id == user.id
    count = (await db_session.execute(
        select(User).where(User.full_name == "Юрченкова Анастасия Евгеньевна", User.org_id == test_org.id)
    )).scalars().all()
    assert len(count) == 1
