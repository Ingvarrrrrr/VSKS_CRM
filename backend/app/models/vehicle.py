"""
Vehicle fleet main model — Plan 29-01, Phase 29 «Имущество → Автотранспорт».

Decisions covered: D-04, D-06, D-08, D-13, D-18, D-20.

DATE COLUMNS (needed in _DATE_FIELDS for PATCH routers — plans 29-04+):
  - registered_at
  - insurance_until
  - last_to_date
  - tech_inspection_until
  - assignment_doc_date  (Phase 29.3)
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Numeric,
    ForeignKey, Date, DateTime, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Vehicle(Base):
    """
    Основная карточка транспортного средства.

    D-06: owner_org_id — кому принадлежит; assigned_org_id — у кого в эксплуатации.
    D-08: mixed schema — канонические колонки + bool-слоты + JSONB props.
    D-20: fuel_norm_summer / fuel_norm_winter — нормы расхода л/100км.
    """
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)

    # D-06 Multi-tenancy visibility
    owner_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_text = Column(String(100), nullable=True)  # fallback: свободный текст для регионов без org

    # Identification
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    color = Column(String(50), nullable=True)
    vin = Column(String(17), nullable=True, index=True)
    # Автоблок (2026-09): гос. номер необязателен — машина может быть куплена, но
    # ещё не поставлена на учёт. unique=True сохранён — в Postgres несколько NULL
    # не конфликтуют друг с другом. Опознавание такой машины — по VIN (см.
    # app/routers/vehicles_dashboard.py _dedup_key: vin → plate → id).
    plate = Column(String(20), nullable=True, unique=True, index=True)

    # Registration & docs
    registered_at = Column(Date, nullable=True)       # DATE — add to _DATE_FIELDS in 29-04
    insurance_until = Column(Date, nullable=True)     # DATE — add to _DATE_FIELDS in 29-04

    # Extended Голичков registry fields (Plan 29-3a2)
    year_of_manufacture = Column(Integer, nullable=True)       # Год выпуска
    last_to_mileage_km = Column(Integer, nullable=True)        # Пробег при последнем ТО
    last_to_date = Column(Date, nullable=True)                 # Дата последнего ТО
    pts_number = Column(String(50), nullable=True)             # Номер ПТС
    sts_number = Column(String(50), nullable=True)             # Номер СТС
    tech_inspection_until = Column(Date, nullable=True)        # Техосмотр действителен до
    purchase_info = Column(String(200), nullable=True)         # Где/как куплено ("ФПГ Иркутск")

    # Type & state: VARCHAR (not PG ENUM) per RISKS: easier migration
    # VehicleType values: car_light / suv / pickup / minivan / truck_van / truck_board /
    #   truck_tank / truck_metal / bus / special / quadbike / snowmobile / boat / boat_motor /
    #   trailer / other
    type = Column(String(30), nullable=True, index=True)

    # VehicleState values: working / broken / in_repair / needs_repair / destroyed / utilized
    state = Column(String(20), nullable=True, default="working", index=True)

    # Fuel — D-20
    # FuelType values: AI-92 / AI-95 / AI-98 / AI-100 / DT / GAS / other
    fuel_type = Column(String(20), nullable=True)
    fuel_norm_summer = Column(Float, nullable=True)   # л/100км, May-Sep
    fuel_norm_winter = Column(Float, nullable=True)   # л/100км, Oct-Apr

    # Equipment bool slots (D-08)
    has_tracker = Column(Boolean, nullable=True)
    akb_ok = Column(Boolean, nullable=True)
    has_radio = Column(Boolean, nullable=True)
    mirrors_ok = Column(Boolean, nullable=True)
    has_keys = Column(Boolean, nullable=True)
    has_first_aid_kit = Column(Boolean, nullable=True)
    has_spare_wheel = Column(Boolean, nullable=True)
    has_extinguisher = Column(Boolean, nullable=True)

    # Принадлежность — основание передачи (Phase 29.3)
    assignment_basis = Column(String(200), nullable=True)      # Основание для использования
    assignment_doc_number = Column(String(100), nullable=True) # Номер документа
    assignment_doc_date = Column(Date, nullable=True)          # Дата документа

    # Двигатель (Phase 29.3)
    engine_power_hp = Column(Integer, nullable=True)   # Мощность двигателя, л.с.
    engine_volume_l = Column(Float, nullable=True)     # Объём двигателя, л

    # TO warning (D-17)
    next_to_km = Column(Integer, nullable=True)             # километраж следующего ТО
    current_odometer_km = Column(Integer, nullable=True)    # snapshot из последнего VehicleOdometer

    # JSONB props (D-08): branding, paint_condition, tires_type, defect_description, note, custom.*
    # server_default='{}' to avoid mutable-default trap
    props = Column(JSONB, nullable=False, server_default="{}")

    # ── Автоблок: полный реестр полей ТС (35 колонок) — лист «26.05.2026» ──────
    # см. AUTOBLOCK_FIELDS_SPEC.md §1. Все nullable. Даты — в _DATE_FIELDS routers/vehicles.py.
    body_type = Column(String(50), nullable=True)                       # Кузов
    pts_category = Column(String(10), nullable=True)                    # Категория ТС по ПТС
    insurance_company = Column(String(150), nullable=True)              # Страховая компания
    insurance_policy_number = Column(String(100), nullable=True)        # Номер страхового договора
    ownership_basis = Column(String(200), nullable=True)                # Основание возникновения собственности
    ownership_doc_number = Column(String(100), nullable=True)           # № документа основания собственности
    ownership_doc_date = Column(Date, nullable=True)                    # Дата документа основания собственности
    owner_since = Column(Date, nullable=True)                           # Дата, когда организация стала собственником
    location_city = Column(String(100), nullable=True)                  # Текущее место нахождения — город
    location_address = Column(String(300), nullable=True)               # Текущее место нахождения — адрес
    home_base_city = Column(String(100), nullable=True)                 # Место постоянной приписки ТС
    responsible_name = Column(String(150), nullable=True)               # Ответственный (ФИО)
    pts_kind = Column(String(20), nullable=True)                        # Вид ПТС: paper / electronic
    sts_issued_at = Column(Date, nullable=True)                         # СТС — дата выдачи
    tech_inspection_status = Column(String(100), nullable=True)         # Обязательный техосмотр (текст)
    tech_inspection_last_date = Column(Date, nullable=True)             # Дата последнего обязательного техосмотра
    pass_zo = Column(String(100), nullable=True)                        # Пропуск ЗО
    pass_zo_until = Column(Date, nullable=True)                         # Дата истечения пропуска ЗО
    pass_ho = Column(String(100), nullable=True)                        # Пропуск ХО
    pass_ho_until = Column(Date, nullable=True)                         # Дата истечения пропуска ХО
    pass_dnr = Column(String(100), nullable=True)                       # Пропуск ДНР
    pass_dnr_until = Column(Date, nullable=True)                        # Дата истечения пропуска ДНР
    pass_lnr = Column(String(100), nullable=True)                       # Пропуск ЛНР
    pass_lnr_until = Column(Date, nullable=True)                        # Дата истечения пропуска ЛНР
    pass_moscow = Column(String(100), nullable=True)                    # Пропуск Москва
    pass_moscow_until = Column(Date, nullable=True)                     # Дата истечения пропуска Москва
    has_spare_tires = Column(Boolean, nullable=True)                    # Наличие сменной резины
    tires_condition = Column(String(100), nullable=True)                # Состояние резины
    has_mirrors = Column(Boolean, nullable=True)                        # Наличие зеркал
    first_aid_kit_until = Column(Date, nullable=True)                   # Аптечка — срок истечения использования
    extinguisher_check_date = Column(Date, nullable=True)               # Огнетушитель — дата поверки
    tracker_paid_until = Column(Date, nullable=True)                    # Трекер — дата оплаты
    has_tachograph = Column(Boolean, nullable=True)                     # Тахограф
    tachograph_check_date = Column(Date, nullable=True)                 # Тахограф — дата поверки
    repair_required = Column(Boolean, nullable=True)                    # Требуется ремонт
    tech_condition_info = Column(Text, nullable=True)                   # Сведения о техническом состоянии

    # ── Брендирование: признак Да/Нет отдельно от состояния (2026-09) ──────────
    # props.branding хранит ТЕКСТ состояния брендирования (переиспользован —
    # раньше был просто "брендирование" свободным текстом); has_branding — новый
    # типизированный признак наличия, проставлен миграцией по факту непустого текста.
    has_branding = Column(Boolean, nullable=True)                       # Брендирование (Да/Нет)

    # ── Резина: летний/зимний комплект отдельно (2026-09) ───────────────────────
    # tires_type (props) — какой комплект СЕЙЧАС установлен (Зимняя/Летняя/Нет
    # данных); tires_condition (колонка выше) — устаревшее общее поле, оставлено
    # как есть, данные перенесены миграцией в один из комплектов ниже.
    tires_summer_radius = Column(String(20), nullable=True)             # Летняя резина — радиус
    tires_summer_profile = Column(String(20), nullable=True)            # Летняя резина — профиль
    tires_summer_condition = Column(String(100), nullable=True)         # Летняя резина — состояние
    tires_winter_radius = Column(String(20), nullable=True)             # Зимняя резина — радиус
    tires_winter_profile = Column(String(20), nullable=True)            # Зимняя резина — профиль
    tires_winter_condition = Column(String(100), nullable=True)         # Зимняя резина — состояние

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner_org = relationship("Organization", foreign_keys=[owner_org_id])
    assigned_org = relationship("Organization", foreign_keys=[assigned_org_id])

    attachments = relationship(
        "VehicleAttachment", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin"
    )
    repairs = relationship(
        "VehicleRepair", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleRepair.date.desc()"
    )
    field_history = relationship(
        "VehicleFieldHistory", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleFieldHistory.changed_at.desc()"
    )
    odometer_entries = relationship(
        "VehicleOdometer", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleOdometer.date.desc()"
    )
    fuel_logs = relationship(
        "FuelLog", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FuelLog.date.desc()"
    )
    trips = relationship(
        "Trip", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="Trip.date.desc()"
    )
    transfer_history = relationship(
        "VehicleTransferHistory", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleTransferHistory.changed_at.desc()"
    )
    fines = relationship(
        "VehicleFine", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehicleFine.issued_at.desc()"
    )
    # Phase 30: documents
    fleet_documents = relationship(
        "FleetDocument", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="FleetDocument.expires_at.desc().nullslast()"
    )
    # 2026-09: произвольный набор пропусков (заменяет 10 фиксированных колонок pass_*)
    passes = relationship(
        "VehiclePass", back_populates="vehicle",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="VehiclePass.name"
    )
