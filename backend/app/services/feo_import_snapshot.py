"""Этап 1 импорта ФЭО: снимок дерева категорий ДО импорта.

Перенесено из тела `_do_feo_import` (было ~строки 213–269 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5).
Нужен и для отчёта «несопоставленные узлы» (feo_import_report.py), и для
фазы переезда/удаления N2б (feo_import_remap.py) — переезд/удаление должны
опираться на состояние дерева ДО того, как основной цикл (feo_import_apply.py)
его изменит.

В оригинале `_get_root_id`/`_full_path`/`_subtree_ids_local` были замыканиями
над `existing_by_id`/`existing_children` (локальными переменными
`_do_feo_import`). Здесь это модульные функции, чтобы ими могли пользоваться
несколько файлов-этапов без копий (Правило №6) — `existing_by_id`/
`existing_children` переданы явным первым параметром вместо захвата
из замыкания; логика тела функций не менялась.
"""
import re

from app.models.feo_category import FeoCategory


def snapshot_tree_before(state) -> None:
    """Строит state.existing_by_id / state.existing_children из state.existing_cats."""
    existing_cats = state.existing_cats
    existing_by_id: dict[int, FeoCategory] = {c.id: c for c in existing_cats}
    existing_children: dict[int, list[int]] = {}
    for c in existing_cats:
        if c.parent_id is not None:
            existing_children.setdefault(c.parent_id, []).append(c.id)
    state.existing_by_id = existing_by_id
    state.existing_children = existing_children


def get_root_id(existing_by_id: dict, cat_id: int) -> int:
    cur = existing_by_id.get(cat_id)
    if cur is None:
        return cat_id
    visited: set[int] = set()
    while cur.parent_id is not None and cur.parent_id in existing_by_id:
        if cur.id in visited:
            break
        visited.add(cur.id)
        cur = existing_by_id[cur.parent_id]
    return cur.id


def full_path(existing_by_id: dict, cat_id: int) -> str:
    chain: list[str] = []
    cur = existing_by_id.get(cat_id)
    visited: set[int] = set()
    while cur is not None and cur.id not in visited:
        chain.append(cur.name)
        visited.add(cur.id)
        if cur.parent_id is None:
            break
        cur = existing_by_id.get(cur.parent_id)
    return " / ".join(reversed(chain))


def subtree_ids(existing_children: dict, root_id: int) -> list[int]:
    ids = [root_id]
    stack = [root_id]
    while stack:
        cur_id = stack.pop()
        for ch_id in existing_children.get(cur_id, []):
            ids.append(ch_id)
            stack.append(ch_id)
    return ids


def _strip_num(s: str) -> str:
    return re.sub(r'^\s*\d+([.\)]\d+)*[.\)]?\s*', '', s).strip()


def canon_path(path: str, *, lower: bool, yo: bool) -> str:
    out = []
    for seg in path.split(" / "):
        s = _strip_num(seg)
        if lower:
            s = re.sub(r'\s+', ' ', s.lower()).strip()
        if yo:
            s = s.replace('ё', 'е')
        out.append(s)
    return " / ".join(out)
