"""Этап 6 импорта ФЭО: N2б — переезд (remap) + удаление опустевших старых
узлов. Выполняется ТОЛЬКО при apply_remap=True — обычная загрузка (без
явного согласия из мастера сопоставления) уже сделала только анализ
(feo_import_report.py), ничего не переносит и не удаляет.

Перенесено из тела `_do_feo_import` (было ~строки 1136–1235 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики. Обязательно ДО dry_run rollback/commit (см. оркестратор
feo_import_core.py) — все строки путей материализуются в обычные str/dict,
пока ORM-объекты ещё не просрочены.

`_full_path`/`_subtree_ids_local` заменены на модульные
`feo_import_snapshot.full_path`/`subtree_ids` (Правило №6 — тот же helper,
что и в feo_import_apply.py/feo_import_report.py, не вторая копия обхода
дерева). `_feo_category_load`/`_relink_feo_category` импортируются ЛОКАЛЬНО
(как и в оригинале) — тот же приём против циклического импорта.
"""
from app.models.feo_category import FeoCategory
from app.routers import feo_categories as fc
from app.services.feo_import_snapshot import full_path
from app.services.feo_import_snapshot import subtree_ids as _subtree_ids_of


async def remap_and_prune(state) -> None:
    from app.routers.feo_import import _feo_category_load, _relink_feo_category

    db = state.db
    apply_remap = state.apply_remap
    unmatched = state.unmatched
    errors = state.errors
    skipped_details = state.skipped_details
    remap_list = state.remap_list
    new_path_cats = state.new_path_cats
    seen_ids = state.seen_ids
    warnings = state.warnings
    cat_cache = state.cat_cache
    existing_by_id = state.existing_by_id
    existing_children = state.existing_children

    # --- N2б: переезд (remap) + удаление опустевших старых узлов ---
    # Обязательно ДО dry_run rollback/commit — все строки путей ниже нужно
    # материализовать в обычные str/dict, пока ORM-объекты ещё не просрочены.
    # Выполняется ТОЛЬКО при apply_remap=True (см. docstring) — обычная
    # загрузка (без явного согласия из мастера сопоставления) делает только
    # анализ unmatched/new_paths выше, ничего не переносит и не удаляет.
    relinked_count = 0
    deleted_count = 0
    remap_applied: list[dict] = []
    deleted_details: list[dict] = []
    remap_aborted_reason: str | None = None

    if apply_remap:
        _unmatched_ids = {u["id"] for u in unmatched}

        if errors:
            remap_aborted_reason = "переезд отменён: в файле есть ошибки"
        elif any(sd.get("reason") == "не указана субсидия назначения" for sd in skipped_details):
            remap_aborted_reason = "переезд отменён: часть строк без субсидии назначения"
        elif not seen_ids:
            remap_aborted_reason = "переезд отменён: файл не описал ни одного узла"

        _resolved_remap: list[tuple[int, FeoCategory, str]] = []
        if remap_aborted_reason is None:
            for _rm in remap_list:
                _old_id = _rm["old_id"]
                _new_path = _rm["new_path"]
                if _old_id not in _unmatched_ids:
                    remap_aborted_reason = f"переезд отменён: узел не найден среди несопоставленных (id={_old_id})"
                    break
                _new_cat = new_path_cats.get(_new_path)
                if _new_cat is None or _new_cat.id is None:
                    remap_aborted_reason = f"переезд отменён: цель сопоставления не найдена в новой разбивке: «{_new_path}»"
                    break
                _resolved_remap.append((_old_id, _new_cat, _new_path))

        if remap_aborted_reason is None:
            # Шаг A — применить переезды. Пути берём СЕЙЧАС (пока объекты живы).
            for _old_id, _new_cat, _new_path in _resolved_remap:
                _old_path = full_path(existing_by_id, _old_id)
                _counts = await _relink_feo_category(_old_id, _new_cat.id, db)
                relinked_count += sum(_counts.values())
                remap_applied.append({
                    "old_path": _old_path,
                    "new_path": _new_path,
                    "counts": _counts,
                })

            # Шаг B — удалить опустевшие несопоставленные узлы (кроме тех, кого
            # файл всё-таки назвал где-то в поддереве — их каскадом не трогаем).
            already_deleted: set[int] = set()
            # обходим от корня к листьям (по глубине path), иначе ребёнок удалится раньше родителя и родитель останется пустым висяком
            _unmatched_by_depth = sorted(unmatched, key=lambda _c: _c["path"].count(" / "))
            for _cand in _unmatched_by_depth:
                _cand_id = _cand["id"]
                if _cand_id in already_deleted:
                    continue
                subtree = _subtree_ids_of(existing_children, _cand_id)
                if any(_sid in already_deleted for _sid in subtree):
                    continue
                if any(_sid in seen_ids for _sid in subtree):
                    continue
                load = await _feo_category_load(subtree, db)
                _real_refs = any(load[k] for k in (
                    "purchases", "purchase_items", "wishes", "wish_items", "products", "feo_planned_items",
                ))
                # own_data (свой план/финансирование/поля ФЭО) считается наравне со
                # внешними ссылками — узел с собственными данными НЕ удаляется, даже
                # если в файле его нет и ссылок на него нет. Боевая причина: категория
                # «(DONGFENG) JUNFENG K33» дважды исчезала с прода — в ней был план
                # (planned_quantity/planned_amount) на 10 130 000, но ссылок не было,
                # и старая проверка has_refs их не видела, поэтому узел молча удалялся.
                has_refs = _real_refs or bool(load.get("own_data"))
                if has_refs:
                    if not _real_refs:
                        warnings.append({
                            "kind": "kept_has_own_plan",
                            "row": None,
                            "name": _cand["path"],
                            "message": (
                                f"Категория «{_cand['path']}» не удалена: в ней есть собственный план или "
                                f"финансирование по ФЭО, хотя в файле её нет. Проверьте, не потерялась ли строка в файле"
                            ),
                        })
                    continue
                for _sid in subtree:
                    if _sid == _cand_id:
                        deleted_details.append({"path": _cand["path"], "reason": "нет в новом файле, ссылок нет"})
                    else:
                        deleted_details.append({"path": full_path(existing_by_id, _sid), "reason": f"внутри удаляемого «{_cand['path']}»"})
                await fc._purge_feo_categories(subtree, db)
                deleted_count += len(subtree)
                already_deleted.update(subtree)

            # Шаг C — вычистить cat_cache от удалённых id, чтобы ниже по коду
            # (если он появится) не переиспользовать протухшие объекты.
            if already_deleted:
                for _k in [k for k, c in cat_cache.items() if c.id in already_deleted]:
                    del cat_cache[_k]

    state.relinked_count = relinked_count
    state.deleted_count = deleted_count
    state.remap_applied = remap_applied
    state.deleted_details = deleted_details
    state.remap_aborted_reason = remap_aborted_reason
