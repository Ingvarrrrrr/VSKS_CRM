#!/usr/bin/env python3
"""Генерирует frontend/src/data/dictionaries.json из бэкенда (Правило №6 —
один источник истины для справочников закупки и ключей прав доступа).

Источники (читаются статически через `ast`, БЕЗ импорта пакета `app` —
тот же приём, что в check_alembic_single_head.py: импорт `app` требует живых
env-переменных вроде SECRET_KEY и тянет всю цепочку моделей/БД, а этот скрипт
обязан работать в CI-джобе backend без Postgres и без .env):

  - backend/app/services/dictionaries.py — STATUS_LABELS, SUBSTATUS_LABELS,
    CONTRACT_TYPE_LABELS, PURCHASE_METHOD_LABELS, PURCHASE_BASIS_LABELS
    (простые словарные литералы верхнего уровня).
  - backend/app/routers/purchases.py — STATUS_ORDER (порядок статусов в
    канбане/фильтрах; см. GET /api/dictionaries/purchase, который использует
    тот же STATUS_ORDER — здесь НЕ дублируем значение, а не читаем эндпоинт).
  - backend/app/startup/permission_seeds.py — все action_key/description и
    tab_key/title, которые сиды создают через PermissionAction(...)/
    PermissionTab(...) (в т.ч. под function-local алиасами импорта вроде
    `PermissionAction as _PA29`, и внутри `for action_key, description in
    [...]:` циклов) — статический AST-разбор, см. _extract_permission_seeds().

Известное ограничение (см. отчёт агента K2/K3, сессия 2026-09-07): часть
action_key реально существующих на бэкенде (например 'publication.create',
'purchase_files.upload') заведена через alembic-миграции (baseline/
perm_seed_hotfix.sql), а не через permission_seeds.py, и в выгрузку не попадёт.
Это осознанно: alembic-миграции — история, их не переразбираем регексом/AST
задним числом. Такие ключи отмечены в отчёте отдельно, а не в этом файле.

Использование:
  python backend/scripts/export_dictionaries.py            — (пере)записать frontend/src/data/dictionaries.json
  python backend/scripts/export_dictionaries.py --check    — 0, если копия совпадает с источником; иначе 1

Exit code: 0 — ок; 1 — источник недоступен для --check и разошёлся с копией,
или ошибка разбора AST.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DICTIONARIES_SRC = BACKEND_DIR / "app" / "services" / "dictionaries.py"
PURCHASES_SRC = BACKEND_DIR / "app" / "routers" / "purchases.py"
PERMISSION_SEEDS_SRC = BACKEND_DIR / "app" / "startup" / "permission_seeds.py"
ITEM_FORMS_SRC = BACKEND_DIR / "app" / "services" / "item_forms.py"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
OUTPUT_PATH = FRONTEND_DIR / "src" / "data" / "dictionaries.json"
ITEM_FORMS_OUTPUT_PATH = FRONTEND_DIR / "src" / "data" / "item_forms.json"

DICT_NAMES = [
    "STATUS_LABELS",
    "SUBSTATUS_LABELS",
    "CONTRACT_TYPE_LABELS",
    "PURCHASE_METHOD_LABELS",
    "PURCHASE_BASIS_LABELS",
]

# item-forms-accommodation-transport.md: CONTRACT_FORM_LABELS живёт в
# dictionaries.py рядом с остальными словарями закупки — читаем тем же
# _extract_module_dicts, но отдельно от DICT_NAMES/dictionaries.json, т.к.
# идёт в свой файл item_forms.json (см. build_item_forms ниже).
CONTRACT_FORM_DICT_NAME = "CONTRACT_FORM_LABELS"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _extract_module_dicts(tree: ast.Module, names: list[str]) -> dict[str, dict]:
    """Top-level `NAME = { 'k': 'v', ... }` literal assignments."""
    found: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                found[target.id] = ast.literal_eval(node.value)
    missing = set(names) - set(found)
    if missing:
        raise ValueError(f"{DICTIONARIES_SRC.name}: не найдены словари {sorted(missing)}")
    return found


def _extract_status_order(tree: ast.Module) -> list[str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "STATUS_ORDER":
                return ast.literal_eval(node.value)
    raise ValueError(f"{PURCHASES_SRC.name}: STATUS_ORDER не найден")


def _literal_str(node: ast.expr | None):
    if node is None:
        return None
    try:
        val = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None
    return val if isinstance(val, str) else None


def _extract_permission_seeds(tree: ast.Module) -> tuple[dict[str, str], dict[str, str]]:
    """Разбирает все `async def _xxx()` в permission_seeds.py и достаёт
    action_key->description и tab_key->title, независимо от того, заданы ли
    они прямой строкой, через локальную константу (`ACTION_KEY = '...'`) или
    через `for k, desc in [(...), ...]:` + PermissionAction(action_key=k, description=desc).
    """
    actions: dict[str, str] = {}
    tabs: dict[str, str] = {}

    for func in tree.body:
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 1. Алиасы импорта PermissionAction/PermissionTab внутри функции
        #    (`from app.models.permission import PermissionAction as _PA29, ...`).
        alias_to_orig: dict[str, str] = {}
        for node in ast.walk(func):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in ("PermissionAction", "PermissionTab"):
                        alias_to_orig[alias.asname or alias.name] = alias.name

        # 2. Простые локальные строковые константы верхнего уровня функции
        #    (`ACTION_KEY = 'foo'`) — только прямые присваивания-операторы
        #    функции (не внутри for/if), поиск по всему телу через ast.walk
        #    (Assign может лежать и внутри try/with — этого достаточно, они
        #    не переопределяются циклами в этих функциях).
        local_consts: dict[str, str] = {}
        local_lists: dict[str, list[tuple]] = {}
        for node in ast.walk(func):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            s = _literal_str(node.value)
            if s is not None:
                local_consts[target.id] = s
                continue
            if isinstance(node.value, (ast.List, ast.Tuple)):
                items = []
                for elt in node.value.elts:
                    if isinstance(elt, (ast.Tuple, ast.List)):
                        vals = [_literal_str(e) for e in elt.elts]
                        items.append(tuple(vals))
                if items:
                    local_lists[target.id] = items

        # 3. `for a, b[, c] in <list literal or local_lists name>:` циклы —
        #    достаём (key, description) по позиции для каждого элемента.
        for node in ast.walk(func):
            if not isinstance(node, ast.For):
                continue
            if not isinstance(node.target, ast.Tuple):
                continue
            target_names = [e.id if isinstance(e, ast.Name) else None for e in node.target.elts]

            iter_items: list[tuple] | None = None
            if isinstance(node.iter, ast.Name) and node.iter.id in local_lists:
                iter_items = local_lists[node.iter.id]
            elif isinstance(node.iter, (ast.List, ast.Tuple)):
                iter_items = []
                for elt in node.iter.elts:
                    if isinstance(elt, (ast.Tuple, ast.List)):
                        iter_items.append(tuple(_literal_str(e) for e in elt.elts))
            if not iter_items:
                continue

            # Найти в теле цикла Call к PermissionAction/PermissionTab с
            # keyword-значениями = именами из target_names.
            for call_node in ast.walk(node):
                if not isinstance(call_node, ast.Call):
                    continue
                fname = call_node.func.id if isinstance(call_node.func, ast.Name) else None
                orig = alias_to_orig.get(fname)
                if orig not in ("PermissionAction", "PermissionTab"):
                    continue
                key_field = "action_key" if orig == "PermissionAction" else "tab_key"
                label_field = "description" if orig == "PermissionAction" else "title"
                kw = {k.arg: k.value for k in call_node.keywords if k.arg}
                if key_field not in kw or label_field not in kw:
                    continue
                key_pos = _pos_of(kw[key_field], target_names)
                label_pos = _pos_of(kw[label_field], target_names)
                if key_pos is None or label_pos is None:
                    continue
                for item in iter_items:
                    if key_pos >= len(item) or label_pos >= len(item):
                        continue
                    k, v = item[key_pos], item[label_pos]
                    if isinstance(k, str) and isinstance(v, str):
                        (actions if orig == "PermissionAction" else tabs)[k] = v

        # 4. Прямые вызовы PermissionAction(...)/PermissionTab(...) с
        #    буквальными строками или именами локальных констант.
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            fname = node.func.id if isinstance(node.func, ast.Name) else None
            orig = alias_to_orig.get(fname)
            if orig not in ("PermissionAction", "PermissionTab"):
                continue
            key_field = "action_key" if orig == "PermissionAction" else "tab_key"
            label_field = "description" if orig == "PermissionAction" else "title"
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if key_field not in kw or label_field not in kw:
                continue
            key = _resolve(kw[key_field], local_consts)
            label = _resolve(kw[label_field], local_consts)
            if key and label:
                (actions if orig == "PermissionAction" else tabs)[key] = label

    return actions, tabs


def _pos_of(value_node: ast.expr, target_names: list[str | None]):
    if isinstance(value_node, ast.Name) and value_node.id in target_names:
        return target_names.index(value_node.id)
    return None


def _resolve(node: ast.expr, local_consts: dict[str, str]):
    s = _literal_str(node)
    if s is not None:
        return s
    if isinstance(node, ast.Name):
        return local_consts.get(node.id)
    return None


def build_dictionaries() -> dict:
    dicts = _extract_module_dicts(_parse(DICTIONARIES_SRC), DICT_NAMES)
    status_order = _extract_status_order(_parse(PURCHASES_SRC))
    actions, tabs = _extract_permission_seeds(_parse(PERMISSION_SEEDS_SRC))

    def entries(labels: dict[str, str], order: list[str] | None = None) -> list[dict]:
        keys = order if order is not None else sorted(labels)
        return [{"key": k, "label": labels[k]} for k in keys if k in labels]

    return {
        "statuses": entries(dicts["STATUS_LABELS"], status_order),
        "substatuses": entries(dicts["SUBSTATUS_LABELS"]),
        "contract_types": entries(dicts["CONTRACT_TYPE_LABELS"]),
        "purchase_methods": entries(dicts["PURCHASE_METHOD_LABELS"]),
        "purchase_bases": entries(dicts["PURCHASE_BASIS_LABELS"]),
        "permission_actions": [
            {"key": k, "description": actions[k]} for k in sorted(actions)
        ],
        "permission_tabs": [
            {"key": k, "title": tabs[k]} for k in sorted(tabs)
        ],
    }


def build_item_forms() -> dict:
    """item-forms-accommodation-transport.md: ITEM_FORMS/CONTRACT_FORM_TO_ITEM_FORM
    (services/item_forms.py) + CONTRACT_FORM_LABELS (services/dictionaries.py) —
    тот же набор, что отдаёт GET /api/dictionaries/item-forms (см.
    app/routers/dictionaries.py::get_item_forms), одна структура на бэк и фронт."""
    item_forms_tree = _parse(ITEM_FORMS_SRC)
    item_forms = _extract_module_dicts(item_forms_tree, ["ITEM_FORMS"])["ITEM_FORMS"]
    contract_form_to_item_form = _extract_module_dicts(
        item_forms_tree, ["CONTRACT_FORM_TO_ITEM_FORM"]
    )["CONTRACT_FORM_TO_ITEM_FORM"]
    contract_form_labels = _extract_module_dicts(
        _parse(DICTIONARIES_SRC), [CONTRACT_FORM_DICT_NAME]
    )[CONTRACT_FORM_DICT_NAME]
    return {
        "item_forms": item_forms,
        "contract_forms": [
            {"key": k, "label": contract_form_labels[k], "order": i}
            for i, k in enumerate(contract_form_labels)
        ],
        "contract_form_to_item_form": contract_form_to_item_form,
    }


def _write_or_check(output_path: Path, data: dict, check_only: bool, sources_desc: str) -> int:
    serialized = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"

    if check_only:
        if not output_path.exists():
            print(f"[export_dictionaries] {output_path} отсутствует. Запустите: python backend/scripts/export_dictionaries.py")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != serialized:
            print(
                f"[export_dictionaries] {output_path} РАСХОДИТСЯ с источниками "
                f"({sources_desc}). Запустите: python backend/scripts/export_dictionaries.py — и закоммитьте JSON."
            )
            return 1
        print(f"[export_dictionaries] OK: {output_path.name} в синхроне с источниками")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"[export_dictionaries] записано: {output_path}")
    return 0


def main() -> int:
    check_only = "--check" in sys.argv[1:]

    if not FRONTEND_DIR.is_dir():
        # Тот же приём, что frontend/scripts/sync-ru-regions.mjs (Правило №6):
        # backend-образ собирается с build-контекстом ./backend (docker-compose.yml)
        # и не содержит frontend/ вовсе — не ошибка, а ожидаемое окружение (Docker,
        # CI-джоба без checkout соседней папки). Молча выходим 0, копия (если есть)
        # уже закоммичена.
        print(f"[export_dictionaries] {FRONTEND_DIR} недоступен (ожидаемо в собранном backend-образе) — пропуск.")
        return 0

    try:
        data = build_dictionaries()
    except Exception as exc:  # noqa: BLE001 — CI-скрипт, нужен читаемый вывод
        print(f"[export_dictionaries] ошибка разбора источников (dictionaries.json): {exc}")
        return 1

    try:
        item_forms_data = build_item_forms()
    except Exception as exc:  # noqa: BLE001
        print(f"[export_dictionaries] ошибка разбора источников (item_forms.json): {exc}")
        return 1

    rc1 = _write_or_check(OUTPUT_PATH, data, check_only, "dictionaries.py/purchases.py/permission_seeds.py")
    rc2 = _write_or_check(ITEM_FORMS_OUTPUT_PATH, item_forms_data, check_only, "item_forms.py/dictionaries.py")
    return rc1 or rc2


if __name__ == "__main__":
    sys.exit(main())
