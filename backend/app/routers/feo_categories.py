"""Ядро дерева категорий ФЭО: CRUD, гейты записи, ссылочная целостность.

Разрезано из app/routers/feo_categories.py (Правило №5, модульность) без
изменения поведения. Соседние модули несут остальные пути на том же
префиксе /api/feo-categories:
- feo_plan_reads.py — read-only агрегаты плана (/purchase-totals,
  /planned-purchase-totals, /plan-tree, /planned-purchase-items, /leaves,
  /plan-positions, /budget-residuals);
- feo_import.py — импорт/экспорт Excel (/import/template, /import-preview,
  /import, /import-mapped, /export) + ссылочные хелперы _relink_feo_category/
  _feo_category_load;
- feo_tree_ops.py — операции над деревом (/{cat_id}/move, /{cat_id}/reorder,
  /{cat_id}/align-budget-to-plan);
- services/feo_import_engine.py — тяжёлое ядро парсинга импорта
  (_do_feo_import).

Все три роутера зовут гейты/хелперы ЭТОГО модуля через `from app.routers
import feo_categories as fc; fc._require_feo_category_write(...)` — так
тесты (test_feo_category_write_gate.py) продолжают подменять
`fc._require_feo_category_write` через monkeypatch независимо от того, в
каком файле реально живёт вызывающий обработчик.

`move_category`/`reorder_category`/`_do_feo_import` физически определены в
соседних модулях, но по-прежнему доступны как `feo_categories.move_category`
и т.п. — см. `__getattr__` (PEP 562) в конце файла, тот же приём, что и в
app/routers/purchases.py после его разрезания (коммит 89187a0).

Регистрация всех четырёх роутеров — в app/routes.py; feo_plan_reads.router и
feo_import.router несут ТОЛЬКО статичные однословные пути на этом префиксе
и обязаны регистрироваться ДО этого router'а (здесь — catch-all
GET/PUT/DELETE "/{cat_id}"), иначе Starlette матчит их на catch-all раньше.
feo_tree_ops.router путей короче "/{cat_id}/<literal>" не имеет — порядок
относительно этого router'а не важен (тот же принцип, что и у
wish_transitions.router относительно wishes.router).
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.schemas.schemas import FeoCategoryOut, FeoCategoryCreate
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab
from app.auth.visibility import get_visible_subsidy_ids
from app.utils.http import content_disposition
from typing import List, Optional

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


_content_disposition = content_disposition


def _validate_plan_pair(planned_quantity: Optional[float], planned_amount: Optional[float]) -> None:
    """Правило владельца (2026-08-09): плановое количество и плановая цена за
    единицу — ПАРА. Если задана цена за единицу, обязано быть задано и
    количество (тогда сумма = кол-во × цена считается автоматически). Если
    задано количество без цены — то же самое наоборот. Пусто-пусто — план по
    этому листу просто не задан руками (допустимо, план может считаться из
    детей/факта). Оба заполнены — допустимо.

    «Заполнено» = число > 0 (не просто not None) — совпадает с порогом
    app.services.feo_plan.compute_feo_plan_tree._visit (qty > 0 and amt > 0),
    иначе planned_quantity=0 с ценой прошло бы валидацию, но провалилось бы в
    формуле плана (фолбэк на сумму активных FeoPlannedItem, как и «пусто-пусто» —
    молчаливый и неожиданный для пользователя результат).

    Альтернатива для плана ОБЩЕЙ суммой без разбивки на кол-во/цену (напр.
    «Канцтовары» на 1 000 000 без детализации) — не эта пара полей категории, а
    плановая позиция (FeoPlannedItem, кнопка «Добавить плановую» в панели) с
    суммой amount и БЕЗ quantity.
    """
    qty_filled = planned_quantity is not None and float(planned_quantity) > 0
    amt_filled = planned_amount is not None and float(planned_amount) > 0
    if qty_filled == amt_filled:
        return
    if qty_filled:
        detail = (
            "Задано плановое количество, но не задана плановая стоимость за единицу. "
            "Заполните оба поля («Плановое количество» и «Плановая стоимость за ед.») — "
            "тогда сумма посчитается автоматически, — либо очистите количество и задайте "
            "план общей суммой отдельной плановой позицией (кнопка «Добавить плановую» "
            "в панели) без указания количества."
        )
    else:
        detail = (
            "Задана плановая стоимость за единицу, но не задано плановое количество. "
            "Заполните оба поля («Плановое количество» и «Плановая стоимость за ед.») — "
            "тогда сумма посчитается автоматически, — либо очистите цену и задайте план "
            "общей суммой отдельной плановой позицией (кнопка «Добавить плановую» в "
            "панели) без указания количества."
        )
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _plan_pair_unchanged(
    old_quantity: Optional[float], old_amount: Optional[float],
    new_quantity: Optional[float], new_amount: Optional[float],
) -> bool:
    """Дефект 2026-08-31 (владелец, «Редактировать направление ФЭО», тупик 409):
    диалог редактирования категории НЕ даёт править planned_quantity/planned_amount
    напрямую (см. комментарий у кнопки «Сохранить» в SubsidiesView.vue) — он молча
    ретранслирует то, что пришло с GET. Если у категории УЖЕ есть унаследованный
    из БД мисматч пары (старые данные/импорт), PUT с ЛЮБЫМ другим изменением
    (например, только суммы финансирования) раньше падал 409 из _validate_plan_pair
    навсегда, без способа сохраниться — комментарий в PUT-обработчике это допускал,
    но сама проверка была безусловной. Правило владельца «пара обязана биться»
    остаётся в силе ТОЛЬКО когда пользователь реально ЗАДАЁТ/МЕНЯЕТ одно из двух
    полей этим запросом — если оба значения пришли ровно такими же, как в БД,
    мисматч не новый, блокировать нечего.
    """
    def norm(v):
        return None if v is None else float(v)
    return norm(old_quantity) == norm(new_quantity) and norm(old_amount) == norm(new_amount)


async def _has_feo_action(current_user, db: AsyncSession, action_key: str) -> bool:
    """Есть ли у пользователя один из feo_budget.* action-ключей (эффективно, с учётом
    ролевой матрицы + персональных/субсидийных оверрайдов). superadmin — всегда True.
    Общий хелпер для мягкого усечения денежных полей в /leaves, /flat, /plan-tree —
    см. задачу владельца 2026-08-06 «остаток средств по каждой категории ФЭО»."""
    if current_user.role == "superadmin":
        return True
    from app.auth.permissions import _get_effective, _active_org
    effective = await _get_effective(current_user, db, _active_org(current_user))
    return action_key in effective


async def _require_feo_category_write(
    current_user, db: AsyncSession, subsidy_id: Optional[int] = None,
) -> None:
    """Этап B2 (план владельца, 2026-09-01): настоящий гейт ЗАПИСИ дерева категорий
    ФЭО — право feo_category.edit (заведено и засижено этапом B1, коммит 208d848),
    а НЕ факт видимости вкладки. require_tab('feo_categories') на этих же ручках —
    отдельный гейт ВИДИМОСТИ, остаётся как есть, этим хелпером НЕ заменяется.

    has_org_key (а не _get_effective/_has_key_in_any_org) — сознательно: право
    редактировать НЕ наследуется по иерархии «ставлю задачи» (решение 2026-07-06,
    см. её докстринг в app.auth.permissions), проверяется для КОНКРЕТНОЙ орги
    операции + персональный/субсидийный оверрайд по subsidy_id.

    subsidy_id известен не всегда:
      - create/PUT/DELETE/move/reorder — субсидия конкретной категории. ВАЖНО:
        вызывающий код обязан передавать subsidy_id категории, ЗАГРУЖЕННОЙ ИЗ БД
        (cat.subsidy_id), а не присланный в теле запроса — иначе право проверяется
        не по той субсидии, что реально меняется (обход подменой поля).
      - импорт файла БЕЗ единой субсидии назначения (построчный c_subsidy, файл
        может касаться нескольких субсидий одновременно) — subsidy_id=None: право
        проверяется по ЛЮБОЙ доступной пользователю орге (has_org_key на каждую
        кандидатскую оргу активная+UOA, БЕЗ наследования по иерархии).
    """
    if current_user.role == "superadmin":
        return

    def _deny():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "feo_category_edit_required",
                "message": (
                    "Нет права редактировать справочник категорий ФЭО. Просмотр "
                    "остаётся доступен. За правом редактирования обратитесь к "
                    "администратору."
                ),
            },
        )

    from app.models.subsidy import Subsidy
    from app.auth.permissions import has_org_key, _active_org

    if subsidy_id is not None:
        sub = (await db.execute(
            select(Subsidy).where(Subsidy.id == subsidy_id)
        )).scalar_one_or_none()
        org_id = sub.org_id if sub is not None else None
        if await has_org_key(current_user, db, org_id, "feo_category.edit", subsidy_id=subsidy_id):
            return
        _deny()
        return

    candidates: list = []
    active = _active_org(current_user)
    if active:
        candidates.append(active)
    for oid in (getattr(current_user, "_uoa_org_ids", None) or []):
        if oid not in candidates:
            candidates.append(oid)
    if not candidates:
        candidates = [None]
    for oid in candidates:
        if await has_org_key(current_user, db, oid, "feo_category.edit"):
            return
    _deny()


async def _require_feo_import_write(
    current_user, db: AsyncSession, touched_subsidies, sub_rows,
) -> None:
    """Дыра импорта ФЭО, закрыта 2026-09-01 (владелец, после установки гейтов
    B2): `_do_feo_import` (общий код /import и /import-mapped) определяет
    субсидию-назначение НЕ единым subsidy_id запроса, а построчно — колонка
    «Субсидия» файла (сопоставляется по имени через sub_by_name) с
    default_subsidy_id как фолбэком для пустых ячеек. Один файл может
    одновременно затрагивать НЕСКОЛЬКО субсидий, в т.ч. чужих организаций.

    Раньше вызывающие ручки проверяли только
    _require_feo_category_write(current_user, db, subsidy_id=None) — «право
    есть в ЛЮБОЙ доступной пользователю организации» — вообще не глядя, какие
    субсидии реально резолвятся при записи. Пользователь с feo_category.edit
    только в организации A мог импортом записать категории в субсидию
    организации B, если она была названа в колонке «Субсидия» (или задана
    как default_subsidy_id) — тот же класс дыры, что и остальные B2-гейты.

    Проверяет право ПО КАЖДОЙ субсидии из `touched_subsidies` (тот же набор,
    что реально идёт на запись — см. вызывающий код, вычисляется ДО снимка
    версии дерева и ДО основного цикла записи) через уже существующий
    _require_feo_category_write(subsidy_id=...) — ту же проверку, что и для
    create/PUT/DELETE/move/reorder одной категории. Порядок — по возрастанию
    id (детерминированно для тестов/логов). При первой недоступной субсидии
    отказывает ЦЕЛИКОМ (fail-fast, ничего ещё не записано), явно называя
    субсидию в сообщении — не generic 403.

    current_user=None пропускается молча (тот же контракт, что и снимок
    версии дерева ниже, — на живых ручках user всегда реальный, т.к. обе
    зависят от require_tab, который требует аутентификацию).
    """
    if current_user is None:
        return
    sub_name_by_id = {s.id: s.name for s in sub_rows}
    for sid in sorted(touched_subsidies):
        try:
            await _require_feo_category_write(current_user, db, sid)
        except HTTPException as e:
            label = sub_name_by_id.get(sid, f"id={sid}")
            inner = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    **inner,
                    "subsidy_id": sid,
                    "message": (
                        f"Нет права записывать категории ФЭО в субсидию «{label}» — "
                        + str(inner.get("message") or "")
                    ).strip(),
                },
            )


@router.get("/", response_model=List[FeoCategoryOut])
async def list_categories(
    parent_id: Optional[int] = Query(None),
    level: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    appendix: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(FeoCategory)
    vis = await get_visible_subsidy_ids(current_user, db, "feo_categories")
    if vis is not None:
        # ФЭО-категории выбираются внутри форм заявки/закупки, поэтому пикер
        # доступен всем, кто видит субсидию по вкладкам wishes или purchases
        # (напр. роль Менеджер без админской вкладки feo_categories видит субсидию
        # только через «Заявки») — иначе список категорий пуст.
        vis = vis | await get_visible_subsidy_ids(current_user, db, "purchases")
        vis = vis | await get_visible_subsidy_ids(current_user, db, "wishes")
        q = q.where(FeoCategory.subsidy_id.in_(vis))
    if parent_id is not None:
        q = q.where(FeoCategory.parent_id == parent_id)
    if level is not None:
        q = q.where(FeoCategory.level == level)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    if appendix is not None:
        q = q.where(FeoCategory.appendix == appendix)
    if is_active is not None:
        q = q.where(FeoCategory.is_active == is_active)
    result = await db.execute(q.order_by(FeoCategory.sort_order.nulls_last(), FeoCategory.id))
    return result.scalars().all()


def _category_has_plan(cat, cats_with_plan_items: set) -> bool:
    """Структурный признак «у категории задан план» — вынесен из get_feo_flat в чистую
    функцию, чтобы покрыть тестом на подставных объектах (без БД/async), см.
    tests/test_feo_has_plan.py. Три независимых источника плана (любой > 0 → True):
    1) planned_quantity × planned_amount категории (обычный CRM-план);
    2) активная FeoPlannedItem с amount > 0 под категорией (cats_with_plan_items —
       предвычисленный набор id, см. вызывающий код);
    3) plan_source == 'manual_sum' и manual_plan_amount > 0 (план введён одной суммой,
       без количества/цены за единицу — см. FeoCategory.plan_source/manual_plan_amount).
    """
    from_quantity_amount = bool(
        cat.planned_quantity is not None
        and cat.planned_amount is not None
        and float(cat.planned_quantity) * float(cat.planned_amount) > 0
    )
    from_planned_items = cat.id in cats_with_plan_items
    from_manual_sum = bool(
        cat.plan_source == "manual_sum"
        and cat.manual_plan_amount is not None
        and float(cat.manual_plan_amount) > 0
    )
    return from_quantity_amount or from_planned_items or from_manual_sum


@router.get("/flat")
async def get_feo_flat(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns all FeoCategory nodes for a subsidy as a flat list with is_leaf flag.

    Response: [{id, name, parent_id, level, is_leaf, budget, planned_quantity, planned_amount,
                has_budget, has_plan}]
    is_leaf = True if the node has no children within the same subsidy.
    budget = собственная (ручная) сумма финансирования узла, без расчёта по детям.
    planned_quantity/planned_amount — плановые показатели (CRM-план), заполняются НЕЗАВИСИМО
    от budget: конечная категория может иметь план (использована в плане закупок) без
    собственного budget.

    has_budget/has_plan — СТРУКТУРНЫЕ булевы признаки (НЕ денежные величины, НЕ гейтятся
    правом): has_budget истинен, если у узла задан собственный budget > 0; has_plan истинен,
    если planned_quantity × planned_amount > 0, ЛИБО (фолбэк — план переехал в записи
    внутри категории) у узла есть активная FeoPlannedItem с amount > 0, ЛИБО (план введён
    одной суммой) plan_source == 'manual_sum' и manual_plan_amount > 0. Без этих фолбэков
    мигрированные категории-листья (planned_quantity/planned_amount категории пусты, план
    введён плановыми позициями либо ручной суммой) пропадают из дерева выбора категории ФЭО
    в заявке/закупке — к ним нельзя привязать закупку, хотя план реально есть. Фронт (useFeoLeaves.filterFundedNodes)
    считает узел значимым по has_budget ИЛИ has_plan (с фолбэком на числовые budget/
    planned_quantity/planned_amount, если бэкенд старый) — иначе такие категории
    вырезались из дерева выбора, хотя реально существуют и используются (баг «категория
    ФЭО была удалена из справочника», сессия 2026-08-05). Важно: has_budget/has_plan
    обязаны приходить ВСЕГДА, независимо от права feo_budget.view_leaf — иначе у роли без
    этого права дерево выбора категорий ФЭО становится полностью пустым (найдено при
    ревью гейта, сессия 2026-08-06).
    Sorted by level, then sort_order, then id.

    Право feo_budget.view_leaf (дефолт — все роли, включая employee) гейтит денежные
    поля budget/planned_amount — без права оба приходят null (уже допустимое по типу
    состояние, см. ниже); planned_quantity — количество, не деньги, не гейтится.
    Закрытие дыры: раньше эндпоинт вообще не проверял права (задача владельца 2026-08-06).
    """
    can_view_leaf = await _has_feo_action(current_user, db, "feo_budget.view_leaf")
    cats_q = (
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .order_by(FeoCategory.level, FeoCategory.sort_order.nulls_last(), FeoCategory.id)
    )
    all_cats = (await db.execute(cats_q)).scalars().all()
    if not all_cats:
        return []

    # Determine which nodes have children
    has_children: set[int] = set()
    for c in all_cats:
        if c.parent_id is not None:
            has_children.add(c.parent_id)

    # Фолбэк has_plan: план переехал в записи внутри категории (FeoPlannedItem) —
    # у мигрированных категорий-листьев planned_quantity/planned_amount пусты, план
    # введён активными плановыми позициями. Без этого набора has_plan у таких узлов
    # уходит в false, и они пропадают из дерева выбора категории ФЭО на фронте
    # (useFeoLeaves.filterFundedNodes) — к ним нельзя привязать закупку, хотя план
    # реально есть (на боевых данных таких категорий около сотни). Один batch-запрос
    # на все категории ответа — без N+1 в цикле.
    from app.models.feo_planned_item import FeoPlannedItem
    cat_ids = [c.id for c in all_cats]
    cats_with_plan_items: set[int] = set()
    if cat_ids:
        plan_rows = (await db.execute(
            select(FeoPlannedItem.feo_category_id)
            .where(FeoPlannedItem.feo_category_id.in_(cat_ids))
            .where(FeoPlannedItem.is_active.is_(True))
            .where(FeoPlannedItem.amount > 0)
            .group_by(FeoPlannedItem.feo_category_id)
        )).scalars().all()
        cats_with_plan_items = set(plan_rows)

    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "level": c.level,
            "is_leaf": c.id not in has_children,
            "description": c.description,
            "budget": (float(c.budget) if c.budget is not None else None) if can_view_leaf else None,
            "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
            "planned_amount": (float(c.planned_amount) if c.planned_amount is not None else None) if can_view_leaf else None,
            # Структурные признаки — НЕ гейтятся правом, см. docstring выше.
            "has_budget": bool(c.budget is not None and float(c.budget) > 0),
            "has_plan": _category_has_plan(c, cats_with_plan_items),
        }
        for c in all_cats
    ]


@router.get("/tree")
async def category_tree(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(FeoCategory)
    if subsidy_id is not None:
        q = q.where(FeoCategory.subsidy_id == subsidy_id)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, FeoCategory.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q.order_by(FeoCategory.level, FeoCategory.sort_order.nulls_last(), FeoCategory.id))
    all_cats = result.scalars().all()
    by_id = {c.id: {"id": c.id, "parent_id": c.parent_id, "subsidy_id": c.subsidy_id,
                    "level": c.level, "name": c.name, "code": c.code,
                    "appendix": c.appendix, "is_active": c.is_active,
                    "description": c.description,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "feo_quantity": float(c.feo_quantity) if c.feo_quantity is not None else None,
                    "feo_unit": c.feo_unit,
                    "feo_amount": float(c.feo_amount) if c.feo_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "unit": c.unit,
                    "children": []} for c in all_cats}
    roots = []
    for c in all_cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


class _UnallocatedBody(BaseModel):
    subsidy_id: int
    parent_id: Optional[int] = None


async def _check_unallocated_write_access(
    current_user, db: AsyncSession, org_id: Optional[int], subsidy_id: int,
) -> None:
    """Этап B3 (план владельца, 2026-09-01): гейт для POST /unallocated.

    ЭТО НЕ гейт «редактирование дерева категорий» (feo_category.edit) — ручку
    дёргает обычный сотрудник из формы заявки/закупки при выборе категории
    «Не определена», у него обычно НЕТ доступа к справочнику ФЭО вовсе. По
    образцу app.routers.feo_planned_items._check_planned_item_write_access:
    пропускаем, если есть feo_category.edit ПО ЭТОЙ СУБСИДИИ, ИЛИ
    wish.edit_feo ПО ЭТОЙ СУБСИДИИ, ИЛИ вкладка wishes/purchases (кто заводит
    заявки/закупки, должен уметь завести недостающий узел «Не определена» под
    них). has_org_key/has_org_key — ненаследующая по иерархии проверка права
    (иерархия «ставлю задачи» не даёт права на чужую субсидию), а
    _has_key_in_any_org для вкладок — та же логика видимости, что и у tab-гейтов.
    """
    if current_user.role == "superadmin":
        return
    from app.auth.permissions import has_org_key, _has_key_in_any_org

    if await has_org_key(current_user, db, org_id, "feo_category.edit", subsidy_id=subsidy_id):
        return
    if await has_org_key(current_user, db, org_id, "wish.edit_feo", subsidy_id=subsidy_id):
        return
    if await _has_key_in_any_org(current_user, db, "wishes"):
        return
    if await _has_key_in_any_org(current_user, db, "purchases"):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "unallocated_category_access_required",
            "message": (
                "Нет права заводить категорию «Не определена»: нет доступа к "
                "справочнику ФЭО по этой субсидии, нет права на перераспределение "
                "позиций заявки по категориям ФЭО и нет вкладки заявок/закупок."
            ),
        },
    )


@router.post("/unallocated")
async def get_or_create_unallocated(
    body: _UnallocatedBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Найти или создать категорию «Не определена» (или «Нераспределённое») для субсидии.

    Доступна всем авторизованным пользователям с доступом к субсидии
    (wishes / purchases / feo_categories). Не требует require_tab('feo_categories'),
    но требует _check_unallocated_write_access (B3) — своя, более мягкая матрица
    прав, см. её докстринг.

    parent_id (опц.) — создать дочернюю «Не определена» под этим родителем.

    Response: {id, name, subsidy_id, parent_id, created: bool}
    """
    from app.models.subsidy import Subsidy

    # Проверить существование субсидии
    sub = (await db.execute(select(Subsidy).where(Subsidy.id == body.subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Субсидия не найдена")

    # Изоляция по организации (аналогично list_categories)
    vis = await get_visible_subsidy_ids(current_user, db, "feo_categories")
    if vis is not None:
        vis = vis | await get_visible_subsidy_ids(current_user, db, "purchases")
        vis = vis | await get_visible_subsidy_ids(current_user, db, "wishes")
        if body.subsidy_id not in vis:
            raise HTTPException(status_code=403, detail="Нет доступа к этой субсидии")

    # B3: право ЗАВЕСТИ узел «Не определена» — своя (мягкая) матрица, не
    # feo_category.edit целиком (см. докстринг хелпера).
    await _check_unallocated_write_access(current_user, db, sub.org_id, body.subsidy_id)

    # Загрузить родителя, если указан
    parent: Optional[FeoCategory] = None
    if body.parent_id is not None:
        parent = (await db.execute(
            select(FeoCategory).where(FeoCategory.id == body.parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Родительская категория не найдена")
        if parent.subsidy_id != body.subsidy_id:
            raise HTTPException(
                status_code=422,
                detail="Родительская категория относится к другой субсидии",
            )

    # Найти существующую (все варианты имён для обратной совместимости)
    stmt = (
        select(FeoCategory)
        .where(FeoCategory.subsidy_id == body.subsidy_id)
        .where(FeoCategory.is_active.is_(True))
        .where(func.lower(FeoCategory.name).in_([
            "не определена",
            "нераспределённое",
            "нераспределенное",
        ]))
    )
    if body.parent_id is None:
        stmt = stmt.where(FeoCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(FeoCategory.parent_id == body.parent_id)

    existing = (await db.execute(stmt.order_by(FeoCategory.id).limit(1))).scalars().first()
    if existing:
        return {
            "id": existing.id,
            "name": existing.name,
            "subsidy_id": existing.subsidy_id,
            "parent_id": existing.parent_id,
            "created": False,
        }

    # Создать новую
    new_level = (parent.level + 1) if parent is not None else 1
    new_cat = FeoCategory(
        name="Не определена",
        subsidy_id=body.subsidy_id,
        parent_id=body.parent_id,
        level=new_level,
        sort_order=9999,
        is_active=True,
    )
    db.add(new_cat)
    await db.commit()
    await db.refresh(new_cat)
    return {
        "id": new_cat.id,
        "name": new_cat.name,
        "subsidy_id": new_cat.subsidy_id,
        "parent_id": new_cat.parent_id,
        "created": True,
    }


@router.post("/", response_model=FeoCategoryOut)
async def create_category(
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    # B2: создание новой категории — субсидия ещё не существует как объект, законно
    # берём subsidy_id из тела (это и есть целевая субсидия операции).
    await _require_feo_category_write(current_user, db, category_data.subsidy_id)
    _validate_plan_pair(category_data.planned_quantity, category_data.planned_amount)

    if category_data.parent_id:
        parent_result = await db.execute(
            select(FeoCategory).where(FeoCategory.id == category_data.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Родительская категория не найдена")
        level = parent.level + 1
    else:
        level = 1

    new_category = FeoCategory(
        parent_id=category_data.parent_id,
        subsidy_id=category_data.subsidy_id,
        level=level,
        name=category_data.name,
        code=category_data.code,
        appendix=category_data.appendix,
        is_active=category_data.is_active,
        description=category_data.description,
        budget=category_data.budget,
        feo_quantity=category_data.feo_quantity,
        feo_unit=category_data.feo_unit,
        feo_amount=category_data.feo_amount,
        planned_quantity=category_data.planned_quantity,
        planned_amount=category_data.planned_amount,
        unit=category_data.unit,
        plan_source=category_data.plan_source or "planned_items",
        manual_plan_amount=category_data.manual_plan_amount,
    )
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category


@router.put("/{cat_id}", response_model=FeoCategoryOut)
async def update_category(
    cat_id: int,
    category_data: FeoCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    result = await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # B2: субсидия берётся из УЖЕ ЗАГРУЖЕННОЙ категории (cat.subsidy_id), а не из
    # тела запроса (category_data.subsidy_id) — иначе право можно обойти подменой
    # поля в запросе, отправив subsidy_id чужой субсидии, где есть право.
    await _require_feo_category_write(current_user, db, cat.subsidy_id)
    if not _plan_pair_unchanged(
        cat.planned_quantity, cat.planned_amount,
        category_data.planned_quantity, category_data.planned_amount,
    ):
        _validate_plan_pair(category_data.planned_quantity, category_data.planned_amount)
    _old_plan = (
        cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount,
        cat.plan_source, cat.manual_plan_amount,
    )
    cat.name = category_data.name
    cat.code = category_data.code
    cat.appendix = category_data.appendix
    cat.is_active = category_data.is_active
    cat.description = category_data.description
    cat.budget = category_data.budget
    cat.feo_quantity = category_data.feo_quantity
    cat.feo_unit = category_data.feo_unit
    cat.feo_amount = category_data.feo_amount
    cat.planned_quantity = category_data.planned_quantity
    cat.planned_amount = category_data.planned_amount
    cat.unit = category_data.unit
    cat.plan_source = category_data.plan_source or "planned_items"
    cat.manual_plan_amount = category_data.manual_plan_amount

    # Задача владельца «план ≠ факт» (шаг D, сессия 2026-08-06): защита от повторения
    # К1 (боевые 16 760 000 — сумма записана в поле «цена за единицу»). НЕ блокируем
    # (владелец мог ввести именно это осознанно), только предупреждаем в ответе, если
    # planned_quantity × planned_amount более чем вдвое больше финансирования ФЭО —
    # похоже на «сумму вместо цены за единицу» при quantity > 1.
    warning: Optional[str] = None
    if (
        cat.planned_quantity is not None and float(cat.planned_quantity) > 1
        and cat.planned_amount is not None
        and cat.budget is not None and float(cat.budget) > 0
    ):
        _qty = float(cat.planned_quantity)
        _amt = float(cat.planned_amount)
        _budget = float(cat.budget)
        _total = _qty * _amt
        if _total > _budget * 2:
            warning = (
                f"Похоже, в поле «Цена за единицу» введена сумма: "
                f"{_qty:g} × {_amt:,.2f} = {_total:,.2f} ₽ при финансировании {_budget:,.2f} ₽."
            )

    # Владелец, план zany-fluttering-mountain.md (2026-08-13): предупреждение о
    # смене режима расчёта плана, если в категории уже есть плановые позиции —
    # переключение на 'manual_sum' не удаляет их (они продолжают участвовать в
    # excess_plan_over_manual/qty_plan), но раньше именно их сумма БЫЛА планом,
    # теперь плановой суммой становится manual_plan_amount, введённая руками.
    if _old_plan[5] != cat.plan_source:
        from app.models.feo_planned_item import FeoPlannedItem as _FeoPlannedItem
        _items_cnt = (await db.execute(
            select(func.count(_FeoPlannedItem.id))
            .where(_FeoPlannedItem.feo_category_id == cat_id)
            .where(_FeoPlannedItem.is_active.is_(True))
        )).scalar_one()
        if _items_cnt:
            _mode_warning = (
                f"Смена способа расчёта плана: у категории уже есть {_items_cnt} "
                f"плановых позиций. "
                + (
                    "Планом теперь становится введённая сумма, а не их Σ — если сумма "
                    "меньше, появится превышение."
                    if cat.plan_source == "manual_sum"
                    else "Планом снова становится Σ плановых позиций."
                )
            )
            warning = f"{warning} {_mode_warning}" if warning else _mode_warning

    _new_plan = (
        cat.budget, cat.feo_quantity, cat.feo_amount, cat.planned_quantity, cat.planned_amount,
        cat.plan_source, cat.manual_plan_amount,
    )
    if _new_plan != _old_plan and cat.subsidy_id:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(subsidy_id=cat.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение плановых показателей ФЭО «{cat.name}»")
    await db.commit()
    await db.refresh(cat)
    if warning:
        out = FeoCategoryOut.model_validate(cat).model_dump()
        out["warning"] = warning
        return out
    return cat


async def _collect_subtree_ids(cat_id: int, db: AsyncSession) -> list[int]:
    """Recursively collect all descendant IDs including the given cat_id."""
    ids = [cat_id]
    children = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.parent_id == cat_id)
    )).scalars().all()
    for cid in children:
        ids.extend(await _collect_subtree_ids(cid, db))
    return ids


# Удаление блокируют только закупки, по которым работа реально идёт
# (стадия «Ведётся работа» и далее). Желания/план закупок/подтверждено —
# работа не начата, категория удаляется, привязка обнуляется (FK SET NULL).
BLOCKING_STATUSES = ("work_in_progress", "contracted", "ordered", "delivered", "paid")


async def _collect_blocking_purchases(ids: list[int], db: AsyncSession) -> list:
    """Закупки в блокирующих статусах, привязанные к переданным категориям
    напрямую (Purchase.feo_category_id) либо через позиции (PurchaseItem.feo_category_id).
    Уникальные по id, поля: id, purchase_number, subject, status."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    direct = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status).where(
            Purchase.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()
    via_items = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.status)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.feo_category_id.in_(ids),
            Purchase.status.in_(BLOCKING_STATUSES),
        )
    )).all()

    seen: dict[int, object] = {}
    for row in direct:
        seen[row.id] = row
    for row in via_items:
        seen.setdefault(row.id, row)
    return list(seen.values())


async def _purge_feo_categories(ids: list[int], db: AsyncSession):
    """Отвязать все ссылки на переданные категории и удалить их. Не коммитит —
    коммитит вызывающий."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product
    from app.models.feo_planned_item import FeoPlannedItem

    # Отвязать закупки ранних стадий и их позиции от удаляемого поддерева
    await db.execute(
        Purchase.__table__.update().where(Purchase.feo_category_id.in_(ids)).values(feo_category_id=None)
    )
    await db.execute(
        PurchaseItem.__table__.update().where(PurchaseItem.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK references in products before deleting
    await db.execute(
        Product.__table__.update().where(Product.feo_category_id.in_(ids)).values(feo_category_id=None)
    )

    # Nullify FK in purchase_items referencing planned_items of these categories
    planned_item_ids = (await db.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_(ids))
    )).scalars().all()
    if planned_item_ids:
        await db.execute(
            PurchaseItem.__table__.update().where(
                PurchaseItem.feo_planned_item_id.in_(planned_item_ids)
            ).values(feo_planned_item_id=None)
        )

    # Delete planned items explicitly (in case DB lacks CASCADE)
    await db.execute(
        FeoPlannedItem.__table__.delete().where(FeoPlannedItem.feo_category_id.in_(ids))
    )

    # Delete categories in one statement — feo_categories.parent_id is
    # ON DELETE CASCADE in the DB, so order doesn't matter. Doing it via
    # a table-level DELETE (instead of ORM db.delete per object) avoids
    # lazy-loading the `children` backref (FeoCategory.parent relationship).
    await db.execute(
        FeoCategory.__table__.delete().where(FeoCategory.id.in_(ids))
    )


@router.get("/{cat_id}/subtree")
async def get_category_subtree(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Имя категории + id всего поддерева (для фильтра «закупки этой категории»)."""
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == cat_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    ids = await _collect_subtree_ids(cat_id, db)
    return {"id": cat.id, "name": cat.name, "ids": ids}


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # B2: субсидия удаляемой категории — из объекта, загруженного из БД, тело
    # запроса у DELETE вообще отсутствует, подменить нечем, но источник тот же.
    await _require_feo_category_write(current_user, db, cat.subsidy_id)

    # Collect entire subtree
    all_ids = await _collect_subtree_ids(cat_id, db)

    linked_purchases = await _collect_blocking_purchases(all_ids, db)
    if linked_purchases:
        purchase_ids = [p.id for p in linked_purchases]
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Нельзя удалить: {len(linked_purchases)} закупок со стадией "
                    f"«Ведётся работа» и далее привязано к этой категории. "
                    f"Закупки на ранних стадиях (желания, план закупок) удалению не мешают."
                ),
                "purchase_ids": purchase_ids,
                "feo_category_ids": all_ids,
            }
        )

    await _purge_feo_categories(all_ids, db)
    await db.commit()
    deleted_count = len(all_ids)
    return {"ok": True, "deleted_count": deleted_count}


# Ленивый ре-экспорт (PEP 562 module __getattr__) символов, которые уехали в
# новые routers/feo_*.py и services/feo_import_engine.py, но тесты и другие
# роутеры всё ещё обращаются к ним через app.routers.feo_categories / `fc.<имя>`
# (fc = import app.routers.feo_categories as fc, см. test_feo_category_write_gate.py
# и test_feo_import_tree.py). Этот модуль-ядро НЕ импортирует новые роутеры на
# уровне модуля — иначе цикл (feo_tree_ops.py/feo_import.py сами импортируют
# fc._require_feo_category_write/fc._collect_subtree_ids/... ИЗ этого модуля при
# загрузке) — сам импорт происходит только по факту обращения к атрибуту, когда
# оба модуля уже полностью загружены. По образцу app/routers/purchases.py
# (коммит 89187a0).
_LAZY_REEXPORTS = {
    "_do_feo_import": "app.services.feo_import_engine",
    "move_category": "app.routers.feo_tree_ops",
    "reorder_category": "app.routers.feo_tree_ops",
    "align_budget_to_plan": "app.routers.feo_tree_ops",
    "_update_subtree_levels": "app.routers.feo_tree_ops",
    "_relink_feo_category": "app.routers.feo_import",
    "_feo_category_load": "app.routers.feo_import",
}


def __getattr__(name):
    module_path = _LAZY_REEXPORTS.get(name)
    if module_path is not None:
        import importlib
        return getattr(importlib.import_module(module_path), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
