"""
Разовый запрос местоположения сотрудника через мессенджер — владелец
(организация спасателей), 2026-09.

Контекст: 32 из 41 сотрудников не привязали ни один мессенджер, и от
большинства остальных нельзя дождаться, что они сами включат смену
(см. staff_shift.py). Диспетчер жмёт «Запросить местоположение» у конкретного
человека — дальше это РАЗОВАЯ операция, не трансляция.

Каналы доставки (2026-09, обновлено по требованию владельца): **push —
основной канал**, Telegram/MAX — запасные, включаются ТОЛЬКО если push не
доставлен (нет подписки, подписка мертва, ошибка отправки). Порядок и логика
отката — services/staff_location_requests.py::create_request. Push открывает
экран подтверждения в самом приложении (frontend/src/views/staff/
LocationRequestRespondView.vue) с кнопками «Отправить» / «Отказаться»;
Telegram — кнопку геопозиции в реплай-клавиатуре; MAX — только текстовая
просьба (см. services/staff_location_requests.py, почему кнопка не сделана).

Отдельная сущность от StaffShift/StaffLocationPoint: запрос — это переписка
с сотрудником (кто попросил, когда, ответил ли), а не факт присутствия на
смене. Точка-ответ (point_id) кладётся в ту же таблицу staff_location_points,
что и точки со смены — с другим source (см. staff_location.py), чтобы карта
«Где люди» могла показать обоих без дублирования модели точки.

Статусы (status):
  sent      — запрос отправлен (хотя бы в один канал), ждём ответа.
  answered  — сотрудник прислал геопозицию, point_id заполнен.
  declined  — сотрудник ЯВНО отказался (кнопка «Отказаться» на экране
              подтверждения push) — отличается от "не увидел": диспетчер
              должен видеть отказ, а не думать, что запрос просто не дошёл.
  expired   — истёк срок жизни запроса (см. _REQUEST_TTL в services/
              staff_location_requests.py) — вычисляется ЛЕНИВО (как cleanup
              в staff_location.py): при чтении/попытке ответить на запрос
              со статусом 'sent' и просроченным expires_at статус
              перезаписывается в БД, без фонового джоба.
  cancelled — диспетчер отменил запрос вручную до ответа.

Отправка без единого канала (ни push-подписки, ни Telegram, ни MAX) у
сотрудника вообще не создаёт запись — роутер отвечает 400 с понятной
причиной ДО INSERT (см. services/staff_location_requests.py::create_request).
Поля-состояния "отправка не удалась" в модели поэтому нет — сам факт
создания строки означает, что хотя бы один канал был доступен И реально
использован для отправки (channels_sent — то, что СРАБОТАЛО, а не просто
было предпринято; см. докстринг create_request про крайний случай, когда
единственным доступным каналом был push и его отправка не удалась).
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class StaffLocationRequest(Base):
    __tablename__ = "staff_location_requests"

    id = Column(Integer, primary_key=True, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), nullable=False, default="sent", server_default="sent")
    # Какими каналами СРАБОТАЛА отправка: "push", "telegram", "max" или их
    # сочетание через запятую (обычно один — push первый, мессенджеры только
    # запасные, см. докстринг модуля и create_request).
    channels_sent = Column(String(40), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    # Точка-ответ в staff_location_points. ON DELETE SET NULL — если точку
    # когда-нибудь удалит фоновая очистка (30 дней, см. staff_location.py),
    # сам факт "ответил тогда-то" в истории запроса не пропадает.
    point_id = Column(Integer, ForeignKey("staff_location_points.id", ondelete="SET NULL"), nullable=True)

    requested_by = relationship("User", foreign_keys=[requested_by_id])
    user = relationship("User", foreign_keys=[user_id])
    point = relationship("StaffLocationPoint", foreign_keys=[point_id])

    __table_args__ = (
        # "Есть ли у пользователя активный запрос" — основной паттерн выборки
        # (создание нового запроса, поиск при ответе через вебхук).
        Index("ix_staff_location_requests_user_status", "user_id", "status"),
        Index("ix_staff_location_requests_created_at", "created_at"),
    )
