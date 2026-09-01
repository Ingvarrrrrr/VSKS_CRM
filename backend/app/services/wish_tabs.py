"""Накопительные множества статусов для вкладок «Заявки на закупку».

Жалоба владельца (сессия 2026-09-01): вкладка «Все заявки» показывала меньше
записей, чем «Конвертированные», потому что дефолтный фильтр списка
(``GET /wishes/`` без ``status``) исключает ``converted`` — так задумано для
других экранов (см. ``list_wishes`` в ``app/routers/wishes.py``), но фронт
использовал ЭТОТ путь и для «Все» на вкладке заявок.

Решение владельца: каждая вкладка — НАКОПИТЕЛЬНАЯ цепочка, включающая всё, что
когда-либо прошло через это состояние, а не точное совпадение статуса.

Фактический поток статусов (проверено по коду, 2026-09-01):
    draft -> submitted -> approved -> converted
                        \\-> rejected
                        \\-> converted (approve-distribution может конвертировать
                            прямо из submitted/draft, минуя явный статус
                            'approved' — см. approve_distribution и
                            force_wish_status в app/routers/wishes.py). Это не
                            ломает накопительные множества ниже: они собраны по
                            ТЕКУЩЕМУ статусу записи, а не по истории переходов,
                            и 'converted' — подмножество и 'submitted', и
                            'approved' в любом случае.

Других значений wish.status в коде нет (Wish.status — Column(String(30),
default='draft'); force_wish_status ограничивает ручное переключение тем же
пятиэлементным набором).
"""
from __future__ import annotations

# Порядок ключей значим только для чтения — код опирается на набор (set), а не
# на порядок словаря.
WISH_TAB_STATUS_SETS: dict[str, set[str]] = {
    "draft": {"draft"},
    "submitted": {"submitted", "approved", "rejected", "converted"},
    "approved": {"approved", "converted"},
    "rejected": {"rejected"},
    "converted": {"converted"},
    "all": {"draft", "submitted", "approved", "rejected", "converted"},
}


def wish_tab_statuses(tab: str) -> set[str]:
    """Множество статусов, попадающих во вкладку ``tab``.

    Неизвестное имя вкладки трактуется как «Все» (безопасный дефолт — шире,
    не уже, чтобы не прятать записи молча).
    """
    return WISH_TAB_STATUS_SETS.get(tab, WISH_TAB_STATUS_SETS["all"])
