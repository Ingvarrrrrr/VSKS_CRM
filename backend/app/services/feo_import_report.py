"""Этап 5 импорта ФЭО: отчёт «несопоставленные узлы» — ТОЛЬКО анализ, без
мутаций/перепривязок.

Перенесено из тела `_do_feo_import` (было ~строки 1068–1135 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики. Дерево родитель→дети (`existing_by_id`/`existing_children`,
собранные feo_import_snapshot.snapshot_tree_before) и её хелперы
(`get_root_id`/`full_path`/`subtree_ids`/`canon_path`) — те же самые функции,
что использует feo_import_apply.py и feo_import_remap.py (Правило №6, один
источник, не заводить вторую копию обхода дерева).

`_feo_category_load` импортируется ЛОКАЛЬНО (внутри функции, не на уровне
модуля) из app.routers.feo_import — тот модуль импортирует `_do_feo_import`
из фасада (app.services.feo_import_engine) на уровне модуля, top-level
импорт в обе стороны дал бы цикл (тот же приём, что в оригинале).
"""
from app.services.feo_import_snapshot import canon_path, full_path, get_root_id
from app.services.feo_import_snapshot import subtree_ids as _subtree_ids_of


async def build_unmatched_report(state) -> None:
    from app.routers.feo_import import _feo_category_load

    db = state.db
    existing_cats = state.existing_cats
    existing_by_id = state.existing_by_id
    existing_children = state.existing_children
    seen_ids = state.seen_ids
    seen_roots = state.seen_roots
    new_paths = state.new_paths

    # --- Отчёт "несопоставленные узлы": ТОЛЬКО анализ, без мутаций/перепривязок ---
    # Дерево родитель→дети (existing_by_id/existing_children) и хелперы
    # (get_root_id/full_path/subtree_ids/canon_path) определены в
    # feo_import_snapshot.py — они нужны и здесь, и в фазе переезда/удаления
    # (feo_import_remap.py).
    unmatched: list[dict] = []
    if seen_roots:
        candidates = [
            c for c in existing_cats
            if c.id not in seen_ids and get_root_id(existing_by_id, c.id) in seen_roots
        ]
        # Предрасчёт канонических форм всех new_paths (для подсказок)
        _np_nonum = [(np, canon_path(np, lower=False, yo=False)) for np in new_paths]
        _np_norm = [(np, canon_path(np, lower=True, yo=False)) for np in new_paths]
        _np_yo = [(np, canon_path(np, lower=True, yo=True)) for np in new_paths]

        for cand in candidates:
            cand_path = full_path(existing_by_id, cand.id)
            subtree_ids = _subtree_ids_of(existing_children, cand.id)
            load = await _feo_category_load(subtree_ids, db)
            # own_data (свой план/финансирование/поля ФЭО) считается наравне со
            # внешними ссылками — узел с собственными данными не «пустой», даже
            # если на него никто не ссылается (см. own_data в _feo_category_load,
            # причина — боевая пропажа категории (DONGFENG) JUNFENG K33).
            has_refs = any(load[k] for k in (
                "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
                "own_data",
            ))
            kind = "needs_mapping" if has_refs else "empty"

            suggestion = None
            suggestion_reason = None
            suggestion_candidates: list[str] | None = None
            if kind == "needs_mapping":
                cand_nonum = canon_path(cand_path, lower=False, yo=False)
                for np, np_c in _np_nonum:
                    if np != cand_path and np_c == cand_nonum:
                        suggestion, suggestion_reason = np, "отличается нумерацией"
                        break
                if suggestion is None:
                    cand_norm = canon_path(cand_path, lower=True, yo=False)
                    for np, np_c in _np_norm:
                        if np != cand_path and np_c == cand_norm:
                            suggestion, suggestion_reason = np, "отличается регистром или пробелами"
                            break
                if suggestion is None:
                    cand_yo = canon_path(cand_path, lower=True, yo=True)
                    for np, np_c in _np_yo:
                        if np != cand_path and np_c == cand_yo:
                            suggestion, suggestion_reason = np, "отличается ё/е"
                            break
                if suggestion is None:
                    # Уровень вложенности мог измениться (в файле появился/пропал
                    # промежуточный узел) — тогда полный путь никогда не совпадёт
                    # ни по одной из трёх канонизаций выше, хотя лист (последний
                    # сегмент) и корень (первый сегмент) — те же самые. Пример
                    # боевого случая: «Организация питания / ИРП/Сухпай» (в БД,
                    # 2 уровня) vs «Организация питания / Питание.../ИРП/Сухпай»
                    # (в новом файле, 3 уровня). Сопоставляем по (корень, лист);
                    # предлагаем ТОЛЬКО если кандидат в new_paths ровно один —
                    # неоднозначность не разрешаем автоматически.
                    cand_yo2 = canon_path(cand_path, lower=True, yo=True)
                    cand_segs = cand_yo2.split(" / ")
                    if len(cand_segs) >= 2:
                        cand_root, cand_leaf = cand_segs[0], cand_segs[-1]
                        _leaf_matches: list[str] = []
                        for np, np_c in _np_yo:
                            if np == cand_path:
                                continue
                            np_segs = np_c.split(" / ")
                            if len(np_segs) >= 2 and np_segs[0] == cand_root and np_segs[-1] == cand_leaf:
                                if np not in _leaf_matches:
                                    _leaf_matches.append(np)
                        if len(_leaf_matches) == 1:
                            suggestion, suggestion_reason = _leaf_matches[0], "отличается уровнем вложенности"
                        elif len(_leaf_matches) > 1:
                            suggestion_candidates = _leaf_matches

            unmatched.append({
                "id": cand.id,
                "path": cand_path,
                "kind": kind,
                "suggestion": suggestion,
                "suggestion_reason": suggestion_reason,
                "suggestion_candidates": suggestion_candidates,
                "load": {
                    "purchases": load["purchases"],
                    "purchase_items": load["purchase_items"],
                    "wishes": load["wishes"],
                    "wish_items": load["wish_items"],
                    "products": load["products"],
                    "feo_planned_items": load["feo_planned_items"],
                },
                "blocking_purchases": load["blocking_purchases"],
            })

    state.unmatched = unmatched
