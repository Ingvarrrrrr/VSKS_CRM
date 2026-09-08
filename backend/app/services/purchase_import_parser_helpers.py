"""Purchase import — small per-row/per-cell helpers and ФЭО-path resolution.

Split out of `services/purchase_import_parser.py` (refactor, 2026-09): these
helpers are used exclusively by `purchase_import_parser_group._parse_and_group`
(via the facade) — moved here verbatim to keep that file under the
modularity guideline (ПРАВИЛО №5). `to_decimal` (ПРАВИЛО №6: single Decimal
coercion source) is imported from `app.utils.numbers`, not reimplemented.
"""
import re as _re
from datetime import datetime
from typing import Dict, List

from app.models.feo_category import FeoCategory
from app.utils.numbers import to_decimal
from app.utils.text import normalize_feo_name


def _make_cell_helper(col_idx: Dict[str, int]):
    def cell(row, field):
        idx = col_idx.get(field)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None
    return cell


_to_dec = to_decimal


def _to_date_val(v):
    if v is None:
        return None
    if hasattr(v, "date"):
        return v.date()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except Exception:
            pass
    return None


def _build_feo_index(feo_rows: List[FeoCategory], sid: int) -> Dict[int, FeoCategory]:
    """Return {id: FeoCategory} for categories belonging to given subsidy."""
    return {f.id: f for f in feo_rows if f.subsidy_id == sid}


_norm_feo = normalize_feo_name


async def _resolve_feo_levels(
    levels: List[str],
    sid: int,
    feo_index: Dict[int, FeoCategory],
    db=None,
    feo_rows_all=None,
    create_missing: bool = False,
    simulate: bool = False,
    pending_created: list | None = None,
    _sim_id_counter: list | None = None,
) -> tuple:
    """
    Walk the FEO tree of THIS subsidy using ordered level values.
    levels = non-empty strings in order (e.g. ['Снаряжение', 'Одежда', 'Кепи']).

    - Схлопывает соседние дубли (нормализованные): если levels[i] == levels[i-1], выбрасывает дубль.
    - Матчинг: сначала точное совпадение по нормализованным именам, затем вхождение.
    - При create_missing=True и наличии db: создаёт отсутствующие узлы автоматически.
    - При simulate=True: НЕ трогает БД, создаёт узлы-заглушки с отрицательными id,
      собирает в pending_created список {level, name, path} для отображения в превью.
    Returns (feo_category_id, error_message_or_None).
    """
    if not levels:
        return None, "Не указан ни один уровень ФЭО"

    # Схлопнуть соседние дубли по нормализованному значению
    deduped: List[str] = [levels[0]]
    for lv in levels[1:]:
        if _norm_feo(lv) != _norm_feo(deduped[-1]):
            deduped.append(lv)
    levels = deduped

    roots = [f for f in feo_index.values() if f.parent_id is None or f.parent_id not in feo_index]
    current_candidates = roots
    current_node = None
    # Track path for pending_created
    path_parts: List[str] = []

    for level_idx, part in enumerate(levels):
        nn_needle = _norm_feo(part)
        matched = None
        # exact match по нормализованным
        for candidate in current_candidates:
            if _norm_feo(candidate.name) == nn_needle:
                matched = candidate
                break
        # substring fallback по нормализованным
        if matched is None:
            for candidate in current_candidates:
                nn_cand = _norm_feo(candidate.name)
                if nn_needle and nn_needle in nn_cand:
                    matched = candidate
                    break
                if nn_cand and nn_cand in nn_needle:
                    matched = candidate
                    break
        # Автосоздание / симуляция, если не найдено
        if matched is None:
            if create_missing and db is not None:
                parent_id = current_node.id if current_node is not None else None
                # level = 1-based depth
                depth = level_idx + 1
                new_node = FeoCategory(
                    subsidy_id=sid,
                    parent_id=parent_id,
                    level=depth,
                    name=part,  # оригинальное имя из файла (с префиксом)
                    sort_order=None,
                    is_active=True,
                )
                db.add(new_node)
                await db.flush()
                # Добавляем в индекс и в общий список
                feo_index[new_node.id] = new_node
                if feo_rows_all is not None:
                    feo_rows_all.append(new_node)
                matched = new_node
            elif simulate:
                # Режим симуляции: создаём заглушку в памяти с отрицательным id
                if _sim_id_counter is None:
                    _sim_id_counter = [-1]
                sim_id = _sim_id_counter[0]
                _sim_id_counter[0] -= 1
                parent_id = current_node.id if current_node is not None else None
                depth = level_idx + 1
                stub_node = FeoCategory(
                    subsidy_id=sid,
                    parent_id=parent_id,
                    level=depth,
                    name=part,
                    sort_order=None,
                    is_active=True,
                )
                # Присваиваем отрицательный id без записи в БД
                stub_node.id = sim_id  # type: ignore[assignment]
                feo_index[sim_id] = stub_node
                if feo_rows_all is not None:
                    feo_rows_all.append(stub_node)
                # Собираем в коллектор (без дублей по полному пути)
                full_path = " / ".join(path_parts + [part])
                if pending_created is not None:
                    existing_paths = {e["path"] for e in pending_created}
                    if full_path not in existing_paths:
                        pending_created.append({
                            "level": depth,
                            "name": part,
                            "path": full_path,
                        })
                matched = stub_node
            else:
                return None, f"ФЭО не найдено на уровне {level_idx + 1}: '{part}'"
        path_parts.append(part)
        current_node = matched
        current_candidates = [f for f in feo_index.values() if f.parent_id == matched.id]

    if current_node is None:
        return None, "ФЭО не найдено"
    return current_node.id, None


async def _resolve_feo_path(
    path_str: str,
    feo_index: Dict[int, FeoCategory],
    sid: int = 0,
    db=None,
    feo_rows_all=None,
    create_missing: bool = False,
    simulate: bool = False,
    pending_created: list | None = None,
    _sim_id_counter: list | None = None,
) -> tuple:
    """
    Backward-compat: resolve old single path string (parts separated by ' / ' or '>').
    Returns (feo_category_id, error_message_or_None).
    """
    parts = [p.strip() for p in _re.split(r"\s*/\s*|\s*>\s*", path_str) if p.strip()]
    if not parts:
        return None, "Пустой путь ФЭО"
    return await _resolve_feo_levels(
        parts, sid, feo_index,
        db=db, feo_rows_all=feo_rows_all, create_missing=create_missing,
        simulate=simulate, pending_created=pending_created, _sim_id_counter=_sim_id_counter,
    )


def _find_payments_sheet(wb):
    """Find the «Платежи» worksheet (case-insensitive match on 'платеж')."""
    for sheet in wb.worksheets:
        if "платеж" in sheet.title.lower():
            return sheet
    return None
