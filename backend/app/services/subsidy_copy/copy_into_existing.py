"""Дублирование отдельных закупок и заявок из ОДНОЙ субсидии в ДРУГУЮ, уже
существующую (не связанную copied_from_id — не «копия для экспериментов»,
см. ../__init__.py::create_sandbox_copy для того случая). Задание владельца
06.10.2026: продублировать закупки РЕЕ-2026-00976/00973/00960 и заявку id=95
из «ФАДМ_2026» в «ФАДМ 2026_2», старые записи не трогать.

Закупки копирует copy_purchases() (../copy_purchases.py) с фильтром
purchase_ids — ПРАВИЛО №6, второй копировщик закупок здесь НЕ заводится.
Этот модуль добавляет то, чего у copy_purchases нет: сопоставление дерева
ФЭО/плановых позиций ДВУХ РАЗНЫХ субсидий по имени (у «копии для экспериментов»
дерево копируется вместе с субсидией и id просто переносятся — здесь оба
дерева уже существуют независимо и могут отличаться) и копирование заявки
(Wish/WishItem; wish_members/wish_approvals сознательно не копируются —
согласование копии начинается заново, см. docstring copy_wishes ниже).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_item import WishItem

from ._clone import clone_row

# Статусы заявки, которые переживают копию как есть — заявка ещё не прошла
# согласование (draft) или ждёт его (submitted), копия логично продолжает с
# той же точки. Любой другой статус (approved/converted/rejected/...)
# предполагает уже случившееся решение/конвертацию в закупку конкретной
# (исходной) субсидии — копия без purchase_id и без approvals отправляется
# на НОВОЕ согласование, поэтому "submitted" (владелец, задание 06.10.2026:
# "статус копии = статус оригинала, если он draft/submitted, иначе submitted").
_PRESERVED_WISH_STATUSES = {"draft", "submitted"}


def normalize_name(name: Optional[str]) -> str:
    """trim + схлопнуть внутренние пробелы + casefold — ЕДИНСТВЕННОЕ правило
    сравнения имён категорий/плановых позиций в этом модуле. build_category_map/
    build_planned_item_map и отчёт скрипта copy_into_subsidy.py обязаны звать
    именно это (ПРАВИЛО №6), а не придумывать своё сравнение строк."""
    if not name:
        return ""
    return " ".join(name.strip().split()).casefold()


async def _load_categories(db: AsyncSession, subsidy_id: int):
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    by_id: dict[int, FeoCategory] = {c.id: c for c in cats}
    children: dict[Optional[int], list[FeoCategory]] = defaultdict(list)
    for c in cats:
        children[c.parent_id].append(c)
    return by_id, children


def _path_tuple(by_id: dict[int, FeoCategory], cat_id: int) -> tuple[str, ...]:
    names: list[str] = []
    cur = by_id.get(cat_id)
    seen: set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        names.append(normalize_name(cur.name))
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return tuple(reversed(names))


def category_path_str(by_id: dict[int, FeoCategory], cat_id: Optional[int]) -> str:
    """Человекочитаемый путь (без нормализации — реальные имена) для отчёта
    скрипта. cat_id=None или не найден в by_id -> понятная заглушка, а не KeyError."""
    if cat_id is None:
        return "(нет категории)"
    cat = by_id.get(cat_id)
    if cat is None:
        return f"#{cat_id} (не в загруженном дереве)"
    names: list[str] = []
    cur = cat
    seen: set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        names.append(cur.name)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return " / ".join(reversed(names))


class CategoryMapResult:
    __slots__ = ("map", "unmatched", "source_by_id", "target_by_id")

    def __init__(self) -> None:
        self.map: dict[int, Optional[int]] = {}
        self.unmatched: list[int] = []
        self.source_by_id: dict[int, FeoCategory] = {}
        self.target_by_id: dict[int, FeoCategory] = {}


async def build_category_map(db: AsyncSession, source_sid: int, target_sid: int) -> CategoryMapResult:
    """{old_cat_id: new_cat_id} по совпадению ПУТИ имён (уровень1 / уровень2 /
    уровень3, normalize_name). Путь целиком не совпал, но путь РОДИТЕЛЯ (на
    уровень выше) совпал -> ищем лист по имени среди детей совпавшего
    родителя в целевой субсидии. Не нашлось ни так, ни так -> new_cat_id=None
    (попадает в .unmatched, скрипт печатает «НЕ НАЙДЕНА»)."""
    result = CategoryMapResult()
    src_by_id, _src_children = await _load_categories(db, source_sid)
    tgt_by_id, tgt_children = await _load_categories(db, target_sid)
    result.source_by_id = src_by_id
    result.target_by_id = tgt_by_id

    tgt_path_to_id: dict[tuple[str, ...], int] = {}
    for cid in tgt_by_id:
        # setdefault — при дубле пути в целевом дереве берём первый найденный
        # (дубль путей — редкость и не повод падать здесь).
        tgt_path_to_id.setdefault(_path_tuple(tgt_by_id, cid), cid)

    for cid in src_by_id:
        path = _path_tuple(src_by_id, cid)
        new_id = tgt_path_to_id.get(path)
        if new_id is None and len(path) > 1:
            parent_id = tgt_path_to_id.get(path[:-1])
            if parent_id is not None:
                leaf = path[-1]
                for child in tgt_children.get(parent_id, []):
                    if normalize_name(child.name) == leaf:
                        new_id = child.id
                        break
        result.map[cid] = new_id
        if new_id is None:
            result.unmatched.append(cid)
    return result


class PlannedItemMapResult:
    __slots__ = ("map", "unmatched", "cloned")

    def __init__(self) -> None:
        self.map: dict[int, Optional[int]] = {}
        # Категория самой позиции не сопоставлена -> клонировать некуда,
        # позиция остаётся без плановой (единственный случай, когда
        # map[id] остаётся None).
        self.unmatched: list[int] = []
        # Позиция НЕ нашлась по имени в сопоставленной категории -> клонирована
        # (map[id] заполнен новым id) — отчёт скрипта отличает «перенесена»
        # от «найдена по имени».
        self.cloned: set[int] = set()


async def build_planned_item_map(
    db: AsyncSession,
    category_map: dict[int, Optional[int]],
    item_ids: Optional[Iterable[int]] = None,
) -> PlannedItemMapResult:
    """{old_planned_item_id: new_planned_item_id} по normalize_name ВНУТРИ
    соответствующей новой категории (category_map[item.feo_category_id]).

    item_ids=None (умолчание) — обрабатывает ВСЕ плановые позиции всех
    категорий из category_map (простое «посчитать сопоставление для всего
    дерева»). item_ids={...} — ТОЛЬКО перечисленные позиции: так вызывает
    copy_into_subsidy.py, чтобы не раздувать план целевой субсидии клонами
    НЕиспользуемых плановых позиций — клонируются только те, что реально
    нужны копируемым закупкам/заявке (владелец, задание 07.10.2026: «всё
    купленное должно быть привязано к плановым»).

    Позиция с таким именем НЕ нашлась ОДНОЗНАЧНО в сопоставленной категории ->
    КЛОНИРУЕТСЯ (clone_row — тот же приём, что copy_feo_tree.copy_feo_tree,
    ПРАВИЛО №6: не второй копировщик FeoPlannedItem) в эту категорию и
    используется её новый id — см. .cloned. Категория самой позиции НЕ
    сопоставлена -> клонировать некуда, new_planned_item_id=None (см.
    .unmatched).

    «Однозначно» (баг прода 07.10.2026: 7 РАЗНЫХ старых плановых с одинаковым
    именем «Обработка заказа в пункте выдачи», каждая со своей суммой,
    склеились в ОДНУ новую — первая клонировалась, остальные «нашлись по
    имени» среди только что склонированных) — ОБА условия сразу:
      1. в целевой категории, ДО начала этого прогона (снимок target_items_by_cat
         взят ОДНИМ запросом в начале функции и больше не пополняется —
         склонированная в этом прогоне строка НИКОГДА не считается «найденной
         по имени» для ДРУГОЙ старой позиции), с этим именем ровно ОДНА позиция;
      2. среди обрабатываемых в ЭТОМ вызове старых позиций (item_ids или все
         позиции мэппинга) с этим именем в той же целевой категории — тоже
         ровно ОДНА (иначе — какая из нескольких старых правильная пара той
         одной целевой? никакая, клонируем все).
    Не выполняется хотя бы одно условие -> клон, а не угадывание.

    Один и тот же старый id, встреченный несколько раз в одном вызове (заявка
    и закупка ссылаются на ТУ ЖЕ плановую позицию) — засчитывается/клонируется
    РОВНО ОДИН раз (select на DISTINCT строки FeoPlannedItem по id) и это —
    единственный случай, когда результат одной старой использует ОДНУ и ту же
    новую для нескольких ссылающихся строк."""
    result = PlannedItemMapResult()
    source_cat_ids = list(category_map.keys())
    if not source_cat_ids:
        return result

    if item_ids is not None:
        item_ids = set(item_ids)
        if not item_ids:
            return result
        source_items = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(item_ids))
        )).scalars().all()
    else:
        source_items = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_(source_cat_ids))
        )).scalars().all()
    if not source_items:
        return result

    target_cat_ids = sorted({v for v in category_map.values() if v is not None})
    # Снимок ДО клонирования — замороженный, НЕ пополняется ниже (см. докстринг
    # «однозначно», п.1). Ключ — (feo_category_id, normalize_name(name)).
    target_by_key: dict[tuple[int, str], list[int]] = defaultdict(list)
    if target_cat_ids:
        target_items = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_(target_cat_ids))
        )).scalars().all()
        for it in target_items:
            target_by_key[(it.feo_category_id, normalize_name(it.name))].append(it.id)

    # Сколько РАЗНЫХ старых позиций в этом вызове претендуют на тот же
    # (целевая категория, имя) — п.2 «однозначно».
    source_by_key: dict[tuple[int, str], list[int]] = defaultdict(list)
    for item in source_items:
        new_cat_id = category_map.get(item.feo_category_id)
        if new_cat_id is not None:
            source_by_key[(new_cat_id, normalize_name(item.name))].append(item.id)

    for item in source_items:
        new_cat_id = category_map.get(item.feo_category_id)
        if new_cat_id is None:
            result.map[item.id] = None
            result.unmatched.append(item.id)
            continue

        key = (new_cat_id, normalize_name(item.name))
        target_candidates = target_by_key.get(key, [])
        source_candidates = source_by_key.get(key, [])

        if len(target_candidates) == 1 and len(source_candidates) == 1:
            new_item_id = target_candidates[0]
        else:
            new_item = clone_row(item, FeoPlannedItem, feo_category_id=new_cat_id)
            db.add(new_item)
            await db.flush()
            new_item_id = new_item.id
            result.cloned.add(item.id)

        result.map[item.id] = new_item_id
    return result


class WishCopyResult:
    __slots__ = ("wish_id_map", "wish_item_id_map", "wish_count", "warnings")

    def __init__(self) -> None:
        self.wish_id_map: dict[int, int] = {}
        # Старый WishItem.id -> новый — нужен relink_wish_and_purchase_copies
        # для перепривязки PurchaseItem.wish_item_id между копиями.
        self.wish_item_id_map: dict[int, int] = {}
        self.wish_count = 0
        self.warnings: list[str] = []


async def copy_wishes(
    db: AsyncSession,
    wish_ids: set[int],
    target_sid: int,
    category_map: dict[int, Optional[int]],
    planned_item_map: dict[int, Optional[int]],
) -> WishCopyResult:
    """Копия Wish + WishItem в target_sid. НЕ копируется: WishApproval
    (wish.approvals, cascade) и WishMember — согласование копии начинается с
    нуля, у неё не должно быть чужих решений/участников (владелец, задание
    06.10.2026). purchase_id копии всегда NULL — заявка ещё не конвертирована
    В ЭТОЙ субсидии. feo_category_id/feo_planned_item_id (заявки и её строк)
    перепривязаны по картам, не найдено -> NULL (предупреждение)."""
    result = WishCopyResult()
    if not wish_ids:
        return result

    target_org_id = (await db.execute(
        select(Subsidy.org_id).where(Subsidy.id == target_sid)
    )).scalar_one_or_none()

    wishes = (await db.execute(
        select(Wish).where(Wish.id.in_(wish_ids))
    )).scalars().all()
    found_ids = {w.id for w in wishes}
    for missing_id in sorted(wish_ids - found_ids):
        result.warnings.append(f"Заявка id={missing_id} не найдена — пропущена")

    for w in wishes:
        new_status = w.status if w.status in _PRESERVED_WISH_STATUSES else "submitted"
        new_cat_id = category_map.get(w.feo_category_id) if w.feo_category_id else None
        if w.feo_category_id and new_cat_id is None:
            result.warnings.append(
                f"Заявка id={w.id}: категория ФЭО #{w.feo_category_id} не сопоставлена "
                f"в целевой субсидии — поле очищено"
            )
        new_w = clone_row(
            w, Wish,
            org_id=target_org_id if target_org_id is not None else w.org_id,
            subsidy_id=target_sid,
            feo_category_id=new_cat_id,
            purchase_id=None,
            status=new_status,
            # Решение/история согласования — не переносится, копия начинает с
            # чистого листа (см. docstring выше).
            rejected_by=None,
            rejected_at=None,
            rejection_reason=None,
            approved_by=None,
            stopped_at=None,
            stopped_by=None,
            stopped_reason=None,
            stopped_partial=False,
            tz_not_required=False,
            tz_waived_by_user_id=None,
        )
        db.add(new_w)
        await db.flush()
        result.wish_id_map[w.id] = new_w.id
        result.wish_count += 1

        items = (await db.execute(
            select(WishItem).where(WishItem.wish_id == w.id)
        )).scalars().all()
        for it in items:
            new_item_cat_id = category_map.get(it.feo_category_id) if it.feo_category_id else None
            new_planned_id = planned_item_map.get(it.feo_planned_item_id) if it.feo_planned_item_id else None
            if it.feo_planned_item_id and new_planned_id is None:
                result.warnings.append(
                    f"Заявка id={w.id}, позиция «{it.item_name}»: плановая позиция "
                    f"#{it.feo_planned_item_id} не сопоставлена — позиция останется без плановой"
                )
            new_it = clone_row(
                it, WishItem,
                wish_id=new_w.id,
                feo_category_id=new_item_cat_id,
                feo_planned_item_id=new_planned_id,
                feo_planned_item_match_confirmed=False,
            )
            db.add(new_it)
            await db.flush()
            result.wish_item_id_map[it.id] = new_it.id

    await db.flush()
    return result


async def relink_wish_and_purchase_copies(
    db: AsyncSession,
    purchase_id_map: dict[int, int],
    wish_id_map: dict[int, int],
    wish_item_id_map: dict[int, int],
    purchase_item_id_map: dict[int, int],
) -> list[str]:
    """Если в ОДНОМ прогоне copy_into_subsidy.py копируются и заявка, и
    связанная с ней закупка (типичный случай — авансовый отчёт: Wish.purchase_id
    и Purchase.wish_id указывают друг на друга, PurchaseItem.wish_item_id — на
    конкретную строку заявки, см. models/wish.py::purchase_id, models/purchase.py
    ::wish_id, models/purchase_item.py::wish_item_id), copy_purchases() и
    copy_wishes() по отдельности этого не знают — обе копии выходят НЕ связаны
    друг с другом (wish_id/purchase_id/wish_item_id копий = NULL). Эта функция
    восстанавливает ТЕ ЖЕ связи между КОПИЯМИ, читая оригинальные связи. Если
    закупка (или заявка) в данном прогоне не копировалась — связь остаётся
    None, как и раньше (владелец, задание 07.10.2026, п.2)."""
    warnings: list[str] = []
    if not purchase_id_map or not wish_id_map:
        return warnings

    old_purchases = (await db.execute(
        select(Purchase).where(Purchase.id.in_(purchase_id_map.keys()))
    )).scalars().all()
    for old_p in old_purchases:
        if old_p.wish_id and old_p.wish_id in wish_id_map:
            new_p = await db.get(Purchase, purchase_id_map[old_p.id])
            new_p.wish_id = wish_id_map[old_p.wish_id]

    old_wishes = (await db.execute(
        select(Wish).where(Wish.id.in_(wish_id_map.keys()))
    )).scalars().all()
    for old_w in old_wishes:
        if old_w.purchase_id and old_w.purchase_id in purchase_id_map:
            new_w = await db.get(Wish, wish_id_map[old_w.id])
            new_w.purchase_id = purchase_id_map[old_w.purchase_id]

    if wish_item_id_map and purchase_item_id_map:
        old_items = (await db.execute(
            select(PurchaseItem).where(
                PurchaseItem.purchase_id.in_(purchase_id_map.keys()),
                PurchaseItem.wish_item_id.in_(wish_item_id_map.keys()),
            )
        )).scalars().all()
        for old_it in old_items:
            new_item_id = purchase_item_id_map.get(old_it.id)
            new_wish_item_id = wish_item_id_map.get(old_it.wish_item_id)
            if new_item_id is not None and new_wish_item_id is not None:
                new_it = await db.get(PurchaseItem, new_item_id)
                new_it.wish_item_id = new_wish_item_id

    await db.flush()
    return warnings
