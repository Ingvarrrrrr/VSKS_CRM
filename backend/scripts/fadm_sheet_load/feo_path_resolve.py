"""🟡 ПЕРЕНЕСЕНО 16.10.2026 в app/services/feo_path_resolve.py (план
composed-noodling-lampson.md, ПРАВИЛО №6 — единственное место этой логики,
используется и мастером «Импорт факта», и этим скриптом). Этот файл — тонкий
re-export shim для обратной совместимости существующих импортов скрипта
(`from .feo_path_resolve import FeoTree, load_feo_tree, resolve_feo_path`) —
никакой логики здесь больше нет."""
from app.services.feo_path_resolve import (  # noqa: F401
    CategoryNode,
    FeoTree,
    ResolvedPath,
    load_feo_tree,
    names_match,
    normalize_feo_name,
    resolve_feo_path,
    resolve_feo_path4,
)
