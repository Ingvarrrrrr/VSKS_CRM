"""
Редактор значков кузова ТС — переопределения по организации (владелец, 2026-09):
«Показать лист, как сопоставлен какой кузов — картинка, и чтобы я мог это
корректировать».

Хранение: app/models/body_type_icon_override.py (таблица
body_type_icon_overrides, по образцу org_section_config — см.
app/services/vehicle_fields.py). Значение по умолчанию НЕ дублируется здесь —
оно хардкод в frontend/src/components/vehicles/bodyTypeIcon.ts
(BODY_TYPE_ICON_MAP); эта модель отвечает только за хранение/валидацию/выдачу
ОТЛИЧИЙ от дефолта. Список допустимых значений «Кузов» — тот же единственный
источник правды, что и для карточки ТС: BODY_TYPE_OPTIONS
(app/services/vehicle_sheet_dictionaries.py).

Право на изменение — vehicle.fields.manage (то же право, что и состав полей
карточки ТС — новый класс настроек того же рода, новых прав не заводим).
"""
from __future__ import annotations

import re
from typing import Dict, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_type_icon_override import BodyTypeIconOverride
from app.services.vehicle_sheet_dictionaries import BODY_TYPE_OPTIONS

ICON_KINDS = {"img", "mdi"}

# icon_value ограничения:
#   img  — basename PNG-файла в /public/vehicle-icons/, без пути и расширения
#   mdi  — полное имя класса @mdi/font
_IMG_VALUE_RE = re.compile(r"^[a-z0-9_]{1,100}$")
_MDI_VALUE_RE = re.compile(r"^mdi-[a-z0-9-]{1,95}$")


class InvalidBodyTypeIcon(ValueError):
    """Валидация переопределения не прошла — понятное сообщение для 400."""


def is_valid_body_type(body_type: str) -> bool:
    return body_type in BODY_TYPE_OPTIONS


def validate_icon(icon_kind: str, icon_value: str) -> None:
    """Бросает InvalidBodyTypeIcon с человеко-читаемым текстом, если что-то не так."""
    if icon_kind not in ICON_KINDS:
        raise InvalidBodyTypeIcon(f"Недопустимый тип значка «{icon_kind}» — ожидается img или mdi.")
    if icon_kind == "img":
        if not _IMG_VALUE_RE.match(icon_value or ""):
            raise InvalidBodyTypeIcon("Некорректное имя файла силуэта.")
    else:
        if not _MDI_VALUE_RE.match(icon_value or ""):
            raise InvalidBodyTypeIcon("Некорректное имя MDI-иконки (должно начинаться с «mdi-»).")


async def get_overrides(db: AsyncSession, org_id: int) -> Dict[str, Dict[str, str]]:
    """Переопределения организации: {body_type: {icon_kind, icon_value}}."""
    rows = (await db.execute(
        select(
            BodyTypeIconOverride.body_type,
            BodyTypeIconOverride.icon_kind,
            BodyTypeIconOverride.icon_value,
        ).where(BodyTypeIconOverride.org_id == org_id)
    )).all()
    return {
        body_type: {"icon_kind": icon_kind, "icon_value": icon_value}
        for body_type, icon_kind, icon_value in rows
    }


async def upsert_override(
    db: AsyncSession, org_id: int, body_type: str, icon_kind: str, icon_value: str
) -> None:
    if not is_valid_body_type(body_type):
        raise InvalidBodyTypeIcon(f"Неизвестное значение «Кузов»: {body_type}")
    validate_icon(icon_kind, icon_value)

    stmt = pg_insert(BodyTypeIconOverride).values(
        org_id=org_id, body_type=body_type, icon_kind=icon_kind, icon_value=icon_value,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_body_type_icon_org_body",
        set_={"icon_kind": icon_kind, "icon_value": icon_value, "updated_at": func.now()},
    )
    await db.execute(stmt)
    await db.commit()


async def delete_override(db: AsyncSession, org_id: int, body_type: str) -> None:
    await db.execute(
        delete(BodyTypeIconOverride).where(
            BodyTypeIconOverride.org_id == org_id,
            BodyTypeIconOverride.body_type == body_type,
        )
    )
    await db.commit()


async def delete_all_overrides(db: AsyncSession, org_id: int) -> None:
    await db.execute(delete(BodyTypeIconOverride).where(BodyTypeIconOverride.org_id == org_id))
    await db.commit()
