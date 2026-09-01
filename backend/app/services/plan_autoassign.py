"""Автозаведение плановой позиции ФЭО (FeoPlannedItem) по позиции заявки/закупки.

Вынесено из app.routers.wishes._auto_assign_planned_items (владелец, план
zany-fluttering-mountain.md шаг 3, 2026-08-07) в отдельный сервис, чтобы им мог
пользоваться не только путь «заявка → закупка» (wishes.py), но и путь «закупка
создана/меняется в обход заявки» (purchases.py) — реальный случай с прода:
категория 3716 «Приобретение брендированных футболок участников финала»
(МИНПРОС) имела финансирование по ФЭО 175 000 ₽, ни одной плановой позиции и
закупку на 149 282,50 ₽ в статусе «Поставлено», потому что закупка была
создана не через заявку, а автозаведение раньше жило только в wishes.py.
Owner-решение: закупка сама становится планом — везде, где позиция закупки
получает feo_category_id без feo_planned_item_id, вызывается эта функция.

Поведение и текст докстринга ФУНКЦИИ НЕ ИЗМЕНЕНЫ относительно оригинала в
wishes.py — путь заявки не должен измениться ни на йоту при переносе.
"""
from typing import Optional

from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession


async def auto_assign_planned_items(
    items, fallback_category_id: Optional[int], db: AsyncSession, *, note: str = "автозаведением плана",
) -> None:
    """Инвариант «закупки вне плана не бывает» (владелец, 2026-08-07, план
    zany-fluttering-mountain.md шаг 3): КАЖДАЯ позиция без явной привязки
    (feo_planned_item_id ещё не проставлен — ни автоподбором, ни пользователем)
    находит существующую FeoPlannedItem по точному совпадению нормализованного
    имени В ПРЕДЕЛАХ категории, либо создаёт новую, и привязывается к ней.
    Явный выбор пользователя не перебивается — такие позиции сюда не попадают
    (проверка `feo_planned_item_id` до вызова функции для каждой it).

    Нормализация — ОБЩАЯ `app.services.text_match.normalize()` (та же, что и
    матчер плановых позиций / товаров), а НЕ отдельная копия `.strip().lower()`
    (была раньше — приёмка 2026-08-07 нашла её пятой копией нормализации в
    проекте). normalize() дополнительно убирает пунктуацию и схлопывает пробелы
    («Бумага А4,» и «Бумага А4» — одна позиция, это ожидаемо).

    Дедуп сравнивается ЦЕЛИКОМ В PYTHON, а не через SQL `lower(trim(name))`:
    так и было раньше, но `lower(trim())` в SQL не убирает пунктуацию, а
    `normalize()` в Python — убирает, поэтому смешивать их — рассинхрон
    (по SQL «Бумага А4,» ≠ «Бумага А4», по Python — равны, и уже к этой позиции
    неверно привязалось/не привязалось бы в зависимости от того, на какой
    стороне считать). Поэтому: для каждой категории все активные плановые
    позиции загружаются ОДИН раз, индексируются `normalize(name)`, и все
    дальнейшие сравнения (существующие + вновь созданные в этом же вызове) идут
    по одному и тому же индексу — обе стороны нормализуются одной функцией.

    Дублирует логику дедупа импорта Excel Ур.5 (feo_categories.py), но с
    нормализацией — источник тут свободный ввод (заявка/авансовый отчёт), а не
    структурированный файл.

    `items` — любые объекты с атрибутами item_name/quantity/unit/total_price/
    feo_category_id/feo_planned_item_id/over_plan — подходят и WishItem, и
    PurchaseItem (общий набор колонок, см. модели). Общий код, чтобы не плодить
    вторую копию: используется и для обычных заявок (WishItem, при переносе в
    План закупок), и для авансовых отчётов (PurchaseItem напрямую — см. вызов
    в _distribute_wish_to_purchases для source == 'advance_report', у которых
    Purchase создаётся раньше самой заявки и мимо обычного пути копирования),
    и для закупок, созданных/меняемых в обход заявки (purchases.py — создание/
    правка позиции существующей закупки, смена категории ФЭО у позиции).

    ВАЖНО (приёмка 2026-08-07, обнаружено эмпирически при проверке Шага 5):
    если у листа УЖЕ задан «ручной план ФЭО» напрямую (FeoCategory.
    planned_quantity/planned_amount — как «Great Wall POER (лист): 2×4 000 000»
    без дочерних FeoPlannedItem), для такой позиции НЕЛЬЗЯ заводить новую
    самоссылающуюся FeoPlannedItem (amount = собственная цена позиции): тогда
    1) assert_tz_not_over_plan сравнивал бы позицию САМУ С СОБОЙ — план листа
       (4 000 000/ед) навсегда обходится любой ценой, дефект 1 остаётся дырой;
    2) compute_feo_plan_tree (см. plan_consumption_by_category/
       ordered_consumption_by_category, exclude_planned_item_linked=True)
       исключает позиции с feo_planned_item_id из consumed/ordered ЛИСТА —
       сумма позиции стала бы невидимой для plan_manual листа НАВСЕГДА (лист
       вечно показывает «0 заказано» при реально потраченных деньгах — ровно
       те осиротевшие/задвоенные строки, из-за которых затевался этот план).
    В этом случае оставляем feo_planned_item_id = None: assert_tz_not_over_plan
    сам берёт план из FeoCategory.planned_quantity/planned_amount (ветка 2 её
    docstring), а дерево ФЭО считает позицию как обычный расход листа (без
    exclude_planned_item_linked) — ровно «псевдо-строка ручного плана»,
    описанная в плане (не изобретаем новую сущность, лист уже И ЕСТЬ план).
    Автозаведение НОВОЙ FeoPlannedItem остаётся только там, где на листе
    никакого плана вообще нет (сценарий «канцтовары» — много разных позиций,
    план вводится по факту заявки).
    Commit НЕ делает — это на вызывающем.
    """
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.feo_category import FeoCategory
    from app.services.text_match import normalize

    # cat_id -> {normalize(name): fpi_id}; загружается лениво, один раз на категорию.
    _cat_index: dict[int, dict[str, int]] = {}
    # cat_id -> есть ли у листа собственный «ручной план» (planned_quantity/amount)
    _cat_has_leaf_plan: dict[int, bool] = {}
    for it in items:
        if getattr(it, "feo_planned_item_id", None):
            continue
        eff_cat_id = getattr(it, "feo_category_id", None) or fallback_category_id
        if not eff_cat_id:
            continue
        norm_name = normalize(getattr(it, "item_name", None) or "")
        if not norm_name:
            continue
        index = _cat_index.get(eff_cat_id)
        if index is None:
            existing_res = await db.execute(
                select(FeoPlannedItem).where(
                    FeoPlannedItem.feo_category_id == eff_cat_id,
                    FeoPlannedItem.is_active == True,
                )
            )
            index = {}
            for fpi in existing_res.scalars().all():
                key = normalize(fpi.name or "")
                if key and key not in index:
                    index[key] = (fpi.id, fpi.item_type)  # первое совпадение побеждает при легаси-дублях в БД
            _cat_index[eff_cat_id] = index

            cat_row = await db.get(FeoCategory, eff_cat_id)
            _cat_has_leaf_plan[eff_cat_id] = bool(
                cat_row is not None
                and ((cat_row.planned_quantity or 0) > 0 or (cat_row.planned_amount or 0) > 0)
            )
        index = _cat_index[eff_cat_id]
        entry = index.get(norm_name)
        if entry is None:
            if _cat_has_leaf_plan.get(eff_cat_id):
                # У листа уже есть ручной план целиком — он и есть «план» этой
                # позиции (см. предупреждение в docstring выше). Не создаём
                # дублирующую FeoPlannedItem, оставляем позицию непривязанной —
                # assert_tz_not_over_plan и дерево ФЭО прочитают план с листа.
                continue
            # amount=it.total_price — снимок плана (Шаг 1 «план ≠ факт»): фиксируется
            # как план категории в момент постановки в план закупок.
            new_fpi = FeoPlannedItem(
                feo_category_id=eff_cat_id,
                name=getattr(it, "item_name", None),
                quantity=getattr(it, "quantity", None),
                unit=getattr(it, "unit", None),
                amount=getattr(it, "total_price", None),
                is_active=True,
                notes=f"Создано {note}",
                # Владелец (2026-08-18): «в позиции точно прописано, товар это или
                # услуга/работа... почему не подтягивается?» — тип известен у
                # исходной позиции заявки/закупки, незачем рождать плановую позицию
                # пустой. Уже заполненный item_type у существующих строк здесь не
                # трогаем (эта ветка — только создание НОВОЙ FeoPlannedItem).
                item_type=(getattr(it, "item_type", None) or None),
                # Задача владельца «закупка сама становится планом» (2026-08-12):
                # позиция заведена автоматически (не человеком) — фронт помечает
                # такие строки отдельно (см. auto_created в схеме FeoPlannedItemOut).
                auto_created=True,
                # Происхождение (владелец, 2026-09-01): автозаведённая позиция
                # никогда не была построчной разбивкой ФЭО — родилась из
                # реального расхода заявки/закупки, не из файла ФЭО (см.
                # докстринг миграции aa1b2c3d4e5f_feo_planned_item_origin.py).
                is_internal_plan=True,
            )
            db.add(new_fpi)
            await db.flush()
            entry = (new_fpi.id, new_fpi.item_type)
            index[norm_name] = entry  # следующая позиция этого же вызова с тем же
            # нормализованным именем (напр. «Бумага А4,» после «Бумага А4») найдёт
            # её здесь и не создаст вторую плановую строку.
        fpi_id, _fpi_item_type = entry
        it.feo_planned_item_id = fpi_id
        if hasattr(it, "over_plan"):
            it.over_plan = False
        # Признак «Товар/Услуга/Работа» (блок 1, план zany-fluttering-mountain.md):
        # свежепривязанная плановая позиция задаёт тип по умолчанию, если у самой
        # позиции заявки/закупки он ещё не заполнен — уже заполненный не трогаем.
        if _fpi_item_type and hasattr(it, "item_type") and not getattr(it, "item_type", None):
            it.item_type = _fpi_item_type

    # Позиции, у которых feo_planned_item_id был проставлен ДО этого вызова (явный
    # выбор пользователя/матчинг) — их сам цикл выше пропускает (см. continue в
    # начале), но проброс типа от плановой позиции им всё равно причитается.
    await backfill_item_type_from_plan(items, db)


async def backfill_item_type_from_plan(items, db: AsyncSession) -> None:
    """Признак «Товар/Услуга/Работа» (блок 1, план zany-fluttering-mountain.md,
    2026-08-14): если у позиции заявки/закупки item_type ещё пуст, а связанная
    плановая позиция (FeoPlannedItem.item_type) его знает — подставляем. Уже
    заполненный item_type НИКОГДА не перетирается (правило проекта — выбранное
    пользователем на предыдущем этапе не меняется само).

    Общая функция для WishItem и PurchaseItem (тот же набор атрибутов
    item_type/feo_planned_item_id, что и у auto_assign_planned_items выше) —
    вызывается как из неё самой (для позиций, у которых feo_planned_item_id уже
    был проставлен ДО вызова и поэтому не попал в её основной цикл), так и
    отдельно из мест, которые НЕ проходят через auto_assign_planned_items
    (см. app/routers/wishes.py::_sync_wish_items_to_purchases).

    Кэширует lookup по feo_planned_item_id внутри одного вызова — несколько
    позиций одной и той же плановой строки не порождают лишних SELECT.
    Commit НЕ делает — это на вызывающем.
    """
    from app.models.feo_planned_item import FeoPlannedItem

    _cache: dict[int, Optional[str]] = {}
    for it in items:
        if not hasattr(it, "item_type") or getattr(it, "item_type", None):
            continue
        fpi_id = getattr(it, "feo_planned_item_id", None)
        if not fpi_id:
            continue
        if fpi_id not in _cache:
            _cache[fpi_id] = (await db.execute(
                select(FeoPlannedItem.item_type).where(FeoPlannedItem.id == fpi_id)
            )).scalar_one_or_none()
        fpi_item_type = _cache[fpi_id]
        if fpi_item_type:
            it.item_type = fpi_item_type


# ---------------------------------------------------------------------------
# «Плановые позиции следуют за сменой категории» (владелец, 2026-08-17):
# если позиция заявки/закупки переезжает в другую категорию ФЭО, а у неё есть
# СОБСТВЕННАЯ плановая позиция (FeoPlannedItem), созданная из неё же и ни на
# кого больше не завязанная, — плановая позиция обязана переехать вместе с
# позицией (та же строка, тот же id, история/notes/sort_order не теряются), а
# не остаться сиротой в старой категории, пока auto_assign_planned_items выше
# заводит/находит новую по имени в категории-получателе. Если же на плановую
# позицию завязано что-то ещё (общий план на несколько закупок/заявку и её
# уже сконвертированную закупку одновременно) — переезд запрещён: трогаем
# только привязку переезжающей позиции, отдаём предупреждение вызывающему.
# ---------------------------------------------------------------------------

async def move_planned_item_to_category(db: AsyncSession, fpi, new_category_id: int) -> None:
    """Единая логика «переезда» FeoPlannedItem в другую категорию ФЭО вместе со
    ВСЕМИ позициями закупок/заявок, которые на неё ссылаются (feo_planned_item_id).

    Вынесено из app.routers.feo_planned_items.update_planned_item (там раньше
    жила единственная копия этой логики — ручной перенос человеком через
    PUT /feo-planned-items/{id}), чтобы её же мог переиспользовать автоматический
    перенос вслед за позицией заявки/закупки (см. move_or_detach_planned_item
    ниже) — без второй копии того же SQL.

    Каскад теперь покрывает и PurchaseItem, и WishItem (раньше в
    update_planned_item каскадился только PurchaseItem — если на ту же плановую
    позицию была ещё жива ссылка WishItem несконвертированной заявки, она
    расходилась с новой категорией; тот же класс бага, что и с PurchaseItem).
    Commit — на вызывающем.
    """
    from app.models.purchase_item import PurchaseItem
    from app.models.wish_item import WishItem

    fpi.feo_category_id = new_category_id
    await db.execute(
        sql_update(PurchaseItem)
        .where(PurchaseItem.feo_planned_item_id == fpi.id)
        .values(feo_category_id=new_category_id)
    )
    await db.execute(
        sql_update(WishItem)
        .where(WishItem.feo_planned_item_id == fpi.id)
        .values(feo_category_id=new_category_id)
    )


async def _fpi_reference_keys(db: AsyncSession, fpi_id: int) -> set:
    """Множество «логических владельцев» плановой позиции fpi_id.

    Заявка, сконвертированная в закупку, оставляет ДВЕ строки с одним и тем же
    feo_planned_item_id (WishItem — заморожена, PurchaseItem.wish_item_id её
    зеркалит, см. app/routers/wishes.py — конвертация копирует
    feo_planned_item_id в PurchaseItem). Это ОДНА логическая позиция, а не два
    независимых потребителя плана — иначе перенос никогда не считался бы
    «эксклюзивным» ни для одной сконвертированной заявки. Ключ:
      - PurchaseItem с wish_item_id → ('wish_item', wish_item_id) — та же
        позиция, что и её исходная WishItem;
      - PurchaseItem без wish_item_id (заведена прямо в закупке) →
        ('purchase_item', id);
      - WishItem → ('wish_item', id).
    """
    from app.models.purchase_item import PurchaseItem
    from app.models.wish_item import WishItem

    keys: set = set()
    pi_rows = (await db.execute(
        select(PurchaseItem.id, PurchaseItem.wish_item_id)
        .where(PurchaseItem.feo_planned_item_id == fpi_id)
    )).all()
    for pid, wiid in pi_rows:
        keys.add(("wish_item", wiid) if wiid is not None else ("purchase_item", pid))
    wi_rows = (await db.execute(
        select(WishItem.id).where(WishItem.feo_planned_item_id == fpi_id)
    )).all()
    for (wid,) in wi_rows:
        keys.add(("wish_item", wid))
    return keys


async def deactivate_if_orphaned(db: AsyncSession, fpi) -> None:
    """Правило уборки: плановая позиция, заведённая АВТОМАТИЧЕСКИ
    (auto_created=True) из заявки/закупки и оставшаяся без единой привязки
    (ни одна PurchaseItem/WishItem больше на неё не ссылается — значит и
    расход по ней нулевой), деактивируется (is_active=False), а не удаляется
    физически — история (created_at/notes/сумма) остаётся в БД для аудита, но
    позиция пропадает из всех расчётов плана: compute_feo_plan_tree/
    plan_consumption_by_category/plan-positions/_load_plan_catalog — везде
    фильтр FeoPlannedItem.is_active == True (см. app/services/feo_plan.py).

    Плановые позиции, заведённые ЧЕЛОВЕКОМ (auto_created=False), НИКОГДА не
    трогаются здесь, даже без привязок и расхода — их деактивирует/удаляет
    только явное действие человека (DELETE /feo-planned-items/{id} или
    снятие галочки «активна» через PUT).
    """
    if fpi is None or not fpi.is_active or not fpi.auto_created:
        return
    keys = await _fpi_reference_keys(db, fpi.id)
    if keys:
        return
    fpi.is_active = False


async def move_or_detach_planned_item(db: AsyncSession, item, new_category_id: int) -> Optional[str]:
    """Позиция заявки/закупки (`item` — WishItem или PurchaseItem с уже
    актуальным `.feo_category_id`, но ещё старым `.feo_planned_item_id`)
    переезжает в другую категорию ФЭО. Решает судьбу её привязки к плановой
    позиции (FeoPlannedItem):

    - если у плановой позиции нет других владельцев (см. _fpi_reference_keys) —
      плановая позиция физически переезжает в новую категорию ВМЕСТЕ с item
      (move_planned_item_to_category), привязка item.feo_planned_item_id не
      меняется — возвращает None (без предупреждения, переезд тихий и полный);
    - если у плановой позиции есть другие владельцы (общий план на несколько
      закупок/заявку и её уже сконвертированную закупку одновременно) —
      трогать её нельзя (испортит план для остальных владельцев): у ПЕРЕЕЗЖАЮЩЕЙ
      позиции привязка снимается (item.feo_planned_item_id = None, over_plan
      сбрасывается — так же, как раньше делал безусловный сброс в
      purchases.py::patch_purchase_item), а плановая позиция проверяется на
      «уборку» (см. deactivate_if_orphaned — на практике здесь она НЕ
      осиротеет, т.к. по условию ветки у неё есть другие владельцы; проверка
      оставлена как страховка) и возвращается ЯВНОЕ текстовое предупреждение —
      вызывающий обязан вернуть его в ответе API, не проглатывать молча.

    Само item.feo_category_id уже должно быть проставлено ДО вызова (вызывающий
    применяет новую категорию сам, эта функция её не трогает) — new_category_id
    передаётся отдельно, т.к. может понадобиться раньше присвоения (см.
    purchases.py::patch_purchase_item, где категория применяется в начале
    функции). Commit — на вызывающем.
    """
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.feo_category import FeoCategory
    from app.models.purchase_item import PurchaseItem
    from app.models.wish_item import WishItem

    fpi_id = getattr(item, "feo_planned_item_id", None)
    if not fpi_id:
        return None
    fpi = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == fpi_id)
    )).scalar_one_or_none()
    if fpi is None:
        # Привязка на несуществующую строку (данные разъехались раньше) — просто чистим.
        item.feo_planned_item_id = None
        return None
    if fpi.feo_category_id == new_category_id:
        return None  # уже там — нечего переносить

    if isinstance(item, PurchaseItem):
        self_key = ("wish_item", item.wish_item_id) if item.wish_item_id is not None else ("purchase_item", item.id)
    elif isinstance(item, WishItem):
        self_key = ("wish_item", item.id)
    else:
        self_key = None

    all_keys = await _fpi_reference_keys(db, fpi_id)
    other_keys = all_keys - ({self_key} if self_key is not None else set())

    if not other_keys:
        await move_planned_item_to_category(db, fpi, new_category_id)
        return None

    old_cat_name = (await db.execute(
        select(FeoCategory.name).where(FeoCategory.id == fpi.feo_category_id)
    )).scalar_one_or_none()
    item.feo_planned_item_id = None
    if hasattr(item, "over_plan"):
        item.over_plan = False
    await deactivate_if_orphaned(db, fpi)  # страховка — см. докстринг
    return (
        f"Плановая позиция «{fpi.name}» используется ещё и другими закупками/заявками — "
        f"привязка снята, сама плановая позиция осталась в категории «{old_cat_name or '—'}»."
    )
