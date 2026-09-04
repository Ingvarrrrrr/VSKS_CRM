"""Реформация ошибочно заведённой заявки («Заявки на закупку») в авансовый отчёт.

Повод (владелец, 2026-09-04, дословно): «человек может по ошибке заводить
Авансовый через заявку ... надо дать возможность завести эту заявку как
авансовый отчёт». Пример с прода: Любарец завела кабель как обычную заявку
на закупку (она ушла по маршруту согласования/распределения в закупки),
хотя по факту сотрудник уже потратил свои деньги — это должен был быть
авансовый отчёт.

ОДИН ИСТОЧНИК ИСТИНЫ (ПРАВИЛО №6) — этот модуль НЕ пишет вторую копию
логики «заявка → закупка»:
  - копирование позиций и создание Purchase(purchase_method='advance') —
    переиспользует app.routers.wishes._distribute_wish_to_purchases. Эта
    функция уже умеет создавать авансовую закупку сама, если
    wish.source == 'advance_report' (см. её ветку `_is_advance_wish`) —
    ровно тот же код путь, что использует авто-companion заявка при прямом
    создании авансового (app/routers/purchases.py::create_purchase, ветка
    is_advance). Здесь только выставляется wish.source и убираются старые,
    ошибочно заведённые закупки — дальше работает существующий код.
  - порог «когда переоформление уже запрещено» — переиспользует
    app.routers.wishes._wish_locked_descr (та же CONTRACTED_STATUSES = стадии
    «Договор»/«Заказано»/«Поставлено»/«Оплачено», что уже блокирует правку
    заявки нигде больше не продублирована).

Права доступа НЕ проверяются здесь — это ответственность роутера
(app/routers/wishes.py); здесь только бизнес-правило «можно ли вообще
переоформить» и сама трансформация данных.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def convert_wish_to_advance_report(wish, db: AsyncSession, current_user):
    """Переоформляет заявку `wish` в авансовый отчёт.

    Шаги:
      1. Идемпотентность — уже авансовая заявка отклоняется явным сообщением.
      2. Стадийный гейт — реиспользует _wish_locked_descr (см. докстринг модуля).
      3. Требует хотя бы одну заполненную позицию (иначе нечего переносить).
      4. Отменяет (status='cancelled') и отвязывает (wish_id=None) старые
         закупки, заведённые по ошибочному не-авансовому пути — гейт (2) уже
         исключил стадии договор/оплата, так что отмена безопасна: деньги ещё
         не потрачены ЧЕРЕЗ эту закупку (сама история/файлы остаются в БД,
         закупка просто перестаёт быть частью активного плана — см. `_EXCLUDED_
         FROM_SPENT`/`PLANNED_STATUSES` фильтры, они уже исключают 'cancelled').
      5. wish.source = 'advance_report' → _distribute_wish_to_purchases создаёт
         НОВУЮ закупку purchase_method='advance' (позиции переносятся 1:1,
         product_id остаётся как есть — НЕ обязателен, см. PurchaseItemCreate).
      6. Заявка становится «компаньоном» авансового отчёта — тем же статусом,
         что и авто-заявка при прямом создании авансового (status='submitted',
         согласование сброшено) — см. app/routers/purchases.py::create_purchase.

    Возвращает созданный Purchase (purchase_method='advance'). Commit НЕ
    делает — это на вызывающем роутере (как и весь _distribute_wish_to_purchases).
    """
    from app.models.purchase import Purchase
    from app.models.wish_item import WishItem
    from app.routers.wishes import (
        _wish_locked_descr,
        _is_meaningful_item,
        _distribute_wish_to_purchases,
        _reset_approvals,
        _wish_linked_purchases,
    )

    if getattr(wish, "source", None) == "advance_report":
        raise HTTPException(
            status_code=409,
            detail=f"Заявка №{wish.id} уже оформлена как авансовый отчёт — повторное переоформление не требуется.",
        )

    locked_descr = await _wish_locked_descr(wish.id, db)
    if locked_descr:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Заявку №{wish.id} нельзя переоформить в авансовый отчёт: по ней уже есть "
                f"закупка на стадии договора или оплаты — {locked_descr}. "
                "Переделать заявку в авансовый отчёт можно только пока закупка не дошла до "
                "договора — дальнейшие правки вносите прямо в закупке."
            ),
        )

    items_res = await db.execute(select(WishItem).where(WishItem.wish_id == wish.id))
    all_items = items_res.scalars().all()
    meaningful_items = [it for it in all_items if _is_meaningful_item(it)]
    if not meaningful_items:
        raise HTTPException(
            status_code=409,
            detail=f"В заявке №{wish.id} нет ни одной заполненной позиции — переоформлять в авансовый отчёт нечего.",
        )

    # Старые закупки заявки (заведённые по обычному, не-авансовому пути) —
    # отменяем и отвязываем, чтобы _distribute_wish_to_purchases ниже не нашёл
    # их через «защита от дублей» и создал новую, правильно типизированную
    # авансовую закупку, а не просто продвинул статус старой.
    old_purchases = await _wish_linked_purchases(wish.id, db)
    cancelled_purchase_labels: list[str] = [
        f"№{p.purchase_number or p.id}" for p in old_purchases if p.status != "cancelled"
    ]
    for p in old_purchases:
        p.status = "cancelled"
        p.wish_id = None
    if old_purchases:
        wish.purchase_id = None
        await db.flush()

    wish.source = "advance_report"
    created_ids = await _distribute_wish_to_purchases(
        wish, db, current_user, purchase_status="wishes", split=False,
    )
    if not created_ids:
        # Не должно случаться (meaningful_items уже проверены выше), но не
        # молчим — 500 понятнее, чем тихий None ниже по коду.
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось создать авансовый отчёт из заявки №{wish.id}: закупка не была создана.",
        )

    # Заявка теперь — «компаньон» авансового отчёта («заявка на возмещение»),
    # тот же статус, что у авто-заявки при прямом создании авансового
    # (app/routers/purchases.py::create_purchase, ветка is_advance):
    # 'submitted', ждёт своего согласования НЕЗАВИСИМО от закупки (см.
    # докстринг Wish.source в app/models/wish.py).
    wish.status = "submitted"
    wish.approved_by = None
    wish.rejected_by = None
    wish.rejected_at = None
    wish.rejection_reason = None
    wish.stopped_at = None
    wish.stopped_by = None
    wish.stopped_reason = None
    wish.stopped_partial = False
    wish.purchase_id = created_ids[0]
    await _reset_approvals(wish.id, db)
    await db.flush()

    purchase = await db.get(Purchase, created_ids[0])

    # «Заявка не должна остаться дублем» (владелец): заявка сохраняла своё
    # исходное название («Кабель для сервера» и т.п.) — на вкладке «Заявки»
    # это выглядело бы как всё ещё не обработанная заявка на закупку. Дублей
    # не заводим (см. докстринг выше) — приводим название к ЕДИНОМУ формату,
    # который уже используется для КАЖДОЙ авто-заявки на возмещение при прямом
    # создании авансового (app/routers/purchases.py::create_purchase, ветка
    # is_advance: `f"Возмещение по авансовому отчёту {p.registry_number}"`) —
    # тот же источник форматирования, не второй. Так эта запись в реестре
    # заявок выглядит РОВНО как остальные ~20 таких же компаньонов, а не как
    # зависшая копия исходной заявки.
    wish_title = f"Возмещение по авансовому отчёту {purchase.registry_number or f'#{purchase.id}'}"
    wish.title = wish_title[:499]

    # Диагностическая метка для роутера (не персистится) — что именно отменили,
    # чтобы вернуть это фронту в ответе (владелец: «отказ/результат всегда
    # с понятной причиной», по аналогии с wish._excess_warnings/_purchase_sync и т.п.).
    wish._advance_conversion_cancelled_purchases = cancelled_purchase_labels
    return purchase
