"""Сериализация заявки (Wish) в WishOut + сопоставление с закупками.

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-08,
вторая резка wishes.py по образцу первой — commit 89187a0 — и users.py →
commit ca7b02c) БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ.

_enrich/_attach_purchase_matches/_wish_purchase_summaries_map не зависят от
других хелперов ядра app/routers/wishes.py — импортировать их обратно не
нужно, поэтому в отличие от app/services/wish_distribution.py здесь нет
ленивых импортов "во избежание цикла". app/routers/wishes.py импортирует эти
три имени на уровне модуля (для re-export — потребители вроде
app/routers/wish_transitions.py зовут их через `wishes_core._enrich` и т.п.,
см. докстринг wish_transitions.py про monkeypatch).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish import Wish
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.feo_category import FeoCategory
from app.schemas.wishes import WishOut, WishItemPurchaseMatch, WishPurchaseSummary
from app.services.text_match import normalize as _normalize_name
from app.services.item_contractor import item_contractor as _item_contractor


def _enrich(w: Wish) -> WishOut:
    """Convert Wish ORM object to WishOut, filling computed name fields."""
    d = WishOut.model_validate(w)
    if w.creator:
        d.creator_name = w.creator.full_name or w.creator.username
    if w.approver:
        d.approver_name = w.approver.full_name or w.approver.username
    if w.subsidy:
        d.subsidy_name = w.subsidy.name
    if w.assignee:
        d.assignee_name = w.assignee.full_name or w.assignee.username
        d.assigned_to_name = d.assignee_name  # alias for legacy frontend
    if getattr(w, 'event', None):
        d.event_name = w.event.name
    if getattr(w, 'executor', None):
        d.executor_name = w.executor.full_name or w.executor.username
    if getattr(w, 'stopped_by_user', None):
        d.stopped_by_name = w.stopped_by_user.full_name or w.stopped_by_user.username
    if getattr(w, 'rejected_by_user', None):
        d.rejected_by_name = w.rejected_by_user.full_name or w.rejected_by_user.username
    # Контрагент — ПРАВИЛО №6 (группа D5): единственный читатель —
    # item_contractor.item_contractor (FK, когда задан, иначе свободный текст).
    # w.contractor — relationship lazy="selectin" (см. models/wish.py), уже
    # подгружена без доп. запроса.
    _wc = _item_contractor(w, contractor=getattr(w, 'contractor', None))
    if _wc["contractor_name"]:
        d.contractor_display_name = _wc["contractor_name"]
    return d


async def _attach_purchase_matches(wish: Wish, enriched: WishOut, db: AsyncSession) -> None:
    """W-diff (2026-08-13, карточка заявки только): для каждой позиции заявки
    находит её «двойника» в закупке(ах), созданных из этой заявки, и заполняет
    WishItemOut.purchase_match (см. WishItemPurchaseMatch за назначением полей).

    Сопоставление (владелец, 2026-08-13, доразбор неоднозначности заявки №31 —
    «Перчатки … размер L» дважды в заявке, 4 шт/«Финал» и 20 шт/«Окружные»,
    человек различает их количеством):
      1. По PurchaseItem.wish_item_id — надёжная прямая связь.
      2. Иначе — по точному нормализованному имени (app.services.text_match.normalize)
         среди позиций закупок ЭТОЙ ЖЕ заявки, у которых wish_item_id ПУСТ (позиции
         с прямой связью уже разобраны шагом 1 и не участвуют в поиске по имени —
         иначе можно «увести» чужого двойника). Если под этим именем ИЗНАЧАЛЬНО
         (до любых claim'ов) был ровно один кандидат — match_method='item_name'.
      3. Если изначально кандидатов было НЕСКОЛЬКО — сужаем точным совпадением
         quantity. Единственный кандидат с подходящим количеством —
         match_method='item_name_qty' (связь по имени И количеству, честно
         отличается от простого 'item_name'). Это касается КАЖДОЙ позиции
         заявки из такой группы, даже если к моменту её обработки в пуле
         остался только один кандидат (соседняя позиция уже забрала другой) —
         статус группы «была неоднозначна по имени» фиксируется ДО обработки,
         чтобы обе позиции пары «4 шт/20 шт» получили одинаково честную метку,
         а не «первая — по количеству, вторая — как бы просто по имени».
      4. Всё ещё больше одного кандидата с подходящим количеством (или у позиции
         заявки количество не задано) — неоднозначность, наугад не выбираем:
         match_method='item_name_ambiguous' + ambiguous_candidates_count.
         Остальные поля пустые.
      5. Не нашлось вовсе — все поля None.

    Каждый кандидат-двойник закупки достаётся НЕ БОЛЕЕ ЧЕМ одной позиции заявки:
    выбранный кандидат удаляется из пула конкретного имени (list.pop/remove),
    иначе при повторе того же имени в заявке (см. пример выше) вторая позиция
    получила бы того же самого «уже занятого» двойника.

    Один пакетный запрос закупок + один пакетный запрос их позиций (с JOIN на
    feo_categories.name) на всю заявку — без N+1 по позициям.
    """
    purchases_rows = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.status, Purchase.stopped_at)
        .where(Purchase.wish_id == wish.id)
    )).all()
    purchase_info = {r[0]: r for r in purchases_rows}  # purchase_id -> (id, number, status, stopped_at)
    purchase_ids = list(purchase_info.keys())

    purchase_items_rows = []
    if purchase_ids:
        purchase_items_rows = (await db.execute(
            select(PurchaseItem, FeoCategory.name)
            .outerjoin(FeoCategory, FeoCategory.id == PurchaseItem.feo_category_id)
            .where(PurchaseItem.purchase_id.in_(purchase_ids))
        )).all()

    direct_by_wish_item_id: dict[int, tuple] = {}
    unclaimed_by_name: dict[str, list[tuple]] = {}
    for pi, feo_name in purchase_items_rows:
        if pi.wish_item_id is not None:
            direct_by_wish_item_id.setdefault(pi.wish_item_id, (pi, feo_name))
        else:
            key = _normalize_name(pi.item_name or "")
            if key:
                unclaimed_by_name.setdefault(key, []).append((pi, feo_name))
    # Кол-во кандидатов под каждое имя ДО начала claim'а (снимок) — нужно, чтобы
    # оба «близнеца» одной пары «одинаковое имя, разное количество» (см. докстринг)
    # были помечены одинаково 'item_name_qty', а не «первый по количеству, второй
    # по остатку» (иначе один и тот же по сути разбор количества выглядел бы для
    # фронта как связь по имени БЕЗ количества у второй позиции).
    original_candidate_count: dict[str, int] = {k: len(v) for k, v in unclaimed_by_name.items()}

    def _build_match(method: str, pi, feo_name) -> WishItemPurchaseMatch:
        p_row = purchase_info.get(pi.purchase_id)
        return WishItemPurchaseMatch(
            match_method=method,
            purchase_item_id=pi.id,
            purchase_id=pi.purchase_id,
            purchase_number=p_row[1] if p_row else None,
            purchase_status=p_row[2] if p_row else None,
            purchase_stopped_at=p_row[3] if p_row else None,
            feo_category_id=pi.feo_category_id,
            feo_category_name=feo_name,
            quantity=float(pi.quantity) if pi.quantity is not None else None,
            unit_price=float(pi.unit_price) if pi.unit_price is not None else None,
            total_price=float(pi.total_price) if pi.total_price is not None else None,
        )

    wish_items = list(wish.items or [])
    for w_item, out_item in zip(wish_items, enriched.items):
        direct = direct_by_wish_item_id.get(w_item.id)
        if direct is not None:
            out_item.purchase_match = _build_match("wish_item_id", direct[0], direct[1])
            continue
        key = _normalize_name(w_item.item_name or "")
        candidates = unclaimed_by_name.get(key, []) if key else []
        was_ambiguous_name = original_candidate_count.get(key, 0) > 1
        if not candidates:
            continue  # не нашлось — purchase_match остаётся None (default)
        if len(candidates) == 1 and not was_ambiguous_name:
            # Имя изначально указывало ровно на одну позицию закупки — количество
            # не потребовалось.
            pi, feo_name = candidates.pop(0)
            out_item.purchase_match = _build_match("item_name", pi, feo_name)
        else:
            # Имя само по себе неоднозначно (сейчас или изначально — включая
            # случай, когда «сосед» по имени уже разобран выше и остался ровно
            # один кандидат: для НЕГО это тоже разбор по количеству, а не по
            # голому имени). Сужаем точным совпадением quantity.
            qty_matches = [
                c for c in candidates
                if w_item.quantity is not None and c[0].quantity == w_item.quantity
            ]
            if len(qty_matches) == 1:
                pi, feo_name = qty_matches[0]
                candidates.remove((pi, feo_name))  # claim — не достанется другой позиции заявки
                out_item.purchase_match = _build_match("item_name_qty", pi, feo_name)
            else:
                out_item.purchase_match = WishItemPurchaseMatch(
                    match_method="item_name_ambiguous",
                    ambiguous_candidates_count=len(candidates),
                )


async def _wish_purchase_summaries_map(wish_ids: list, db: AsyncSession) -> dict:
    """Пункт 4 (владелец, 2026-08-13): «из согласованной заявки — переход в её
    закупки; если их несколько — выпадающий список с номером/статусом/суммой».
    purchase_ids (List[int], см. рядом) отдаёт только id — этого мало для
    осмысленного меню. Формат карточки закупки вынесен в
    app.services.purchase_summary.purchase_summaries_by_id (план
    zany-fluttering-mountain.md, 2026-08-13) — переиспользуется и «виновниками»
    превышения плана (excess_plan_items, см. app.services.feo_plan), чтобы
    формат карточки не разъехался на два.
    """
    out: dict = {}
    if not wish_ids:
        return out
    from app.services.purchase_summary import purchase_summaries_by_id

    link_rows = (await db.execute(
        select(Purchase.wish_id, Purchase.id)
        .where(Purchase.wish_id.in_(wish_ids))
        .order_by(Purchase.id)
    )).all()
    if not link_rows:
        return out
    summaries = await purchase_summaries_by_id(db, (pid for _wid, pid in link_rows))
    for wid, pid in link_rows:
        s = summaries.get(pid)
        if s is None:
            continue
        out.setdefault(wid, []).append(WishPurchaseSummary(**s))
    return out
