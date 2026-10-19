"""export_columns_catalog.py — общий механизм выбора столбцов выгрузки
(ПРАВИЛО №6, задача владельца 20.10.2026 — вынесено из
app.services.plan_graph_export_columns, чтобы app.services.feo_export_columns
переиспользовал тот же алгоритм вместо второй копии).

Любая таблица столбцов — список кортежей (key, label, group, width, default)
в фиксированном порядке вывода. Функции здесь ТОЛЬКО читают эту таблицу,
ничего не хранят сами — второй источник правды о порядке/подписях не заводится.
"""
from __future__ import annotations

from typing import Iterable, Optional


def columns_catalog(columns: list[tuple]) -> list[dict]:
    """[{key,label,group,default}] для GET .../export/columns — порядок
    фиксирован, совпадает с порядком вывода в файле."""
    return [
        {"key": k, "label": label, "group": group, "default": is_default}
        for k, label, group, _w, is_default in columns
    ]


def resolve_selected_keys(
    columns: list[tuple], requested: Optional[str], *, always: Iterable[str] = (),
) -> list:
    """Парсит query-параметр `columns` (через запятую) в список ключей в
    ФИКСИРОВАННОМ порядке таблицы `columns`; неизвестные ключи игнорируются;
    ключи из `always` присутствуют всегда. Пусто/None → только default=True."""
    all_keys = [k for k, *_ in columns]
    default_keys = [k for k, _l, _g, _w, is_default in columns if is_default]
    if not requested:
        return list(default_keys)
    wanted = {c.strip() for c in requested.split(",") if c.strip()}
    wanted.update(always)
    selected = [k for k in all_keys if k in wanted]
    return selected or list(default_keys)


def headers_and_widths(by_key: dict, selected_keys: list) -> tuple:
    """(headers, widths) для выбранных ключей, в их порядке. `by_key` —
    {key: (label, group, width)}."""
    headers = [by_key[k][0] for k in selected_keys]
    widths = [by_key[k][2] for k in selected_keys]
    return headers, widths


def column_index(selected_keys: list, key: str) -> Optional[int]:
    """1-based индекс столбца `key` среди выбранных, или None, если столбец
    не выбран."""
    try:
        return selected_keys.index(key) + 1
    except ValueError:
        return None
