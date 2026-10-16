from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, select
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql import func
from app.database import Base
from app.models.contractor import Contractor


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    # --- Правило №6: у организации НЕТ своих реквизитов ---------------------
    # Начиная с миграции w6x7y8z9a0b1 (16.10.2026) каждая организация
    # обязана иметь contractor_id — Contractor — ЕДИНСТВЕННОЕ место хранения
    # названия и юр. реквизитов. `name`/`full_name`/`inn`/`kpp`/`ogrn`/
    # `address`/`signatory*` ниже — НЕ колонки, а column_property с
    # скалярным подзапросом к contractors (read-only, вычисляются при
    # каждом SELECT, нигде не хранятся повторно). Присвоение `org.name = X`
    # не персистируется — пишите в `org.contractor` (см.
    # app/routers/organizations.py::update_organization).
    #
    # Физические колонки organizations.name/full_name/inn/... в БД остаются
    # (миграция их не удаляла — исторические данные и сама backfill-миграция
    # читают их), но из Python-кода доступны ТОЛЬКО под префиксом `_legacy_`
    # и только чтобы не плодить вторую живую копию поля с тем же именем;
    # нового кода, читающего `_legacy_*`, быть не должно — единственные
    # легитимные потребители — эта модель и alembic-миграции.
    _legacy_name = Column("name", String(255), nullable=True)
    _legacy_full_name = Column("full_name", String(1000), nullable=True)
    _legacy_inn = Column("inn", String(20), nullable=True)
    _legacy_kpp = Column("kpp", String(20), nullable=True)
    _legacy_ogrn = Column("ogrn", String(20), nullable=True)
    _legacy_address = Column("address", String(500), nullable=True)
    _legacy_signatory = Column("signatory", String(500), nullable=True)
    _legacy_signatory_position = Column("signatory_position", String(255), nullable=True)
    _legacy_signatory_last_name = Column("signatory_last_name", String(100), nullable=True)
    _legacy_signatory_first_name = Column("signatory_first_name", String(100), nullable=True)
    _legacy_signatory_middle_name = Column("signatory_middle_name", String(100), nullable=True)
    # --- конец блока legacy-колонок -----------------------------------------
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Multi-org / contour support
    root_org_id   = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    # Оргструктура «кто кому подчиняется» (редактор иерархии, стрелки орг→орг).
    # Отдельно от root_org_id (контур/видимость) — подчинение НЕ наследует видимость.
    parent_org_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id",         ondelete="SET NULL"), nullable=True)
    # Phase 17.1-03 — single-entity link to Contractor (source of truth for legal requisites)
    contractor_id = Column(Integer, ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True, index=True)
    # Phase 29.3: HEX цвет организации для UI акцентов (напр. #1976d2)
    color = Column(String(20), nullable=True)
    # Phase 30: geo координаты штаба (station-mapping)
    lat = Column(Numeric(9, 6), nullable=True)
    lon = Column(Numeric(9, 6), nullable=True)
    region = Column(String(100), nullable=True)
    head_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Fabrikant: город заключения договора
    contract_city = Column(String(200), nullable=True)
    # Руководитель организации по ЕГРЮЛ (владелец 2026-09-29: «подписант может
    # быть по доверенности — руководитель организации это руководитель
    # организации, из налоговой по ИНН»). ОТДЕЛЬНО от signatory_* (может
    # отличаться, если документы подписывает доверенное лицо) и от
    # head_user_id (не источник для определения руководителя — см.
    # app/services/org_head.py::resolve_org_head_user_id, единственное место,
    # которое читает эти поля для цепочки согласования).
    director_last_name = Column(String(100), nullable=True)
    director_first_name = Column(String(100), nullable=True)
    director_middle_name = Column(String(100), nullable=True)
    director_position = Column(String(255), nullable=True)

    users      = relationship("User", back_populates="organization", foreign_keys="User.org_id")
    child_orgs = relationship("Organization", foreign_keys="Organization.root_org_id", lazy="selectin")
    contractor = relationship("Contractor", foreign_keys="Organization.contractor_id", lazy="joined")

    # --- Правило №6: вычисляемые реквизиты — читают ИСКЛЮЧИТЕЛЬНО контрагента
    # Скалярный подзапрос вместо JOIN: та же техника, что и для обычных
    # computed-полей в SQLAlchemy 2.0 (column_property + scalar_subquery);
    # в проекте это первый column_property — других аналогов пока не было,
    # синтаксис подобран по доке SQLAlchemy 2.0.23 (текущая версия проекта).
    # `.correlate_except(Contractor)` — чтобы подзапрос коррелировал именно
    # с внешним organizations, а не сам с собой.
    #
    # Организация без contractor_id (не должно происходить после миграции
    # w6x7y8z9a0b1 — она привязала контрагента КАЖДОЙ организации, а новый
    # код обязан создавать контрагента при создании org) вернёт NULL по
    # каждому полю — это ЗАДУМАНО: пусто у контрагента значит пусто,
    # никакого фолбэка на _legacy_* в новом коде быть не должно.
    #
    # `expire_on_flush=False` на КАЖДОМ column_property ниже (доработка
    # 17.10.2026, после находки: `Organization.name` читают сотни мест
    # сериализаторов — субсидии/закупки/иерархия/документы — точечные обходы
    # через явную привязку relationship в паре мест не масштабируются).
    # БЕЗ этого флага SQLAlchemy по умолчанию считает скалярный подзапрос
    # потенциально зависящим от ЛЮБОГО UPDATE той же строки organizations и
    # после `flush()` помечает его "expired" — следующий синхронный
    # `getattr(org, 'name')` вне `await` (а он почти всегда синхронный —
    # сериализаторы/логи/f-строки) пытается тихо перезагрузить и падает
    # `sqlalchemy.exc.MissingGreenlet` (воспроизведено: commit правки
    # org.region/color → getattr(org, 'name')). С флагом commit строки
    # organizations не трогает эти атрибуты — они остаются тем значением,
    # что было вычислено при последнем SELECT/refresh этого объекта (ровно
    # то же допущение, что и `expire_on_commit=False` у сессии, просто явно
    # на уровне каждого вычисляемого поля, а не только всей сессии).
    name = column_property(
        select(Contractor.name).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    full_name = column_property(
        select(Contractor.full_name).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    inn = column_property(
        select(Contractor.inn).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    kpp = column_property(
        select(Contractor.kpp).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    ogrn = column_property(
        select(Contractor.ogrn).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    address = column_property(
        select(Contractor.address).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    signatory = column_property(
        select(Contractor.signatory).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    signatory_position = column_property(
        select(Contractor.signatory_position).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    signatory_last_name = column_property(
        select(Contractor.signatory_last_name).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    signatory_first_name = column_property(
        select(Contractor.signatory_first_name).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
    signatory_middle_name = column_property(
        select(Contractor.signatory_middle_name).where(Contractor.id == contractor_id)
        .correlate_except(Contractor).scalar_subquery(),
        expire_on_flush=False,
    )
