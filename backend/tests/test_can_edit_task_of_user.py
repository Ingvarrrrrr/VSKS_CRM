"""Repro for ruff F823 in departments.py::can_edit_task_of_user.

Баг: `from app.models.user_organization import UserOrganization` был
продублирован ЛОКАЛЬНО внутри функции (ниже по коду, ветка ManagerOrganization),
хотя модуль уже импортирует UserOrganization на уровне файла. Правило области
видимости Python: если имени есть присваивание/import где-либо в теле функции,
оно локально для ВСЕЙ функции — значит первое же обращение к UserOrganization
в head_check (department-head проверка, выше по коду) падало с
UnboundLocalError на КАЖДОМ вызове can_edit_task_of_user, для любого
не-админа и не-владельца задачи (see routers/tasks.py:337).

Тест бьёт именно в head_check-ветку (самую первую после admin/own-task
шорткатов) — она одна уже воспроизводила краш до фикса, дальше по функции
код было бесполезно проверять отдельно.
"""
import uuid

import pytest
import pytest_asyncio

from app.models.department import Department
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.routers.departments import can_edit_task_of_user


@pytest_asyncio.fixture
async def dept_setup(db_session):
    """org + department + head (editor) + member (task_owner), head_user_id
    и member.dept_id — та самая связка, которую читает head_check."""
    org = Organization(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    head = User(
        username=f"head_{uuid.uuid4().hex[:8]}", password_hash="x",
        role="manager", org_id=org.id, full_name="Dept Head",
    )
    member = User(
        username=f"member_{uuid.uuid4().hex[:8]}", password_hash="x",
        role="employee", org_id=org.id, full_name="Dept Member",
    )
    db_session.add_all([head, member])
    await db_session.flush()

    dept = Department(name=f"Dept-{uuid.uuid4().hex[:8]}", org_id=org.id, head_user_id=head.id)
    db_session.add(dept)
    await db_session.flush()

    uo = UserOrganization(user_id=member.id, org_id=org.id, dept_id=dept.id)
    db_session.add(uo)
    await db_session.commit()
    await db_session.refresh(head)
    await db_session.refresh(member)
    await db_session.refresh(dept)
    return head, member, dept


@pytest.mark.asyncio
async def test_department_head_can_edit_member_task(db_session, dept_setup):
    """Раньше падало с UnboundLocalError до того, как успевало вернуть True."""
    head, member, _dept = dept_setup
    result = await can_edit_task_of_user(head, member.id, db_session)
    assert result is True


@pytest.mark.asyncio
async def test_unrelated_employee_cannot_edit_task(db_session, test_org):
    """Не админ, не владелец задачи, не начальник отдела → False, а не краш.

    До фикса УЖЕ этот путь (head_check-запрос) ронял UnboundLocalError,
    независимо от того, находил он совпадение или нет — баг был в самой
    попытке выполнить запрос, использующий имя UserOrganization."""
    editor = User(
        username=f"emp_{uuid.uuid4().hex[:8]}", password_hash="x",
        role="employee", org_id=test_org.id, full_name="Just An Employee",
    )
    other = User(
        username=f"other_{uuid.uuid4().hex[:8]}", password_hash="x",
        role="employee", org_id=test_org.id, full_name="Task Owner",
    )
    db_session.add_all([editor, other])
    await db_session.commit()
    await db_session.refresh(editor)
    await db_session.refresh(other)

    result = await can_edit_task_of_user(editor, other.id, db_session)
    assert result is False
