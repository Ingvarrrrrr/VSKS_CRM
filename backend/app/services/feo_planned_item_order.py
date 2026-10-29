# -*- coding: utf-8 -*-
"""feo_planned_item_order.py — ЕДИНЫЙ порядок плановых позиций (ПРАВИЛО №6:
один ключ сортировки, не вторая реализация в каждом месте, где позиции
выводятся списком).

Порядок = ручная перестановка стрелками (sort_order), затем строка файла
загрузки (source_row), затем порядок создания (id) — все NULL идут последними
на своём уровне (легаси/вручную заведённые позиции без source_row/sort_order).
"""
from __future__ import annotations

from app.models.feo_planned_item import FeoPlannedItem


def planned_item_order_by():
    """ORDER BY clauses для запроса FeoPlannedItem — sort_order NULLS LAST,
    затем source_row NULLS LAST, затем id. Использовать везде, где плановые
    позиции выводятся построчно (список категории, отчёты, окно «из чего
    сложено» карточки «Запланировано») — единственное место, где этот порядок
    определён."""
    return (
        FeoPlannedItem.sort_order.nulls_last(),
        FeoPlannedItem.source_row.nulls_last(),
        FeoPlannedItem.id,
    )


def planned_item_sort_key(sort_order, source_row, id):
    """Тот же порядок, что planned_item_order_by(), но для сортировки в
    памяти (Python list.sort/sorted) — None идёт ПОСЛЕДНИМ на каждом уровне,
    как и NULLS LAST в SQL."""
    return (
        sort_order is None, sort_order if sort_order is not None else 0,
        source_row is None, source_row if source_row is not None else 0,
        id,
    )
