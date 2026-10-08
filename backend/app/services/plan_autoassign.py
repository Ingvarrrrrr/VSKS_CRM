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
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import feo_history


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
    from app.services.feo_import_common import resolve_origin_flags
    from app.services.text_match import normalize
    from app.services.feo_plan_duplicate_match import find_unique_feo_plan_match
    from app.services import feo_history

    # cat_id -> {normalize(name): fpi_id}; загружается лениво, один раз на категорию.
    _cat_index: dict[int, dict[str, int]] = {}
    # cat_id -> есть ли у листа собственный «ручной план» (planned_quantity/amount)
    _cat_has_leaf_plan: dict[int, bool] = {}
    # cat_id -> subsidy_id (для поиска по всей субсидии ниже)
    _cat_subsidy_id: dict[int, Optional[int]] = {}
    # subsidy_id -> [FeoPlannedItem НЕ-auto, is_active] всей субсидии; лениво,
    # нужен только когда внутри своей категории пары не нашлось (см. ниже).
    _subsidy_candidates: dict[int, list] = {}
    # subsidy_id -> {id уже занятых в ЭТОМ вызове дублей} — каждая настоящая
    # позиция ФЭО может быть парой только ОДНОМУ дублю этого же прогона
    # (см. докстринг find_unique_feo_plan_match).
    _subsidy_claimed: dict[int, set] = {}
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
            _cat_subsidy_id[eff_cat_id] = cat_row.subsidy_id if cat_row is not None else None
        index = _cat_index[eff_cat_id]
        entry = index.get(norm_name)
        if entry is None:
            if _cat_has_leaf_plan.get(eff_cat_id):
                # У листа уже есть ручной план целиком — он и есть «план» этой
                # позиции (см. предупреждение в docstring выше). Не создаём
                # дублирующую FeoPlannedItem, оставляем позицию непривязанной —
                # assert_tz_not_over_plan и дерево ФЭО прочитают план с листа.
                continue

            # Причина бага с прода (см. докстринг feo_plan_duplicate_match.py):
            # прежде чем заводить НОВУЮ auto_created позицию, проверяем, нет ли
            # уже настоящей (не-auto) позиции ФЭО с тем же именем+суммой в
            # ДРУГОЙ категории ЭТОЙ ЖЕ субсидии — если позиция заявки/закупки
            # осталась без собственной feo_category_id (упала в fallback,
            # обычно «Не определена»), её план скорее всего уже где-то есть.
            _sid = _cat_subsidy_id.get(eff_cat_id)
            matched_fpi_id = None
            matched_item_type = None
            if _sid is not None:
                candidates = _subsidy_candidates.get(_sid)
                if candidates is None:
                    cand_res = await db.execute(
                        select(FeoPlannedItem)
                        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
                        .where(
                            FeoCategory.subsidy_id == _sid,
                            FeoPlannedItem.is_active == True,
                            FeoPlannedItem.auto_created == False,
                        )
                    )
                    candidates = cand_res.scalars().all()
                    _subsidy_candidates[_sid] = candidates
                claimed = _subsidy_claimed.setdefault(_sid, set())
                matched_fpi_id, _how = find_unique_feo_plan_match(
                    getattr(it, "item_name", None), getattr(it, "total_price", None),
                    candidates, claimed,
                )
                if matched_fpi_id is not None:
                    claimed.add(matched_fpi_id)
                    matched_item_type = next(
                        (c.item_type for c in candidates if c.id == matched_fpi_id), None,
                    )
                    matched_cat_id = next(
                        (c.feo_category_id for c in candidates if c.id == matched_fpi_id), eff_cat_id,
                    )
                    # Позиция заявки/закупки переезжает вслед за найденным планом
                    # (правило проекта: план и факт в одной категории) — та же
                    # сама идея, что и move_or_detach_planned_item, но здесь
                    # позиция ещё ни на что не ссылалась, переносить нечего,
                    # кроме самой feo_category_id.
                    if hasattr(it, "feo_category_id") and matched_cat_id != eff_cat_id:
                        it.feo_category_id = matched_cat_id

            if matched_fpi_id is not None:
                entry = (matched_fpi_id, matched_item_type)
                # В локальный индекс категории НЕ кладём: это позиция из чужой
                # категории, следующий дубль этого же вызова с таким же именем
                # обязан пройти ту же проверку «не занято ли уже» (claimed).
            else:
                new_fpi = await create_auto_planned_item(db, it, eff_cat_id, note)
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


async def create_auto_planned_item(db: AsyncSession, it, eff_cat_id: int, note: str):
    """Строит, сохраняет и журналирует НОВУЮ auto_created=True FeoPlannedItem
    из позиции заявки/закупки (`it` — WishItem/PurchaseItem, тот же набор
    атрибутов item_name/quantity/unit/total_price/unit_price/item_type/
    wish_id/purchase_id, что и в auto_assign_planned_items выше).

    Вынесено из тела auto_assign_planned_items (Правило №6, 30.09.2026) —
    ЕДИНСТВЕННОЕ место, конструирующее авто-плановую позицию: используется и
    здесь (дедуп по точному совпадению имени внутри категории — см. вызов
    выше), и app.services.advance_auto_plan.sync_advance_auto_plan_items
    (авансовые отчёты — владелец, 30.09.2026, «не сопоставляем»: КАЖДАЯ
    позиция получает свою собственную плановую БЕЗ поиска существующей по
    имени, но сама плановая строится совершенно так же).

    db.flush() делает сама (нужен id для истории/присвоения). Commit — на
    вызывающем.
    """
    from app.models.feo_planned_item import FeoPlannedItem
    from app.services.feo_import_common import resolve_origin_flags

    # amount=it.total_price — снимок плана (Шаг 1 «план ≠ факт»): фиксируется
    # как план категории в момент постановки в план закупок.
    _origin_is_feo_breakdown, _origin_is_internal_plan = resolve_origin_flags(
        None, getattr(it, "total_price", None),
    )
    new_fpi = FeoPlannedItem(
        feo_category_id=eff_cat_id,
        name=getattr(it, "item_name", None),
        quantity=getattr(it, "quantity", None),
        unit=getattr(it, "unit", None),
        amount=getattr(it, "total_price", None),
        # Цена за единицу (владелец, 2026-09-02) — снимок реальной цены
        # строки, из которой рождается план (см. FeoPlannedItem.unit_price
        # и assert_tz_not_over_plan в feo_plan.py). Заполняем, ЧТОБЫ НЕ
        # РЕГРЕССИРОВАТЬ прежний контроль превышения: у автозаведённой
        # позиции цена известна точно (это цена самой закупаемой строки),
        # поэтому она не должна молча попадать в «мягкий» режим (сумма без
        # ограничения количества/цены), уготованный для позиций, где
        # человек сознательно указал только общую сумму.
        unit_price=getattr(it, "unit_price", None),
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
        # родилась из реального расхода заявки/закупки, не из файла ФЭО —
        # раздела «Сумма по ФЭО» у неё нет по построению (это не строка
        # Excel-импорта), поэтому feo_money=None. Флаги считает та же
        # resolve_origin_flags, что и импорт ФЭО (Правило №6, единственный
        # источник в feo_import_common.py) — при feo_money=None она
        # детерминированно отдаёт (False, True), то же самое, что было
        # здесь захардкожено раньше, без второй копии правила «денег в
        # ФЭО нет — значит внутренний план».
        is_feo_breakdown=_origin_is_feo_breakdown,
        is_internal_plan=_origin_is_internal_plan,
    )
    db.add(new_fpi)
    await db.flush()
    # Журнал ФЭО (волна 2) — «если плановая появилась из заявки/закупки,
    # пишется, на основании какой» (владелец, дословно, задание волны 2).
    # `items` — WishItem или PurchaseItem (см. докстринг функции): у
    # WishItem source_ref — сама заявка (wish_id), у PurchaseItem — сама
    # закупка (purchase_id). `user`/changed_by остаётся NULL здесь
    # намеренно — по source_ref уже видно происхождение (заявка/закупка),
    # а КТО её завёл/отредактировал — читается из истории самой заявки/
    # закупки, не дублируем это дважды (Правило №6).
    _wish_id = getattr(it, "wish_id", None)
    _purchase_id = getattr(it, "purchase_id", None)
    if _wish_id is not None:
        await feo_history.record_created(
            db, feo_history.ENTITY_FEO_ITEM, new_fpi.id, None,
            source=feo_history.SOURCE_WISH, source_ref=_wish_id, commit=False,
        )
    elif _purchase_id is not None:
        await feo_history.record_created(
            db, feo_history.ENTITY_FEO_ITEM, new_fpi.id, None,
            source=feo_history.SOURCE_PURCHASE, source_ref=_purchase_id, commit=False,
        )
    else:
        await feo_history.record_created(
            db, feo_history.ENTITY_FEO_ITEM, new_fpi.id, None,
            source=feo_history.SOURCE_AUTOASSIGN, commit=False,
        )
    return new_fpi


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

async def move_planned_item_to_category(
    db: AsyncSession, fpi, new_category_id: int, *, record_history: bool = True,
    source: str = feo_history.SOURCE_AUTOASSIGN, source_ref: Optional[int] = None,
) -> None:
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

    `record_history=False` — feo_planned_items.py::update_planned_item
    передаёт: тот эндпоинт уже пишет ОДИН общий дифф всей позиции (включая
    feo_category_id) сам, вызывая эту функцию как часть своей обработки —
    вторая запись здесь задвоила бы историю одного и того же PUT (Правило
    проекта: одно сохранение — одна запись). Автоматический перенос вслед за
    сменой категории позиции закупки/заявки (move_or_detach_planned_item ниже)
    — единственный путь БЕЗ своего диффа выше по стеку, там остаётся True.
    """
    from app.models.purchase_item import PurchaseItem
    from app.models.wish_item import WishItem

    _old_cat_id = fpi.feo_category_id
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
    # Журнал ФЭО (волна 2) — переезд плановой позиции вслед за сменой категории
    # позиции закупки/заявки (см. move_or_detach_planned_item ниже). Вызов из
    # PUT /feo-planned-items/{id} (feo_planned_items.py) уже пишет свой
    # record_updated с полным диффом позиции ДО/ПОСЛЕ — здесь source='manual'
    # тоже подходит (перенос инициирован человеком: либо через PUT напрямую,
    # либо через смену категории у позиции закупки/заявки), поэтому пишем
    # безусловно; при двойном вызове (PUT уже залогировал feo_category_id в
    # своём общем дифф-снимке) это просто вторая строка с тем же изменением —
    # entity_changes не дедуплицирует построчные записи, это уже так для
    # остальных полей (Правило проекта: одно сохранение — одна запись, здесь
    # тот редкий случай двух разных вызывающих путей на одно и то же поле).
    if record_history and _old_cat_id != new_category_id:
        await feo_history.record_updated(
            db, feo_history.ENTITY_FEO_ITEM, fpi.id, None,
            {"feo_category_id": _old_cat_id}, {"feo_category_id": new_category_id},
            source=source, source_ref=source_ref, commit=False,
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
    from app.services import feo_history
    await feo_history.record_updated(
        db, feo_history.ENTITY_FEO_ITEM, fpi.id, None,
        {"is_active": True}, {"is_active": False},
        source=feo_history.SOURCE_AUTOASSIGN, commit=False,
    )


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


# ---------------------------------------------------------------------------
# Расхождение категорий при явной привязке к плановой позиции (владелец,
# 2026-09-02, этапы 2-3 плана исправления расхождения категорий ФЭО): ОДИН
# общий хелпер для двух путей, которыми человек привязывает PurchaseItem к
# конкретной FeoPlannedItem —
#   - PATCH /purchases/{pid}/items/{item_id} (явный выбор плановой позиции в
#     диалоге «Редактировать позицию», см. app/routers/purchases.py::patch_purchase_item);
#   - POST /feo-planned-items/map (сопоставление факта с планом на дашборде
#     ФЭО, см. app/routers/feo_planned_items.py::map_purchase_item_to_planned) —
#     раньше этот путь молча ПЕРЕНОСИЛ позицию закупки в категорию плановой
#     позиции, создавая расхождение с шапкой закупки (feo_per_item=False),
#     которое PATCH выше как раз запрещает — правило разъезжалось.
# Копировать правило по обоим местам нельзя (см. правило проекта) — обе точки
# теперь зовут ЭТУ функцию.
# ---------------------------------------------------------------------------

async def check_planned_item_category_link(
    db: AsyncSession,
    *,
    purchase,
    item,
    item_category_id: Optional[int],
    planned_category_id: Optional[int],
    planned_item_name: str,
    current_user,
) -> None:
    """Проверка соответствия категорий при привязке PurchaseItem к FeoPlannedItem.

    Совпадение — planned_category_id равен item_category_id ИЛИ является его
    потомком (см. app.routers.purchases._category_within, тот же обход дерева
    вверх по parent_id; здесь не дублируется, импортируется лениво).

    При несовпадении:
      - обычному пользователю — HTTPException 409 с detail={code, message},
        сообщение ведёт к решению, а не просто сообщает о проблеме: выбрать
        плановую позицию из категории закупки либо создать её кнопкой
        «Создать в плане закупок»;
      - суперадмину — привязка разрешена, но уведомление уходит согласовавшим
        закупку (PurchaseApproval.status == 'approved') и ответственному/
        назначенному (purchase.assigned_user_id) — тот же паттерн получателей,
        что и app.routers.purchases._guard_feo_category_change_after_approval,
        без дублей (set по user_id).

    item_category_id=None (у закупки нет ни своей, ни шапочной категории) —
    сравнивать не с чем, пропускаем без 409 (пустая категория — отдельная
    проблема, не эта проверка). planned_category_id=None — тоже пропуск
    (снятие привязки идёт другим путём, сюда не попадает).

    Ничего не пишет в БД, не коммитит — только проверка + отправка
    уведомления (у notify_user свой commit внутри, как и у остальных мест,
    использующих этот паттерн)."""
    if planned_category_id is None or item_category_id is None:
        return
    from app.routers.purchases import _category_within  # lazy — против цикла импорта модулей на старте
    if await _category_within(db, planned_category_id, item_category_id):
        return

    from app.models.feo_category import FeoCategory

    async def _cat_name(cid: Optional[int]) -> str:
        if cid is None:
            return "без категории ФЭО"
        cat = await db.get(FeoCategory, cid)
        return (cat.name if cat else None) or f"#{cid}"

    item_cat_name = await _cat_name(item_category_id)
    planned_cat_name = await _cat_name(planned_category_id)

    if current_user.role != "superadmin":
        raise HTTPException(
            409,
            detail={
                "code": "PLANNED_ITEM_CATEGORY_MISMATCH",
                "message": (
                    f"Плановая позиция «{planned_item_name}» относится к категории «{planned_cat_name}», "
                    f"а позиция закупки — к категории «{item_cat_name}». Выберите плановую позицию из "
                    f"категории закупки, либо создайте новую кнопкой «Создать в плане закупок»."
                ),
            },
        )

    # Суперадмин: привязка разрешена, но согласовавшие и ответственный должны узнать.
    from app.notifications import notify_user, _esc, _purchase_url
    from app.models.purchase_approval import PurchaseApproval
    from app.models.user import User

    from app.services.purchase_label import purchase_label as _purchase_label_fmt

    actor_name = current_user.full_name or current_user.username
    when = datetime.now().strftime("%d.%m.%Y %H:%M")
    item_name = getattr(item, "item_name", None) or "Без названия"
    text = (
        f"⚠️ <b>Плановая позиция чужой категории привязана к закупке</b>\n\n"
        f"📌 Закупка {_purchase_label_fmt(purchase)}\n"
        f"👤 {_esc(actor_name)} привязал(а) {when} позицию «{_esc(item_name)}» "
        f"к плановой позиции «{_esc(planned_item_name)}» категории «{_esc(planned_cat_name)}», "
        f"хотя категория самой позиции закупки — «{_esc(item_cat_name)}»."
    )

    recipient_ids: set = set()
    result = await db.execute(
        select(PurchaseApproval.user_id).where(
            PurchaseApproval.purchase_id == purchase.id,
            PurchaseApproval.status == "approved",
            PurchaseApproval.user_id.isnot(None),
        )
    )
    for uid in result.scalars().all():
        recipient_ids.add(uid)
    if getattr(purchase, "assigned_user_id", None):
        recipient_ids.add(purchase.assigned_user_id)

    for uid in recipient_ids:
        u = await db.get(User, uid)
        if u:
            await notify_user(u, text, button_url=_purchase_url(purchase.id), button_label="Открыть закупку")
