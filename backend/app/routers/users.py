from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.auth.jwt import hash_password, require_role, get_current_user, get_org_filter, get_single_org_id, ADMIN_ROLES
from app.schemas.schemas import UserCreate, UserUpdate, UserOut
from typing import List, Optional

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role(*ADMIN_ROLES))):
    q = select(User).order_by(User.full_name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q)
    return result.scalars().all()

@router.post("/", response_model=UserOut)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "account_owner")),
):
    # Email uniqueness check
    existing_email = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if existing_email:
        raise HTTPException(400, "Пользователь с таким email уже существует")

    # Auto-generate username from email if not provided
    username = data.username
    if not username:
        base = data.email.split('@')[0].lower()
        username = base
        suffix = 1
        while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"{base}{suffix}"
            suffix += 1
    else:
        existing = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "Пользователь с таким логином уже существует")

    # Org admins can only create users in their org
    org_id = data.org_id if current_user.role == 'superadmin' and data.org_id else current_user.org_id
    if not org_id:
        raise HTTPException(400, "Необходимо указать организацию")

    norm_dept = data.department.strip().title() if data.department else data.department
    user = User(
        username=username,
        password_hash=hash_password(data.password),
        role=data.role,
        full_name=data.full_name,
        city=data.city,
        department=norm_dept,
        position=data.position,
        phone=data.phone,
        telegram_id=__import__('re').sub(r'[^0-9]', '', str(data.telegram_id)) if data.telegram_id else None,
        email=data.email,
        avatar=data.avatar,
        is_email_confirmed=True,
        org_id=org_id,
        inn=data.inn,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Sync to department if set
    if user.department:
        await _sync_user_department(user, db)
    return user


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Текущий пользователь (для синхронизации role/name в localStorage)."""
    return UserOut.model_validate(current_user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "account_owner", "admin")),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if current_user.role == 'account_owner' and user.org_id != current_user.org_id:
        raise HTTPException(403, "Нет доступа")

    update_data = data.dict(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd:
            if current_user.role not in ("superadmin", "account_owner"):
                raise HTTPException(403, "Изменение пароля доступно только владельцу аккаунта и выше")
            user.password_hash = hash_password(pwd)

    # Normalize department name to Title Case
    if "department" in update_data and update_data["department"]:
        update_data["department"] = update_data["department"].strip().title()

    # Strip non-digits from telegram_id
    import re as _re
    if "telegram_id" in update_data and update_data["telegram_id"]:
        update_data["telegram_id"] = _re.sub(r'[^0-9]', '', str(update_data["telegram_id"]))

    for k, v in update_data.items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)

    # Sync department membership
    if "department" in update_data or "position" in update_data:
        await _sync_user_department(user, db)

    return user


async def _sync_user_department(user: User, db: AsyncSession):
    """Sync user.department to DepartmentMember table and auto-set hierarchy."""
    from app.models.department import Department, DepartmentMember
    from app.models.user_hierarchy import UserHierarchy

    if not user.department or not user.org_id:
        return

    # Find or create department
    dept = (await db.execute(
        select(Department).where(
            Department.org_id == user.org_id,
            Department.name == user.department,
        )
    )).scalar_one_or_none()
    if not dept:
        dept = Department(name=user.department, org_id=user.org_id)
        db.add(dept)
        await db.flush()

    # Ensure membership
    existing = (await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == dept.id,
            DepartmentMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.position = user.position
    else:
        db.add(DepartmentMember(department_id=dept.id, user_id=user.id, position=user.position))

    # If user is head of this dept — auto-create hierarchy for all members
    if dept.head_user_id == user.id:
        await _sync_head_hierarchy(dept, db)

    await db.commit()


async def _sync_head_hierarchy(dept, db: AsyncSession):
    """Make all department members subordinates of the head."""
    from app.models.department import DepartmentMember
    from app.models.user_hierarchy import UserHierarchy

    if not dept.head_user_id:
        return
    members = (await db.execute(
        select(DepartmentMember.user_id).where(
            DepartmentMember.department_id == dept.id,
            DepartmentMember.user_id != dept.head_user_id,
        )
    )).scalars().all()

    for uid in members:
        existing = (await db.execute(
            select(UserHierarchy).where(
                UserHierarchy.manager_id == dept.head_user_id,
                UserHierarchy.subordinate_id == uid,
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(UserHierarchy(manager_id=dept.head_user_id, subordinate_id=uid))

# ---------------------------------------------------------------------------
# Sync user to contractors
# ---------------------------------------------------------------------------

@router.post("/{user_id}/sync-contractor")
async def sync_user_to_contractor(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Create or update a Contractor record from user data (same org, filtered accordingly)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if not user.full_name and not user.inn:
        raise HTTPException(400, "У сотрудника нет ни ФИО, ни ИНН — нечего записывать")

    from app.models.contractor import Contractor

    # Try to find existing contractor by INN or by name within same org
    contractor = None
    if user.inn:
        contractor = (await db.execute(
            select(Contractor).where(
                Contractor.inn == user.inn,
                Contractor.org_id == user.org_id,
            )
        )).scalar_one_or_none()
    if not contractor and user.full_name:
        contractor = (await db.execute(
            select(Contractor).where(
                Contractor.name == user.full_name,
                Contractor.org_id == user.org_id,
            )
        )).scalar_one_or_none()

    if contractor:
        if user.full_name: contractor.name = user.full_name
        if user.inn: contractor.inn = user.inn
        if user.phone: contractor.phone = user.phone
        if user.email: contractor.email = user.email
        contractor.contact_person = user.full_name
        await db.commit()
        return {"ok": True, "action": "updated", "contractor_id": contractor.id}
    else:
        c = Contractor(
            name=user.full_name or user.username,
            inn=user.inn,
            phone=user.phone,
            email=user.email,
            contact_person=user.full_name,
            org_type="Физ.лицо",
            org_id=user.org_id,
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return {"ok": True, "action": "created", "contractor_id": c.id}


# ---------------------------------------------------------------------------
# Signature (подпись пользователя)
# ---------------------------------------------------------------------------

@router.get("/me/signature")
async def get_my_signature(current_user: User = Depends(get_current_user)):
    return {"signature": current_user.signature_image}


@router.put("/me/signature")
async def save_my_signature(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sig = body.get("signature", "")
    if not sig or not sig.startswith("data:image/"):
        raise HTTPException(422, "Подпись должна быть в формате data:image/png;base64,...")
    if len(sig) > 500_000:
        raise HTTPException(422, "Подпись слишком большая (макс 500 КБ)")
    current_user.signature_image = sig
    await db.commit()
    return {"ok": True}


@router.delete("/me/signature")
async def delete_my_signature(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.signature_image = None
    await db.commit()
    return {"ok": True}


@router.get("/me/photo")
async def get_my_photo(current_user: User = Depends(get_current_user)):
    return {"photo_url": current_user.profile_photo}


@router.put("/me/photo")
async def save_my_photo(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = body.get("photo_url", "")
    if not photo or not photo.startswith("data:image/"):
        raise HTTPException(422, "Фото должно быть в формате data:image/...;base64,...")
    if len(photo) > 2_000_000:
        raise HTTPException(422, "Фото слишком большое (макс 2 МБ)")
    current_user.profile_photo = photo
    await db.commit()
    return {"ok": True}


@router.delete("/me/photo")
async def delete_my_photo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.profile_photo = None
    await db.commit()
    return {"ok": True}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "account_owner")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    # Org admin can only delete users from their org
    if current_user.role == 'account_owner' and user.org_id != current_user.org_id:
        raise HTTPException(403, "Insufficient permissions")
    await db.delete(user)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dictionaries: departments & positions
# ---------------------------------------------------------------------------

DEFAULT_DEPARTMENTS = [
    "Отдел закупок", "Бухгалтерия", "Юридический отдел", "Склад",
    "Отдел кадров", "ИТ-отдел", "Отдел продаж", "Административный отдел",
    "Финансовый отдел", "Отдел логистики", "Отдел маркетинга",
    "Производственный отдел", "Служба безопасности", "Канцелярия",
]

DEFAULT_POSITIONS = [
    "Начальник отдела", "Заместитель начальника отдела", "Ведущий специалист",
    "Главный специалист", "Специалист", "Менеджер", "Старший менеджер",
    "Бухгалтер", "Главный бухгалтер", "Юрист", "Кладовщик",
    "Администратор", "Секретарь", "Инженер", "Аналитик",
    "Руководитель направления", "Директор", "Заместитель директора",
]


@router.get("/dictionaries/departments")
async def get_department_names(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Default + custom departments used in this org."""
    org_ids = get_org_filter(current_user)
    q = select(User.department).where(User.department.isnot(None), User.department != "").distinct()
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q)
    custom = {r[0] for r in result.all()}
    all_depts = sorted(set(DEFAULT_DEPARTMENTS) | custom)
    return all_depts


@router.get("/dictionaries/positions")
async def get_position_names(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Default + custom positions used in this org."""
    org_ids = get_org_filter(current_user)
    q = select(User.position).where(User.position.isnot(None), User.position != "").distinct()
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q)
    custom = {r[0] for r in result.all()}
    all_positions = sorted(set(DEFAULT_POSITIONS) | custom)
    return all_positions


# ---------------------------------------------------------------------------
# Excel import
# ---------------------------------------------------------------------------

VALID_ROLES = ("employee", "manager", "admin", "account_owner")


@router.get("/import/template")
async def users_import_template(_=Depends(require_role("superadmin", "account_owner"))):
    """Download xlsx template for bulk user import."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    wb = Workbook()
    ws = wb.active
    ws.title = "Пользователи"

    headers = ["ФИО", "Email", "Логин", "Пароль", "Роль", "Город"]
    required = {"ФИО", "Email", "Логин", "Пароль"}

    header_fill = PatternFill("solid", fgColor="1E40AF")
    req_fill = PatternFill("solid", fgColor="1D4ED8")
    header_font = Font(bold=True, color="FFFFFF")

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = req_fill if h in required else header_fill
        cell.alignment = Alignment(horizontal="center")

    # Example row
    example = [
        "Иванов Иван Иванович", "ivanov@example.com", "ivanov",
        "Password123", "employee", "Москва",
    ]
    for ci, val in enumerate(example, 1):
        ws.cell(row=2, column=ci, value=val)

    # Role hint row
    ws.cell(row=3, column=5, value="Допустимые роли: employee, manager, admin, account_owner")

    col_widths = [35, 30, 20, 20, 20, 20]
    for ci, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=users_template.xlsx"},
    )


@router.post("/import/excel")
async def import_users_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "account_owner")),
):
    """Bulk import users from Excel file."""
    if not (file.filename or '').lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx / .xls")

    try:
        from openpyxl import load_workbook
    except ImportError:
        raise HTTPException(500, "openpyxl не установлен")

    content = await file.read()
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    ws = wb.active
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise HTTPException(400, "Файл пустой")

    def _norm(v) -> str:
        return str(v).strip().lower() if v else ''

    # Fuzzy column mapping
    col: dict[str, int] = {}
    for i, h in enumerate(header_row):
        h_str = _norm(h)
        if any(x in h_str for x in ('фио', 'фамил', 'имя', 'full_name', 'full name', 'ф.и.о')):
            col.setdefault('full_name', i)
        elif any(x in h_str for x in ('email', 'e-mail', 'почта', 'mail')):
            col.setdefault('email', i)
        elif any(x in h_str for x in ('логин', 'login', 'username', 'пользовател')):
            col.setdefault('username', i)
        elif any(x in h_str for x in ('пароль', 'password', 'pass')):
            col.setdefault('password', i)
        elif any(x in h_str for x in ('роль', 'role', 'должност')):
            col.setdefault('role', i)
        elif any(x in h_str for x in ('город', 'city', 'населённ')):
            col.setdefault('city', i)

    if 'full_name' not in col:
        raise HTTPException(400, "Не найдена колонка ФИО. Убедитесь что заголовок содержит «ФИО» или «full_name».")

    def _cell(row, field):
        idx = col.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ('none', 'null', '-', '—'):
            return None
        return s

    # Collect existing emails and usernames for dedup
    email_result = await db.execute(select(User.email).where(User.email.isnot(None)))
    existing_emails = {r[0].lower() for r in email_result if r[0]}
    username_result = await db.execute(select(User.username))
    existing_usernames = {r[0].lower() for r in username_result if r[0]}

    org_id = get_single_org_id(current_user)

    created = 0
    skipped = 0
    errors_list = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        full_name = _cell(row, 'full_name')
        if not full_name:
            skipped += 1
            continue

        email = _cell(row, 'email')
        username = _cell(row, 'username')
        password = _cell(row, 'password')
        role = _cell(row, 'role') or 'employee'
        city = _cell(row, 'city')

        # Validate required fields
        if not email:
            errors_list.append({"row": row_idx, "error": f"Нет email для «{full_name}»"})
            continue
        if not username:
            # Auto-generate username from email
            username = email.split('@')[0]
        if not password:
            errors_list.append({"row": row_idx, "error": f"Нет пароля для «{full_name}»"})
            continue

        # Validate role
        role = role.lower().strip()
        if role not in VALID_ROLES:
            errors_list.append({"row": row_idx, "error": f"Недопустимая роль «{role}» для «{full_name}». Допустимые: {', '.join(VALID_ROLES)}"})
            continue

        # Dedup
        if email.lower() in existing_emails:
            skipped += 1
            continue
        if username.lower() in existing_usernames:
            skipped += 1
            continue

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            full_name=full_name,
            city=city,
            email=email,
            is_email_confirmed=True,
            org_id=org_id,
        )
        db.add(user)
        existing_emails.add(email.lower())
        existing_usernames.add(username.lower())
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped, "errors": errors_list}
