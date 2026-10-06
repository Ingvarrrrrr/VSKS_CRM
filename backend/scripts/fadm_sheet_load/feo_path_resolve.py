"""Сопоставление (AE, AF, AG) листа GoodsService с категорией дерева ФЭО —
ПО ПУТИ, а не глобальным поиском имени (баг найден 06.10.2026, см. задание):
старый `FeoNameLookup` (sheet_v2_build.py) искал AE/AF/AG среди ВСЕХ категорий
субсидии сразу, без учёта иерархии, из-за чего:
  - AF длиннее имени категории в дереве (лист обрезает/расширяет формулировку)
    не находился вовсе, и позиция падала на корень AE;
  - AG (самое конкретное, уровень 3) проверялся ПОСЛЕДНИМ в `lookup.find(AF,
    AE, AG)` и не использовался вовсе, если AE/AF дали хоть какое-то (пусть
    неверное) совпадение;
  - одинаковые имена на разных уровнях («Техническое оснащение деятельности
    штаба» — и корень level=1, и его единственный ребёнок level=2; «Не
    определена» — несколько штук в дереве) давали непредсказуемый выбор.

ЕДИНОЕ правило сопоставления (ПРАВИЛО №6) — используется и загрузчиком
(sheet_v2_build.py::_resolve_feo_category), и пересчётом уже загруженной
субсидии (remap_feo_categories.py): НИКАКОГО второго алгоритма сравнения имён.

Путь поиска:
  1. Корень по AE — среди категорий уровня 1 (parent_id IS NULL) субсидии.
  2. Среди ДЕТЕЙ найденного корня — по AF.
  3. Если AF не нашёлся среди ПРЯМЫХ детей корня — «глубокий» поиск AF среди
     ВСЕХ потомков корня (level 2 и 3 разом) — владелец, доп. правка
     07.10.2026: папка для AF иногда заводится на уровень глубже, чем прямой
     ребёнок (внук корня) — пример с прода: «Приобретение ОСАГО для
     автомобилей» и «Организация и проведения праздничных мероприятий к
     25-летию ВСКС» созданы level=3, хотя соответствуют AF, а не AG. Только
     если совпадение ОДНОЗНАЧНО (ровно один кандидат, те же три уровня
     сравнения) — иначе остаёмся на корне. Найденный таким образом узел
     отмечается `stopped_at='af_deep'`.
  4. Среди ДЕТЕЙ найденного по AF (прямого или «глубокого») — по AG (если AG
     пусто — остаёмся на AF/af_deep).
  5. Если AF не нашёлся НИГДЕ (ни среди прямых детей, ни глубоким поиском), а
     AG задан — пробуем AG среди ВСЕХ потомков корня (level 2 и 3), но только
     если совпадение ОДНОЗНАЧНО — иначе остаёмся на корне.
  6. Неоднозначность (>1 подходящей категории) на любом шаге — НЕ угадываем,
     остаёмся на уровне, найденном ДО этого шага, и фиксируем это отдельно
     (`ambiguous=True`), чтобы вызывающий код мог показать это в отчёте.

Сравнение имён: нормализация (убрать нумерацию «1.»/«2)», обрамляющие
кавычки, концевую пунктуацию, лишние пробелы, привести к нижнему регистру);
совпадение — ТРИ уровня, в порядке убывания строгости (ПРАВИЛО №6 — одна
функция, не копии при каждом использовании):
  1. exact — точное равенство нормализованных строк.
  2. prefix — одна строка целиком — префикс другой, минимум MIN_PREFIX_MATCH
     (15) общих символов (AF в листе обычно ДЛИННЕЕ имени категории дерева —
     лист не обрезан, дерево обрезано).
  3. common_prefix (владелец, доп. правка 06.10.2026) — типичное расхождение
     СЛОВОФОРМЫ в хвосте длинной строки (прод-находка: лист «...гуманитарных
     миссий и прочих», дерево «...гуманитарных миссиЯХ и прочих» — одно слово
     в другом падеже ближе к концу 290-символьной строки ломает чистый
     prefix-тест, хотя совпадение визуально очевидно). Применяется ТОЛЬКО при
     выборе среди ДЕТЕЙ уже найденного родителя (3-5 кандидатов — безопасно,
     в отличие от globalной дедупликации по всему каталогу, где фаззи
     запрещено, см. feedback_dedup_exact_only): берётся ребёнок с САМЫМ
     длинным общим префиксом с именем из листа, если этот префикс ≥
     COMMON_PREFIX_MIN_LEN (40) символов И длиннее префикса любого другого
     ребёнка минимум на COMMON_PREFIX_MARGIN (10) символов — иначе (нет
     явного лидера) результат как при отсутствии совпадения: остаёмся выше,
     фиксируем неоднозначность.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[.)]\s*")
_EDGE_QUOTES_RE = re.compile(r'^[«"\'\s]+|[»"\'\s]+$')
_TRAILING_PUNCT_RE = re.compile(r"[.,;:\s]+$")
_WS_RE = re.compile(r"\s+")

MIN_PREFIX_MATCH = 15
COMMON_PREFIX_MIN_LEN = 40
COMMON_PREFIX_MARGIN = 10


def normalize_feo_name(raw: Optional[str]) -> str:
    """Нормализация имени направления/категории для сравнения — ЕДИНАЯ для
    AE/AF/AG листа и FeoCategory.name дерева. Снимает ведущий «N.»/«N)»,
    обрамляющие кавычки, концевую пунктуацию, схлопывает пробелы, нижний
    регистр."""
    v = (raw or "").strip()
    v = _LEADING_NUMBER_RE.sub("", v)
    v = _EDGE_QUOTES_RE.sub("", v)
    v = _TRAILING_PUNCT_RE.sub("", v)
    v = _WS_RE.sub(" ", v).strip().lower()
    return v


def names_match(a: str, b: str) -> bool:
    """`a`/`b` — уже нормализованные строки. Совпадение exact ИЛИ prefix (см.
    докстринг модуля, уровни 1-2). Используется для выбора КОРНЯ (AE) — там
    common_prefix (уровень 3) сознательно НЕ применяется (корней субсидии
    может быть много, это не «3-5 кандидатов среди детей»)."""
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < MIN_PREFIX_MATCH:
        return False
    return longer.startswith(shorter)


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


@dataclass(frozen=True)
class CategoryNode:
    id: int
    parent_id: Optional[int]
    name: str
    level: int


@dataclass
class ResolvedPath:
    category_id: Optional[int]
    path: list  # имена категорий от корня до остановки (может быть пустым)
    stopped_at: str  # 'none' | 'root' | 'af' | 'af_deep' | 'ag' | 'ag_global'
    reason: str
    ambiguous: bool = False
    ambiguous_level: Optional[str] = None
    ambiguous_candidates: list = field(default_factory=list)  # [(id, name), ...]
    # Способ, которым найден ИТОГОВЫЙ узел (category_id): 'exact' | 'prefix' |
    # 'common_prefix' | None (узел не найден дальше корня, либо не найден
    # вовсе) — для отчёта пересчёта (владелец, доп. правка 06.10.2026).
    match_method: Optional[str] = None
    # Имена детей на уровне, где поиск НЕ дал однозначного узла (AF не найден
    # среди детей AE, либо AG не найден среди детей AF) — диагностика для
    # отчёта, без повторного похода в дерево на стороне вызывающего кода.
    considered_siblings: list = field(default_factory=list)


class FeoTree:
    """Дерево категорий ОДНОЙ субсидии, построенное из плоского списка строк
    (id, parent_id, name, level) — тот же набор колонок, что в FeoCategory."""

    def __init__(self, categories: Sequence[CategoryNode]) -> None:
        self.by_id: dict[int, CategoryNode] = {c.id: c for c in categories}
        self.children: dict[Optional[int], list[CategoryNode]] = {}
        for c in categories:
            self.children.setdefault(c.parent_id, []).append(c)
        for lst in self.children.values():
            lst.sort(key=lambda c: c.id)

    @property
    def roots(self) -> list[CategoryNode]:
        return self.children.get(None, [])

    def kids(self, parent_id: int) -> list[CategoryNode]:
        return self.children.get(parent_id, [])

    def descendants(self, node_id: int) -> list[CategoryNode]:
        out: list[CategoryNode] = []
        stack = list(self.kids(node_id))
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(self.kids(n.id))
        return out

    def path_to(self, node: CategoryNode) -> list[str]:
        names: list[str] = []
        cur: Optional[CategoryNode] = node
        seen: set[int] = set()
        while cur is not None and cur.id not in seen:
            names.append(cur.name)
            seen.add(cur.id)
            cur = self.by_id.get(cur.parent_id) if cur.parent_id is not None else None
        names.reverse()
        return names


def _find_candidates(nodes: Sequence[CategoryNode], raw_name: str) -> list[CategoryNode]:
    """exact/prefix (уровни 1-2) — используется для выбора КОРНЯ (AE)."""
    norm = normalize_feo_name(raw_name)
    if not norm:
        return []
    return [n for n in nodes if names_match(norm, normalize_feo_name(n.name))]


@dataclass
class _Selection:
    node: Optional[CategoryNode]
    method: Optional[str]  # 'exact' | 'prefix' | 'common_prefix' | None
    ambiguous: bool = False
    ambiguous_candidates: list = field(default_factory=list)  # [(id, name), ...]


def _select_child(nodes: Sequence[CategoryNode], raw_name: str) -> _Selection:
    """Выбор СРЕДИ ДЕТЕЙ уже найденного родителя — ТРИ уровня строгости (см.
    докстринг модуля). nodes — обычно 3-5 кандидатов (прямые дети категории),
    поэтому уровень 3 (common_prefix) здесь безопасен."""
    norm = normalize_feo_name(raw_name)
    if not norm:
        return _Selection(None, None)

    exact = [n for n in nodes if normalize_feo_name(n.name) == norm]
    if len(exact) == 1:
        return _Selection(exact[0], "exact")
    if len(exact) > 1:
        return _Selection(None, None, ambiguous=True,
                           ambiguous_candidates=[(n.id, n.name) for n in exact])

    prefix = [n for n in nodes if names_match(norm, normalize_feo_name(n.name))]
    if len(prefix) == 1:
        return _Selection(prefix[0], "prefix")
    if len(prefix) > 1:
        return _Selection(None, None, ambiguous=True,
                           ambiguous_candidates=[(n.id, n.name) for n in prefix])

    # Уровень 3 — общий префикс (расхождение словоформы в хвосте длинной строки).
    scored = sorted(
        ((_common_prefix_len(norm, normalize_feo_name(n.name)), n) for n in nodes),
        key=lambda t: -t[0],
    )
    if not scored or scored[0][0] < COMMON_PREFIX_MIN_LEN:
        return _Selection(None, None)
    top_len, top_node = scored[0]
    runner_up_len = scored[1][0] if len(scored) > 1 else -1
    if top_len - runner_up_len >= COMMON_PREFIX_MARGIN:
        return _Selection(top_node, "common_prefix")
    # Явного лидера нет — несколько детей с близким общим префиксом листа.
    close = [n for cp, n in scored if top_len - cp < COMMON_PREFIX_MARGIN]
    return _Selection(None, None, ambiguous=True,
                       ambiguous_candidates=[(n.id, n.name) for n in close])


def _finish_from_af(tree: FeoTree, af_node: CategoryNode, base_stopped_at: str,
                     af_match_method: Optional[str], ag: str) -> ResolvedPath:
    """Общий хвост алгоритма — AG среди детей УЖЕ найденного AF-узла, будь то
    прямой ребёнок корня (base_stopped_at='af') или узел, найденный глубоким
    поиском (base_stopped_at='af_deep') — ОДНА функция, не копия при каждом
    способе найти af_node (ПРАВИЛО №6)."""
    path = tree.path_to(af_node)
    ag_norm = normalize_feo_name(ag)
    if not ag_norm:
        return ResolvedPath(af_node.id, path, base_stopped_at, "AG не указан — остаёмся на AF",
                             match_method=af_match_method)

    ag_sel = _select_child(tree.kids(af_node.id), ag)
    if ag_sel.ambiguous:
        return ResolvedPath(
            af_node.id, path, base_stopped_at, "AG неоднозначен среди детей AF — остаёмся на AF",
            ambiguous=True, ambiguous_level="ag", ambiguous_candidates=ag_sel.ambiguous_candidates,
        )
    if ag_sel.node is None:
        return ResolvedPath(af_node.id, path, base_stopped_at, "AG не найден среди детей AF — остаёмся на AF",
                             match_method=af_match_method,
                             considered_siblings=[n.name for n in tree.kids(af_node.id)])

    ag_node = ag_sel.node
    return ResolvedPath(ag_node.id, path + [ag_node.name], "ag", "найдено по AE→AF→AG",
                         match_method=ag_sel.method)


def resolve_feo_path(tree: FeoTree, ae: str, af: str, ag: str) -> ResolvedPath:
    """Основная функция — см. докстринг модуля для алгоритма."""
    root_candidates = _find_candidates(tree.roots, ae)
    if not root_candidates:
        return ResolvedPath(None, [], "none", "AE не найден среди направлений уровня 1 (корней) субсидии")
    if len(root_candidates) > 1:
        return ResolvedPath(
            None, [], "none", "AE неоднозначен среди корней субсидии",
            ambiguous=True, ambiguous_level="ae",
            ambiguous_candidates=[(n.id, n.name) for n in root_candidates],
        )
    root = root_candidates[0]
    path = [root.name]

    af_sel = _select_child(tree.kids(root.id), af)
    if af_sel.ambiguous:
        return ResolvedPath(
            root.id, path, "root", "AF неоднозначен среди детей AE — остаёмся на AE",
            ambiguous=True, ambiguous_level="af", ambiguous_candidates=af_sel.ambiguous_candidates,
        )
    if af_sel.node is not None:
        return _finish_from_af(tree, af_sel.node, "af", af_sel.method, ag)

    # AF не найден среди ПРЯМЫХ детей корня — «глубокий» поиск AF среди ВСЕХ
    # потомков корня (владелец, доп. правка 07.10.2026 — папка для AF иногда
    # заведена на уровень глубже, чем прямой ребёнок). Только однозначно.
    siblings = [n.name for n in tree.kids(root.id)]
    af_deep_sel = _select_child(tree.descendants(root.id), af)
    if af_deep_sel.ambiguous:
        return ResolvedPath(
            root.id, path, "root",
            "AF не найден в прямых детях AE; AF неоднозначен среди ВСЕХ потомков AE (глубокий поиск) — "
            "остаёмся на AE",
            ambiguous=True, ambiguous_level="af_deep", ambiguous_candidates=af_deep_sel.ambiguous_candidates,
            considered_siblings=siblings,
        )
    if af_deep_sel.node is not None:
        return _finish_from_af(tree, af_deep_sel.node, "af_deep", af_deep_sel.method, ag)

    # AF не найден НИГДЕ — пробуем AG среди ВСЕХ потомков корня, только если
    # совпадение однозначно.
    ag_sel_global = _select_child(tree.descendants(root.id), ag)
    if ag_sel_global.ambiguous:
        return ResolvedPath(
            root.id, path, "root",
            "AF не найден в детях AE; AG неоднозначен среди потомков AE — остаёмся на AE",
            ambiguous=True, ambiguous_level="ag_global",
            ambiguous_candidates=ag_sel_global.ambiguous_candidates,
            considered_siblings=siblings,
        )
    if ag_sel_global.node is not None:
        node = ag_sel_global.node
        return ResolvedPath(node.id, tree.path_to(node), "ag_global",
                             "AF не найден в детях AE; AG однозначно найден среди всех потомков AE",
                             match_method=ag_sel_global.method)
    return ResolvedPath(root.id, path, "root", "AF не найден в детях AE, AG тоже не найден — остаёмся на AE",
                         considered_siblings=siblings)


async def load_feo_tree(db, subsidy_id: int) -> FeoTree:
    """Загрузка дерева категорий субсидии — общий хелпер для загрузчика и
    remap-скрипта (ПРАВИЛО №6: один источник построения дерева)."""
    from sqlalchemy import select
    from app.models.feo_category import FeoCategory

    rows = (await db.execute(
        select(FeoCategory.id, FeoCategory.parent_id, FeoCategory.name, FeoCategory.level)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )).all()
    nodes = [CategoryNode(id=i, parent_id=p, name=n, level=lvl or 0) for i, p, n, lvl in rows]
    return FeoTree(nodes)
