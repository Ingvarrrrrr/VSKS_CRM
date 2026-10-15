"""Единственный источник значений initiator_phone/initiator_email для
шаблонов документов (ПРАВИЛО №6 — одно место вычисления).

initiator_phone — мобильный телефон инициатора: User.phone (НЕ work_phone —
это стационарный, backend/app/models/user.py).

initiator_email — почта, по которой инициатор входит в систему: User.email;
если email пуст, а username содержит «@» — берём username (тот же порядок
проверки, что при логине, см. backend/app/routers/auth.py::login — сначала
email, потом username). Иначе "".

Нет пользователя → обе пустые строки.
"""
from typing import Optional

from app.models.user import User


def initiator_contacts(user: Optional[User]) -> dict:
    if user is None:
        return {"initiator_phone": "", "initiator_email": ""}

    phone = (user.phone or "").strip()

    email = (user.email or "").strip()
    if not email:
        username = (user.username or "").strip()
        if "@" in username:
            email = username

    return {"initiator_phone": phone, "initiator_email": email}
