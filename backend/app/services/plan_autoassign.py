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

from sqlalchemy import select
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
                # Задача владельца «закупка сама становится планом» (2026-08-12):
                # позиция заведена автоматически (не человеком) — фронт помечает
                # такие строки отдельно (см. auto_created в схеме FeoPlannedItemOut).
                auto_created=True,
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
