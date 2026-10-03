"""Согласие на обработку персональных данных (152-ФЗ) и обращения субъектов ПДн.

Правило №5 (модульность): отдельный файл — модели не относятся ни к одному
существующему домену (users/organizations/purchases/...), а обслуживают
исключительно юридический контур регистрации.

UserConsent фиксируется в ТОЙ ЖЕ транзакции, что и создание пользователя при
регистрации (backend/app/routers/organizations.py, POST /api/register) —
пользователь без записи согласия появиться не должен ни при каком исходе.
user_id nullable: на момент записи согласия у пользователя уже есть id
(запись создаётся после db.flush() пользователя, до commit), но поле оставлено
nullable с расчётом на будущие точки согласия ДО создания пользователя
(например forms до регистрации) — see `source`.

PersonalDataRequest — обращение субъекта ПДн (или его представителя), либо
запрос уполномоченного органа. Состав полей ЗЕРКАЛИТ бумажный журнал
legal/sources/internal/12-zhurnal-obrashcheniy.md (Правило №6 — один источник
истины на форму данных: колонки журнала и колонки БД не должны разойтись).
Журнал не заводится программно из этой таблицы (и наоборот) — оператор ведёт
журнал по факту зарегистрированных обращений, здесь только сами обращения.
"""
from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class UserConsent(Base):
    __tablename__ = "user_consents"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable: согласие логически привязано к попытке регистрации, а не
    # обязательно к уже существующему пользователю (см. docstring файла).
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    document_version = Column(String(255), nullable=False)
    # Перечень slug'ов документов, на которые дано согласие одним действием
    # (напр. ["privacy", "consent"]) — фронт шлёт один флажок на пакет из
    # нескольких документов сразу (см. LEGAL_VERSION в
    # frontend/src/legal/documents.generated.ts).
    documents = Column(JSONB, nullable=False, default=list)
    accepted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    # Точка получения согласия. Пока единственное значение — 'registration',
    # задел на другие точки (напр. повторное согласие в личном кабинете).
    source = Column(String(50), nullable=False, default="registration", server_default="registration")
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    withdrawal_reason = Column(Text, nullable=True)

    user = relationship("User")


class PersonalDataRequestType:
    """Тип обращения субъекта ПДн — см. п.2 «Суть обращения» журнала."""
    INFO = "info"           # предоставление сведений о наличии/составе ПДн
    CORRECTION = "correction"  # уточнение персональных данных
    WITHDRAWAL = "withdrawal"  # отзыв согласия на обработку
    DELETION = "deletion"      # прекращение обработки / уничтожение ПДн

    ALL = (INFO, CORRECTION, WITHDRAWAL, DELETION)


class PersonalDataRequestStatus:
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    REJECTED = "rejected"

    ALL = (NEW, IN_PROGRESS, ANSWERED, REJECTED)


class PersonalDataRequest(Base):
    """Обращение субъекта ПДн. Регистрация ТОЛЬКО фиксирует обращение —
    удаление/иное действие выполняет оператор вручную по итогам рассмотрения
    (см. docstring routers/legal.py), это не автоматический пайплайн.

    Колонки 1:1 к графам журнала 12-zhurnal-obrashcheniy.md:
    № (id), Дата поступления (received_at), От кого поступило
    (requester_name + email/контакт для ответа — reply_contact), Способ
    поступления (не отдельная графа для наших целей — обращение всегда
    приходит через форму сайта, source зафиксирован константой ниже),
    Суть обращения (request_type + message), Срок ответа (response_due_at),
    Дата ответа (answered_at), Содержание ответа/принятое решение
    (response_text), Кто исполнил (handled_by_user_id).
    """
    __tablename__ = "personal_data_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requester_name = Column(String(255), nullable=True)
    # Контакт для ответа (email или телефон, как ввёл обратившийся) —
    # соответствует графе «От кого поступило» журнала в части реквизита связи.
    reply_contact = Column(String(255), nullable=False)
    request_type = Column(String(20), nullable=False)  # PersonalDataRequestType
    message = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    response_due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default=PersonalDataRequestStatus.NEW,
                     server_default=PersonalDataRequestStatus.NEW)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    response_text = Column(Text, nullable=True)
    handled_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    handled_by = relationship("User", foreign_keys=[handled_by_user_id])
