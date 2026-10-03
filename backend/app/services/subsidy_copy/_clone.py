"""Общий хелпер клонирования ORM-строки (ПРАВИЛО №5/№6 — одна реализация для
всех копировщиков в этом пакете, а не ручной список полей в каждом файле).

copy_tree.py / copy_purchases.py используют ТОЛЬКО это — ручное перечисление
колонок означало бы, что новое поле модели (а их на Purchase/FeoPlannedItem/
PurchaseItem десятки, и они часто прибавляются) тихо не копируется в песочницу.
"""
from __future__ import annotations

from typing import Any, Iterable, Type, TypeVar

T = TypeVar("T")


def clone_row(obj: Any, model: Type[T], exclude: Iterable[str] = (), **overrides: Any) -> T:
    """Новый ORM-объект `model` со значениями всех колонок `obj`, кроме `id`
    и `exclude`; `overrides` применяются после (новые FK/сброшенные поля)."""
    exclude_set = {"id", *exclude}
    data = {
        col.name: getattr(obj, col.name)
        for col in obj.__table__.columns
        if col.name not in exclude_set
    }
    data.update(overrides)
    return model(**data)
