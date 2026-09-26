from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class FeoImportRun(Base):
    """Один прогон импорта ФЭО из Excel (журнал изменений, волна 1, 22.09).

    Владелец: «Импорт ФЭО не оставляет записи, кто загрузил файл и что он
    перезаписал» — эта строка фиксирует факт прогона (кто, когда, какой файл,
    сколько строк создано/обновлено/пропущено); построчные изменения
    записываются в entity_changes с source='import', source_ref=этот id (см.
    app/services/feo_history.py).

    subsidy_id nullable — один файл импорта может нести категории/позиции
    НЕСКОЛЬКИХ субсидий сразу (импорт не привязан к одной субсидии заранее).

    ⚠️ НЕ зарегистрирована в app/models/__init__.py осознанно: тот файл сейчас
    правит параллельная сессия 152-ФЗ (untracked backend/app/models/
    user_consent.py импортируется оттуда) — трогать models/__init__.py
    запрещено во избежание конфликта при коммите параллельной сессии (прод
    ляжет 502, если её untracked-модуль пропадёт из импорта). Вместо этого
    модель импортируется в app/routers/feo_import.py (роутер уже подключён к
    приложению в app/routes.py) — этого достаточно, чтобы Base.metadata знал
    таблицу; саму таблицу создаёт явная миграция
    t6v8x1z3b5d7_feo_history_foundation.py, а не check_schema/create_all.

    TODO: перенести регистрацию `from app.models.feo_import_run import
    FeoImportRun` в app/models/__init__.py, когда 152-ФЗ параллельной сессии
    будет закоммичен и models/__init__.py снова свободен для правок.
    """
    __tablename__ = "feo_import_runs"

    id = Column(Integer, primary_key=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_name = Column(String(200), nullable=True)
    filename = Column(String(500), nullable=True)
    sheet_name = Column(String(200), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_count = Column(Integer, nullable=False, default=0, server_default="0")
    updated_count = Column(Integer, nullable=False, default=0, server_default="0")
    skipped_count = Column(Integer, nullable=False, default=0, server_default="0")
    comments_created = Column(Integer, nullable=False, default=0, server_default="0")
    warnings_count = Column(Integer, nullable=False, default=0, server_default="0")
    summary = Column(JSONB, nullable=True)
