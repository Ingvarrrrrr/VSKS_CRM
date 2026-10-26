"""Единственное место, где решается "новое описание заметно короче старого"
и как объединять старое с новым, когда это так (ПРАВИЛО №6, задача 1,
2026-10-26, владелец — повод: 41 товар с потерей техданных в прошлом dry-run
rebuild_descriptions_from_sources.py при безусловной замене описания файловым).

Используется:
  - backend/app/services/products_import_apply.py (замена описания при
    supplier_description/effective_replace_descriptions);
  - backend/scripts/rebuild_descriptions_from_sources.py (--apply и отчёты).

Вторую реализацию порога "короче" или вторую сборку "старое+новое" в проекте
не заводить — импортировать отсюда.
"""
from app.services.products_import_match import norm_key

# Мерило «заметно короче» (владелец, 2026-10-26, перенесено без изменений из
# прежнего backend/scripts/rebuild_descriptions_from_sources.py::_is_shorter)
# — новое описание короче старого хотя бы на 20% по числу непробельных
# символов.
_SHORTER_RATIO = 0.8


def is_new_description_shorter(old: str, new: str) -> bool:
    """True, если `new` заметно (на >=20% по числу непробельных символов)
    короче `old`. Пустое `old` — не считается (замена пустого описания не
    теряет ничего, значит "короче" не применимо)."""
    old_len = len((old or "").replace(" ", "").replace("\n", ""))
    new_len = len((new or "").replace(" ", "").replace("\n", ""))
    if old_len == 0:
        return False
    return new_len < old_len * _SHORTER_RATIO


def merge_missing_lines(old: str, new: str) -> str:
    """Объединяет старое описание с новым, когда новое заметно короче
    (см. is_new_description_shorter) — старое целиком сохраняется, в конец
    дописываются только те строки нового, которых по смыслу (norm_key) в
    старом ещё не было. Результат по построению никогда короче `old`.

    Пустое/отсутствующее `old` → возвращает `new` как есть (нет старого —
    нечего сохранять, обычная замена)."""
    if not (old or "").strip():
        return new

    old_lines = old.split("\n")
    new_lines = new.split("\n")

    seen_keys = {norm_key(line) for line in old_lines if norm_key(line)}
    appended = []
    for line in new_lines:
        key = norm_key(line)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        appended.append(line)

    if not appended:
        return old
    return "\n".join([*old_lines, *appended])
