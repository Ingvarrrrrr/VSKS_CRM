"""FactImportRun — журнал прогонов мастера «Импорт факта».

Задача 02.10.2026 (план breezy-mixing-lovelace.md, часть 2). Один прогон =
один commit() мастера: файл + лист + решения пользователя (decisions) +
что получилось (счётчики, report, created_refs). GET /runs(/{id}) и
POST /runs/{id}/rollback читают этот ряд вместо повторного парсинга файла.

НЕ зарегистрирован в app/models/__init__.py (тот файл уже правит другая
сессия, см. задачу) — модель импортируется напрямую там, где нужна
(app/services/historical_fact_import/*, app/routers/fact_import.py). Это не
создаёт проблем для relationship()-строк, потому что ни одна существующая
модель не ссылается на FactImportRun по строковому имени — Purchase/Payment
получили только FK-колонку import_run_id (см. их файлы), без relationship().
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class FactImportRun(Base):
    __tablename__ = "fact_import_runs"

    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(500), nullable=True)
    sheet = Column(String(255), nullable=True)
    format = Column(String(20), nullable=True)  # 'columns' | 'sections'
    mapping = Column(JSONB, nullable=False, default=dict)
    decisions = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="committed")  # 'committed' | 'rolled_back'
    purchases_created = Column(Integer, nullable=False, default=0)
    payments_created = Column(Integer, nullable=False, default=0)
    contractors_created = Column(Integer, nullable=False, default=0)
    created_refs = Column(JSONB, nullable=False, default=dict)
    report = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
