"""Проверки соответствия закупки/позиций дереву плана ФЭО.

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения:
- _compute_purchase_feo_excess / _compute_purchase_feo_mismatch — батч-версии
  для списка/карточки закупки (GET /api/purchases, GET /api/purchases/{id});
- _item_feo_mismatch — расхождение категории ОДНОЙ позиции с деревом плана;
- _category_within — общий обход дерева ФЭО вверх по parent_id (единственное
  место, где это считается — используется и _item_feo_mismatch, и
  _reset_incompatible_item_feo_links, дублировать нельзя, ПРАВИЛО №6);
- _reset_incompatible_item_feo_links — сброс несовместимых привязок позиций
  при смене категории ФЭО в шапке закупки.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.feo_category import FeoCategory
from app.services.feo_plan import compute_feo_plan_tree


async def _compute_purchase_feo_excess(db: AsyncSession, purchases: list) -> dict:
    """Владелец (2026-08-12, дополнено планом crystalline-soaring-heron.md, п.4):
    «превышение плана ФЭО» по закупке(ам) — по категории, к которой отнесена сама
    закупка или хотя бы одна её позиция. Единый код для GET /api/purchases
    (список, ?with_feo_excess=true) и GET /api/purchases/{id} (карточка) — раньше
    карточка эти поля вообще не считала (только список), значок пропадал при
    открытии закупки.

    Владелец (п.4): согласованное превышение больше НЕ гасит сам факт превышения —
    feo_excess остаётся True всегда, когда план категории больше её финансирования
    по ФЭО; feo_excess_state отдельно различает «не запрошено/на согласовании/
    согласовано» (тот же PlanExcessApproval, что уже использует compute_feo_plan_tree —
    вторая копия чтения approval не заводится).

    Возвращает {purchase_id: {feo_excess, feo_excess_hint, feo_excess_amount,
    feo_excess_category, feo_excess_category_id, feo_excess_state,
    feo_excess_approved_by, feo_excess_approved_at}} — на КАЖДУЮ закупку из
    `purchases` (нули/None/"none", если превышения нет или у закупки вовсе нет
    субсидии/категории). `purchases` обязаны иметь загруженные `.items`
    (selectinload/joinedload) — по ним ищется категория-виновник, если сама
    закупка без feo_category_id.

    feo_excess_category_id (владелец, 2026-09-03, «подсказка о превышении должна
    быть понятной») — id категории-виновника (= hit_cid ниже), НЕ гейтится правом
    feo_budget.view_leaf (в отличие от FeoCategory.budget на /feo-categories/leaves,
    /flat) — превышение уже посчитано на сервере независимо от того, кто спрашивает,
    и не является бюджетной цифрой. Фронт использует его, чтобы у пользователя БЕЗ
    feo_budget.view_leaf показать в позиции закупки только сам факт и размер
    превышения статьи (без «занято»/финансирования, из которых можно было бы
    вычислить бюджет) — см. categoryResidualFor в PurchaseItemsEditor.vue.
    """
    _empty = {
        "feo_excess": False, "feo_excess_hint": None, "feo_excess_amount": None,
        "feo_excess_category": None, "feo_excess_category_id": None, "feo_excess_state": "none",
        "feo_excess_approved_by": None, "feo_excess_approved_at": None,
    }
    result: dict = {p.id: dict(_empty) for p in purchases}
    subsidy_ids = list({p.subsidy_id for p in purchases if p.subsidy_id})
    if not subsidy_ids:
        return result

    tree = await compute_feo_plan_tree(db, subsidy_ids)
    bad_cats = {
        cid: node for cid, node in (tree or {}).items()
        if (node.get("excess_over_feo") or node.get("excess_amount") or 0.0) > 0.005
    }
    if not bad_cats:
        return result

    names_r = await db.execute(
        select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(bad_cats.keys()))
    )
    cat_names = {row[0]: row[1] for row in names_r.all()}

    for p in purchases:
        cat_ids = {it.feo_category_id for it in (p.items or []) if it.feo_category_id}
        if p.feo_category_id:
            cat_ids.add(p.feo_category_id)
        hit_cid = next((cid for cid in cat_ids if cid in bad_cats), None)
        if hit_cid is None:
            continue
        node = bad_cats[hit_cid]
        excess = float(node.get("excess_over_feo") or node.get("excess_amount") or 0.0)
        name = cat_names.get(hit_cid, f"#{hit_cid}")
        if node.get("excess_approved"):
            state = "approved"
        elif node.get("excess_pending"):
            state = "pending"
        else:
            state = "not_requested"
        result[p.id] = {
            "feo_excess": True,
            "feo_excess_hint": f"Категория «{name}»: план превышает ФЭО на {excess:,.2f} ₽",
            "feo_excess_amount": excess,
            "feo_excess_category": name,
            "feo_excess_category_id": hit_cid,
            "feo_excess_state": state,
            "feo_excess_approved_by": node.get("excess_approval_by_name"),
            "feo_excess_approved_at": node.get("excess_approval_at"),
        }
    return result


async def _item_feo_mismatch(
    db: AsyncSession, purchase: "Purchase", item: PurchaseItem,
    cat_names: dict | None = None, planned_map: dict | None = None,
) -> dict | None:
    """Владелец (2026-09-02): «уведомление глобально, если позиция категории ФЭО
    вверху и в каждом товаре не соответствует друг другу — об этом должен быть
    алярм прям стоять». Это ПРО ДРУГОЕ, чем _reset_incompatible_item_feo_links —
    тот сбрасывает несогласованные привязки ПРИ смене категории шапки; здесь
    считаем расхождения, которые УЖЕ накоплены (никто категорию не менял, но
    данные разъехались — например, руками поправили feo_category_id позиции
    в обход шапки).

    Расхождение по позиции — любое из:
    1) у позиции есть feo_planned_item_id, а категория привязанной плановой
       позиции НЕ равна эффективной категории позиции (item.feo_category_id,
       если задана; иначе — категория шапки) и не её потомок — см.
       _category_within (тот же обход дерева, второй не пишем);
    2) purchase.feo_per_item ВЫКЛЮЧЕН (общая категория на закупку), а у позиции
       задан feo_category_id, отличный от категории шапки — в этом режиме
       позиции обязаны следовать за шапкой.

    Возвращает None, если расхождений нет, иначе — словарь с человекочитаемыми
    полями (название позиции, что стоит у позиции, что стоит у плановой) для
    ответа API (см. FeoMismatchItemOut в schemas.py) — НЕ голый булев флаг,
    пользователь должен понять, что именно разошлось."""
    from app.models.feo_planned_item import FeoPlannedItem

    cat_names = cat_names or {}

    def _name(cid):
        if cid is None:
            return None
        return cat_names.get(cid, f"#{cid}")

    # Владелец (2026-09-02): при ВЫКЛЮЧЕННОМ purchase.feo_per_item собственная
    # категория позиции не имеет смысла (позиции обязаны следовать за шапкой) —
    # эффективная категория ВСЕГДА категория шапки, даже если у позиции осталась
    # протухшая своя. Иначе "planned"-проверка ниже мерит привязанную плановую
    # позицию от мусора и ложно требует "выберите плановую позицию", хотя
    # пользователь уже выбрал верную категорию в шапке. Это то же правило, что
    # на фронте — эталон _effectiveFeoCategoryId в
    # frontend/src/components/PurchaseItemsEditor.vue (~2378) и
    # effectiveCategoryId в ItemsCardsView.vue/ItemsTableFlat.vue/
    # ItemsTableStages.vue/ItemsTableWish.vue — держать в синхроне, дублирование
    # этого правила уже стоило прод-инцидента.
    effective_cat_id = (
        purchase.feo_category_id
        if not purchase.feo_per_item
        else (item.feo_category_id or purchase.feo_category_id)
    )
    reasons: list[str] = []

    planned = None
    planned_cat_id = None
    if item.feo_planned_item_id:
        planned = (planned_map or {}).get(item.feo_planned_item_id)
        if planned is None:
            planned = await db.get(FeoPlannedItem, item.feo_planned_item_id)
        planned_cat_id = planned.feo_category_id if planned else None
        if effective_cat_id and not await _category_within(db, planned_cat_id, effective_cat_id):
            reasons.append("planned")

    if not purchase.feo_per_item and item.feo_category_id and item.feo_category_id != purchase.feo_category_id:
        reasons.append("header")

    if not reasons:
        return None

    reason = "both" if len(reasons) == 2 else reasons[0]
    effective_name = _name(effective_cat_id)
    header_name = _name(purchase.feo_category_id)
    planned_cat_name = _name(planned_cat_id)
    # Собственная (возможно протухшая) категория позиции — ОТДЕЛЬНО от
    # effective_cat_id, который при выключенном тумблере теперь всегда равен
    # категории шапки (см. правку выше). Для reason="header" в тексте нужно
    # показать именно то, что реально висит на позиции, а не то, от чего
    # считается расхождение.
    own_cat_id = item.feo_category_id
    own_name = _name(own_cat_id)
    item_name = item.item_name or "Без названия"

    parts: list[str] = []
    if "planned" in reasons:
        # Владелец (2026-09-02): текст не должен врать про «категорию самой
        # позиции» — при выключенном тумблере позиция вообще не имеет своей
        # категории, расхождение меряется от категории ШАПКИ.
        source_label = (
            "категория шапки закупки" if not purchase.feo_per_item else "своя категория позиции"
        )
        fix_hint = (
            f"выберите плановую позицию из категории «{effective_name or '—'}» "
            f"либо смените категорию шапки закупки"
            if not purchase.feo_per_item
            else
            f"выберите плановую позицию из нужной категории либо исправьте "
            f"категорию позиции"
        )
        parts.append(
            f"привязана к плановой позиции «{planned.name if planned else '?'}» "
            f"категории «{planned_cat_name or '—'}», а {source_label} — "
            f"«{effective_name or '—'}» — {fix_hint}"
        )
    if "header" in reasons:
        # reason="header" срабатывает только когда purchase.feo_per_item
        # выключен (см. условие выше) — шапка тут источник истины, «исправить
        # шапку» не предлагаем, предлагаем убрать протухшую свою категорию.
        parts.append(
            f"своя категория «{own_name or '—'}» осталась у позиции, хотя режим "
            f"«разные категории для каждого товара» выключен — уберите её, чтобы "
            f"позиция следовала за категорией шапки закупки «{header_name or '—'}»"
        )
    message = f"«{item_name}»: " + "; ".join(parts)

    return {
        "item_id": item.id,
        "item_name": item_name,
        "reason": reason,
        "message": message,
        "item_category_id": effective_cat_id,
        "item_category_name": effective_name,
        "header_category_id": purchase.feo_category_id,
        "header_category_name": header_name,
        "planned_item_id": item.feo_planned_item_id,
        "planned_item_name": planned.name if planned else None,
        "planned_category_id": planned_cat_id,
        "planned_category_name": planned_cat_name,
    }


async def _compute_purchase_feo_mismatch(db: AsyncSession, purchases: list) -> dict:
    """Батч-версия _item_feo_mismatch на весь список закупок ОДНИМ проходом
    (реестр закупок большой — не считаем по закупке за раз). Владелец
    (2026-09-02): «уведомление глобально, если позиция категории ФЭО вверху и
    в каждом товаре не соответствует друг другу — об этом должен быть алярм
    прям стоять».

    Батчинг: один SELECT забирает ВСЕ FeoPlannedItem, на которые ссылаются
    позиции переданных закупок (вместо db.get() по одной на каждую позицию);
    следом несколько SELECT'ов прогревают identity map категориями ФЭО
    (собственные категории позиций/шапок + категории плановых позиций + их
    предки, обычно 2-3 уровня) — так _category_within(db, ...) ниже резолвит
    db.get() из кэша сессии, а не шлёт отдельный запрос на каждую позицию
    каждой закупки. Возвращает {purchase_id: {feo_mismatch, feo_mismatch_items}}
    на КАЖДУЮ закупку из `purchases` (пусто/False, если расхождений нет).
    `purchases` обязаны иметь загруженные `.items` (selectinload/joinedload)."""
    from app.models.feo_planned_item import FeoPlannedItem

    result: dict = {p.id: {"feo_mismatch": False, "feo_mismatch_items": []} for p in purchases}
    all_pairs = [(p, it) for p in purchases for it in (p.items or [])]
    if not all_pairs:
        return result

    fpi_ids = {it.feo_planned_item_id for _, it in all_pairs if it.feo_planned_item_id}
    planned_map: dict = {}
    if fpi_ids:
        rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(fpi_ids))
        )).scalars().all()
        planned_map = {r.id: r for r in rows}

    seed_ids = set()
    for p, it in all_pairs:
        if p.feo_category_id:
            seed_ids.add(p.feo_category_id)
        if it.feo_category_id:
            seed_ids.add(it.feo_category_id)
    for fpi in planned_map.values():
        if fpi.feo_category_id:
            seed_ids.add(fpi.feo_category_id)

    known_ids: set = set()
    frontier = set(seed_ids)
    for _ in range(6):  # дерево ФЭО обычно 2-3 уровня, защита от глубоких данных
        frontier = {cid for cid in frontier if cid not in known_ids}
        if not frontier:
            break
        rows = (await db.execute(select(FeoCategory).where(FeoCategory.id.in_(frontier)))).scalars().all()
        known_ids |= frontier
        for r in rows:
            if r.parent_id:
                frontier.add(r.parent_id)

    cat_names: dict = {}
    if known_ids:
        names_r = await db.execute(select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(known_ids)))
        cat_names = {row[0]: row[1] for row in names_r.all()}

    for p in purchases:
        mismatches = []
        for it in (p.items or []):
            m = await _item_feo_mismatch(db, p, it, cat_names=cat_names, planned_map=planned_map)
            if m:
                mismatches.append(m)
        if mismatches:
            result[p.id] = {"feo_mismatch": True, "feo_mismatch_items": mismatches}
    return result


async def _category_within(db: AsyncSession, cat_id, root_id) -> bool:
    """True, если категория cat_id — это сама root_id либо её потомок (обход
    дерева ФЭО вверх по parent_id; дерево обычно 2-3 уровня, короткий путь).
    None на любой стороне — не совпадает. Предок root_id (не потомок) —
    тоже НЕ within: «новая категория или её потомок» не выполняется."""
    if cat_id is None or root_id is None:
        return False
    if cat_id == root_id:
        return True
    seen: set = set()
    cur_id = cat_id
    for _ in range(30):  # защита от циклов в данных
        if cur_id in seen:
            return False
        seen.add(cur_id)
        cat = await db.get(FeoCategory, cur_id)
        if cat is None or cat.parent_id is None:
            return False
        cur_id = cat.parent_id
        if cur_id == root_id:
            return True
    return False


async def _reset_incompatible_item_feo_links(
    items,
    old_category_id,
    new_category_id,
    per_item_mode: bool,
    db: AsyncSession,
) -> int:
    """Владелец (2026-09-02), прод-баг: суперадмин сменил категорию ФЭО в
    шапке закупки, но PurchaseItem.feo_planned_item_id остался указывать на
    плановую позицию СТАРОЙ категории — лист согласования печатает путь ФЭО
    от плановой позиции и показывает ветку, противоречащую шапке. «При
    изменении категории ФЭО выше привязка позиций должна сбрасываться и
    требовать заново переопределения».

    - feo_per_item выключен (общая категория на закупку) — feo_category_id
      каждой позиции подтягивается к новой категории шапки (следует за ней).
    - feo_per_item включён (своя категория на позицию) — feo_category_id
      позиции НЕ трогаем.
    - В обоих случаях: feo_planned_item_id сбрасывается, если привязанная
      плановая позиция не принадлежит ЭФФЕКТИВНОЙ категории самой позиции
      (item.feo_category_id, если задана; иначе — новая категория шапки) и
      не её потомку — см. _category_within.

    Не вызывается, если категория шапки не менялась (old_category_id ==
    new_category_id) — тогда возвращает 0, в БД не лезет.
    Возвращает число позиций, у которых что-то изменилось (для ответа
    эндпоинта фронту — предупредить пользователя)."""
    if old_category_id == new_category_id:
        return 0
    from app.models.feo_planned_item import FeoPlannedItem

    reset_count = 0
    for item in items:
        changed = False
        if not per_item_mode and item.feo_category_id != new_category_id:
            item.feo_category_id = new_category_id
            changed = True
        effective_cat_id = item.feo_category_id or new_category_id
        if item.feo_planned_item_id and effective_cat_id:
            planned = await db.get(FeoPlannedItem, item.feo_planned_item_id)
            planned_cat_id = planned.feo_category_id if planned else None
            if not await _category_within(db, planned_cat_id, effective_cat_id):
                item.feo_planned_item_id = None
                changed = True
        if changed:
            reset_count += 1
    return reset_count
