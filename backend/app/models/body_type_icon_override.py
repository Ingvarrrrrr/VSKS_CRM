from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, DateTime, func
from app.database import Base


class BodyTypeIconOverride(Base):
    """Переопределение значка типа кузова карточки ТС — по организации.

    Владелец (2026-09): «Показать лист, как сопоставлен какой кузов — картинка,
    и чтобы я мог это корректировать». Хранение по образцу OrgSectionConfig
    (app/models/org_section_config.py, см. app/services/vehicle_fields.py) —
    одна строка = один переопределённый кузов конкретной организации.

    Значение по умолчанию НЕ дублируется в БД — оно остаётся хардкодом в
    frontend/src/components/vehicles/bodyTypeIcon.ts (BODY_TYPE_ICON_MAP).
    Эта таблица хранит ТОЛЬКО отличия от дефолта: нет строки для пары
    (org_id, body_type) → используется дефолт, ничего не ломается у тех, кто
    ничего не настраивал.
    """
    __tablename__ = "body_type_icon_overrides"
    __table_args__ = (
        UniqueConstraint("org_id", "body_type", name="uq_body_type_icon_org_body"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    body_type = Column(String(100), nullable=False)
    # 'img' — PNG-силуэт из /public/vehicle-icons/{icon_value}.png
    # 'mdi' — иконка @mdi/font, icon_value хранит полное имя класса ("mdi-truck")
    icon_kind = Column(String(10), nullable=False)
    icon_value = Column(String(100), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
