from datetime import date as _Date_
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab, has_org_key, _has_key_in_any_org
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.schemas import (
    FeoPlannedItemCreate, FeoPlannedItemOut,
    FeoPlannedItemBulkCreate, FeoPlannedItemBulkCreateResult,
)
from app.services.text_match import normalize as _norm_text
from app.services.feo_monthly_schedule import compute_monthly_schedule
# normalize_item_type/ITEM_TYPES/apply_item_type_to_product раньше жили здесь
# (нормализатор был написан прямо в этом роутере) — вынесены в
# app/services/item_types.py (ПРАВИЛО №6, 21.09, раздел W2 плана
# corrections-21-09.md), чтобы Product.item_kind не заводил свою копию
# нормализации. Имя normalize_item_type РЕЭКСПОРТИРУЕТСЯ отсюда без изменений
# — app/services/feo_import_apply.py и app/services/item_type_split.py
# продолжают делать `from app.routers.feo_planned_items import
# normalize_item_type` как раньше, ничего в них менять не нужно.
from app.services.item_types import (  # noqa: F401 (normalize_item_type — реэкспорт)
    normalize_item_type, apply_item_type_to_product, resolve_product_for_planned_item,
)
from app.models.product import Product
from app.services import feo_history
from app.services.feo_planned_item_amount import backfill_unit_price_on_quantity_change
# Волна «Корректировка утверждённой субсидии через проверку» (02.10.2026,
# план breezy-mixing-lovelace.md): тела create/bulk/update/delete вынесены в
# сервис (Правило №6 — одна точка записи, применение корректировки позже
# будет звать её же). _apply_payment_fields/_check_planned_item_write_access/
# _can_edit_feo_origin ОСТАЮТСЯ здесь (их по модулю импортируют
# feo_comments.py и test_planned_item_monthly_period.py) — feo_item_write.py
# импортирует их лениво (внутри функций), во избежание цикл. импорта.
from app.services import feo_item_write


def _apply_payment_fields(item: FeoPlannedItem, data: FeoPlannedItemCreate) -> None:
    """
    W1b + Волна 3, п.3 (владелец, «период с даты по дату вместо целого
    "Количество месяцев"»): единственное место, где monthly-позиция считает
    свою итоговую сумму — через compute_monthly_schedule (app/services/
    feo_monthly_schedule.py, Правило №6 проекта, тот же расчёт использует
    предпросмотр monthly_schedule_preview ниже и cash-flow разворачивание
    в plan_cashflow.expand_planned_item).

      monthly + monthly_end_date задана → период "с даты по дату": полные
        месяцы + остаток дней ÷ длина того месяца, куда остаток попадает.
        months_count ПЕРЕЗАПИСЫВАЕТСЯ вычисленным значением (полные месяцы) —
        ручной ввод данных больше не принимается, но поле остаётся для
        обратной совместимости с cash-flow-разворачиванием/экспортом.
      monthly БЕЗ даты окончания (легаси-позиции с ручным months_count) →
        старая арифметика monthly_amount × months_count, без остатка.
      one_time → amount как есть, ручной ввод.

    Волна 3, п.2 (владелец, «двоится Количество»): для monthly-режима
    quantity — количество ЕДИНИЦ товара/услуги, а не срок. У ежемесячного
    платежа этот параметр не участвует в формуле суммы вообще (сумма — только
    monthly_amount × срок), реального смысла «сколько единиц» тут обычно нет
    (аренда, подписка — это одна позиция), а ручной ввод сюда исторически и
    создавал боевой баг («Кол-во» 6.66, всплывавшее как плановое количество
    категории — см. SUM(FeoPlannedItem.quantity) в
    feo_planned_items_reports.py::cat_plan_fallback). Поле скрыто в
    PlannedItemAddDialog.vue/PlannedItemEditDialog.vue для monthly-режима —
    фиксируем 1 и здесь же, на бэкенде, чтобы прямой вызов API тоже не мог
    протащить произвольное число.
    """
    item.payment_mode = data.payment_mode
    item.planned_date = data.planned_date
    item.monthly_start_date = data.monthly_start_date
    item.monthly_end_date = data.monthly_end_date
    item.monthly_amount = data.monthly_amount

    if data.payment_mode == "monthly":
        schedule = compute_monthly_schedule(
            start_date=data.monthly_start_date,
            end_date=data.monthly_end_date,
            months_count=data.months_count,
            monthly_amount=data.monthly_amount,
        )
        item.months_count = schedule.effective_months_count
        if schedule.total is not None:
            item.amount = schedule.total
        # else: недостаточно данных — оставляем прежнее amount как было
        item.quantity = Decimal("1")
    else:
        # one_time: honour the manually supplied amount and quantity
        item.amount = data.amount
        item.quantity = data.quantity

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


@router.get("/monthly-schedule-preview")
async def monthly_schedule_preview(
    start_date: Optional[_Date_] = Query(None, description="Начало периода (monthly_start_date)"),
    end_date: Optional[_Date_] = Query(None, description="Конец периода (monthly_end_date)"),
    monthly_amount: Optional[Decimal] = Query(None),
    _=Depends(get_current_user),
):
    """Живая расшифровка периода «с даты по дату» для диалогов добавления/
    правки плановой позиции (PlannedItemAddDialog.vue/PlannedItemEditDialog.vue,
    Волна 3, п.2-3 владельца) — «6 мес. 20 дн.» и итоговая сумма ДО сохранения.
    Единственная формула — compute_monthly_schedule (см. её докстринг и
    _apply_payment_fields выше, Правило №6): один расчёт и здесь, и при
    сохранении, и в cash-flow разворачивании (plan_cashflow.py), числа не
    могут разойтись между предпросмотром и итогом.
    """
    if start_date is not None and end_date is not None and end_date <= start_date:
        raise HTTPException(400, "Дата окончания периода должна быть позже даты начала")
    schedule = compute_monthly_schedule(start_date, end_date, None, monthly_amount)
    return {
        "full_months": schedule.full_months,
        "extra_days": schedule.extra_days,
        "label": schedule.label,
        "total": str(schedule.total) if schedule.total is not None else None,
    }


async def _check_planned_item_write_access(current_user, db: AsyncSession, cat: FeoCategory) -> None:
    """Общая проверка доступа к созданию/удалению плановой позиции (Ур.5
    FeoPlannedItem) — вынесена из create_planned_item (см. её докстринг,
    владелец 2026-08-19), чтобы delete_planned_item проверял ровно ту же
    матрицу доступа, а не дублировал условия:
      superadmin ЛИБО вкладка feo_categories ЛИБО право wish.edit_feo по
      субсидии категории ЛИБО вкладка wishes/purchases (кто заводит
      заявки/закупки, должен уметь поправить недостающую/лишнюю плановую
      позицию под них).
    has_org_key (НЕ _has_key_in_any_org/_get_effective) — ненаследующая
    проверка: иерархия «ставлю задачи» не даёт права на чужую субсидию.
    POST /bulk, PUT /{id}, /map по-прежнему НЕ используют этот хелпер —
    остаются доступны только через вкладку feo_categories (владелец
    ограничил задачу именно созданием/удалением одиночной позиции).
    """
    if current_user.role == "superadmin":
        return
    has_tab = await _has_key_in_any_org(current_user, db, 'feo_categories')
    has_edit_feo = False
    if not has_tab and cat.subsidy_id is not None:
        subsidy = (await db.execute(
            select(Subsidy).where(Subsidy.id == cat.subsidy_id)
        )).scalar_one_or_none()
        if subsidy is not None:
            has_edit_feo = await has_org_key(
                current_user, db, subsidy.org_id, "wish.edit_feo", subsidy_id=subsidy.id,
            )
    has_wishes_or_purchases = False
    if not has_tab and not has_edit_feo:
        has_wishes_or_purchases = (
            await _has_key_in_any_org(current_user, db, 'wishes')
            or await _has_key_in_any_org(current_user, db, 'purchases')
        )
    if not has_tab and not has_edit_feo and not has_wishes_or_purchases:
        raise HTTPException(
            403,
            "Нет доступа к справочнику ФЭО, нет права на перераспределение позиций "
            "заявки по категориям ФЭО и нет вкладки заявок/закупок — действие с "
            "плановой позицией недоступно",
        )


async def _can_edit_feo_origin(current_user, db: AsyncSession) -> bool:
    """Владелец (2026-09-01): «тот человек, который может править ФЭО, может
    менять и статус происхождения» (is_feo_breakdown/is_internal_plan) —
    ровно вкладка feo_categories (та же граница, что и у PUT/bulk/import в
    этом файле и в feo_categories.py), а НЕ вся расширенная матрица
    _check_planned_item_write_access (wish.edit_feo/wishes/purchases — те
    дают право создать/удалить недостающую позицию, но не переставлять её
    признак «по ФЭО»/«внутренний план»). Обычному автору заявки, у которого
    нет вкладки ФЭО, менять признак не нужно — create_planned_item просто
    тихо игнорирует эти два поля, если их прислали без права (не 403 —
    остальная часть запроса, создание самой позиции, доступ имеет)."""
    if current_user.role == "superadmin":
        return True
    return await _has_key_in_any_org(current_user, db, 'feo_categories')


@router.get("/", response_model=List[FeoPlannedItemOut])
async def list_planned_items(
    feo_category_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        # Владелец (2026-08-12): позиции можно переставлять местами вручную —
        # sort_order, если задан, а незаполненные (легаси/автозаведённые) —
        # следом в порядке создания.
        .order_by(FeoPlannedItem.sort_order.nulls_last(), FeoPlannedItem.id)
    )).scalars().all()
    return rows


@router.post("/", response_model=FeoPlannedItemOut)
async def create_planned_item(
    data: FeoPlannedItemCreate,
    # Заявка/закупка, из формы/конвертации которой создаётся плановая позиция
    # (FeoPlannedItemsSelect.vue в форме заявки/закупки). Создание ПОД заявку/
    # закупку — это НЕ корректировка субсидии (см.
    # app.services.subsidy_revision_guard.assert_direct_edit), гейт прямой
    # правки здесь не вызывается, но контекст обязан реально относиться к той
    # же субсидии, что и категория — иначе 422 (см. ниже).
    #
    # ⚠️ БЕЗ Query(...) (простой default=None) НАМЕРЕННО: тесты этого роутера
    # (test_feo_history_wave2.py и соседи) зовут create_planned_item напрямую
    # как обычную Python-функцию, минуя FastAPI DI — Query(None) вместо
    # обёртки был бы передан внутрь как объект fastapi.Query, а не None.
    # FastAPI одинаково резолвит безымянный скаляр с дефолтом как query-параметр
    # и через реальный HTTP-запрос, так что поведение API не меняется.
    wish_id: Optional[int] = None,
    purchase_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == data.feo_category_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Категория ФЭО не найдена")

    # Владелец (2026-08-19): «поправить распределение не должно давать
    # возможность переделывать всё ФЭО» — согласующий с правом wish.edit_feo
    # (перераспределение позиций заявки по ФЭО) должен мочь создать
    # НЕДОСТАЮЩУЮ плановую позицию, даже без вкладки feo_categories. Остальные
    # эндпоинты роутера (bulk/PUT/map) и весь feo_categories.py НАМЕРЕННО не
    # тронуты — перемещение и импорт дерева ФЭО остаются доступны только через
    # вкладку. DELETE (см. _check_planned_item_write_access, добавлено
    # 2026-08-19 расширение доступа к удалению) теперь использует ту же матрицу.
    await _check_planned_item_write_access(current_user, db, cat)

    # Корректировка утверждённой субсидии через проверку (02.10.2026): прямое
    # создание плановой позиции из дерева ФЭО субсидии — это правка субсидии,
    # обязана пройти assert_direct_edit. Создание ИЗ заявки/закупки (контекст
    # wish_id/purchase_id выше) — другой путь: заявка/закупка добирает себе
    # недостающий план, это не правка справочника ФЭО субсидии, гейт не
    # вызывается — но контекст обязан реально относиться к той же субсидии.
    if wish_id is not None or purchase_id is not None:
        await feo_item_write.validate_wish_or_purchase_context(db, cat.subsidy_id, wish_id, purchase_id)
    else:
        from app.services.subsidy_revision_guard import assert_direct_edit
        await assert_direct_edit(db, current_user, cat.subsidy_id)

    # Тело создания (дедуп по имени, происхождение, синхронизация каталога,
    # журнал ФЭО, авто-версия плана) — app.services.feo_item_write (Правило №6,
    # применение корректировки позже вызовет ту же функцию).
    item = await feo_item_write.create_planned_item(db, current_user, cat, data)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/bulk", response_model=FeoPlannedItemBulkCreateResult)
async def create_planned_items_bulk(
    body: FeoPlannedItemBulkCreate,
    # См. wish_id/purchase_id у POST / — та же роль и та же причина плоского
    # default=None без Query(...) (прямые вызовы в тестах, минуя FastAPI DI).
    wish_id: Optional[int] = None,
    purchase_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Создать несколько плановых позиций (Ур.5 FeoPlannedItem) ОДНОЙ атомарной
    транзакцией — вместо цикла отдельных POST /feo-planned-items/ с фронта.

    Жалоба владельца (сессия 2026-08-17): «Создать в плане закупок» на заявке с
    7 разными товарами создавала ровно ОДНУ плановую позицию (имя первого товара)
    на всю НМЦД заявки — остальные 6 товаров теряли план целиком. Причина была на
    фронте (headFeoPlannedPrefill/wishFeoPlannedPrefill брали первую позицию + всю
    сумму, диалог создавал 1 запись), но N отдельных POST из цикла на фронте —
    не атомарно и не в одной транзакции, как требует задача; этот эндпоинт решает
    обе части: один HTTP-запрос, одна транзакция, при ошибке — ничего не создаётся.

    Дедуп — тот же принцип, что и в одиночном create_planned_item (см. его
    докстринг): ТОЛЬКО точное совпадение (категория, нормализованное имя),
    никакого fuzzy. Если позиция с таким именем уже активна в категории —
    возвращается она, новая не создаётся (защита от повторного клика/двойного
    сабмита). Дедуп учитывает и позиции, создаваемые в ЭТОМ ЖЕ вызове (две строки
    запроса с одинаковым именем в одной категории не плодят два дубля).

    auto_created НЕ проставляется (остаётся False колонки по умолчанию) — все
    позиции этого эндпоинта заведены человеком через диалог выбора способа
    создания, а не автоматически из закупки без участия человека.

    wish_id/purchase_id (02.10.2026, «Корректировка утверждённой субсидии через
    проверку») — тот же контекст и то же освобождение от assert_direct_edit,
    что и у POST / (см. его докстринг), проверяется по КАЖДОЙ затронутой
    субсидии затрагиваемых категорий.
    """
    # Тело (дедуп/валидация/запись/журнал/авто-версия) — app.services.feo_item_write
    # (Правило №6). Здесь — только гейт: лёгкий запрос subsidy_id категорий ДО
    # полного тела сервиса (который сам ещё раз грузит категории целиком —
    # приемлемая цена одного лишнего узкого SELECT ради единой точки проверки).
    subsidy_ids = set((await db.execute(
        select(FeoCategory.subsidy_id).where(
            FeoCategory.id.in_({it.feo_category_id for it in body.items})
        )
    )).scalars().all())
    subsidy_ids.discard(None)
    if wish_id is not None or purchase_id is not None:
        for sid in subsidy_ids:
            await feo_item_write.validate_wish_or_purchase_context(db, sid, wish_id, purchase_id)
    else:
        from app.services.subsidy_revision_guard import assert_direct_edit
        for sid in subsidy_ids:
            await assert_direct_edit(db, current_user, sid)

    created = await feo_item_write.create_planned_items_bulk(db, current_user, body)
    await db.commit()
    for it in created:
        await db.refresh(it)

    return FeoPlannedItemBulkCreateResult(items=created)


@router.put("/{item_id}", response_model=FeoPlannedItemOut)
async def update_planned_item(
    item_id: int,
    data: FeoPlannedItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")

    # Корректировка утверждённой субсидии через проверку (02.10.2026): правка
    # плановой позиции — ВСЕГДА правка субсидии (в отличие от create/bulk/delete,
    # у PUT нет «контекста заявки/закупки» — это единственная точка изменения
    # уже существующей строки дерева ФЭО), гейт вызывается безусловно.
    _gate_subsidy_id = (await db.execute(
        select(FeoCategory.subsidy_id).where(FeoCategory.id == item.feo_category_id)
    )).scalar_one_or_none()
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, _gate_subsidy_id)

    # Тело правки (дифф полей, перенос категории, синхронизация каталога,
    # журнал ФЭО, авто-версия плана) — app.services.feo_item_write (Правило №6).
    item = await feo_item_write.update_planned_item(db, current_user, item, data)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_planned_item(
    item_id: int,
    purchase_id: Optional[int] = Query(
        None,
        description=(
            "Закупка, из которой удаляют плановую позицию (перечень плановых позиций "
            "в шапке карточки закупки — CreateOrderView.vue). Её ссылки и ссылки "
            "заявки, породившей эту закупку, считаются «своими» и просто снимаются."
        ),
    ),
    wish_id: Optional[int] = Query(
        None,
        description=(
            "Заявка, из формы которой удаляют плановую позицию (корзинка в "
            "FeoPlannedItemsSelect внутри WishesView.vue — плановая позиция создана и "
            "тут же привязана прямо при заполнении заявки, ещё до конвертации в "
            "закупку). Ссылки wish_items ЭТОЙ заявки считаются «своими» и снимаются "
            "молча — так же, как purchase_id снимает ссылки своей закупки."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Удаление плановой позиции.

    БАГ ЦЕЛОСТНОСТИ (владелец, 2026-08-17): здесь раньше не снимались ссылки
    у purchase_items/wish_items.feo_planned_item_id перед удалением строки —
    а в БД для этих колонок никогда не было FK-констрейнта (см. миграцию
    x9y8z7w6v5u4_feo_planned_item_fk_integrity), так что удаление молча
    оставляло висячие ссылки: позиция закупки пропадала с экрана целиком
    (не подставляется — плановой строки уже нет; не попадает в «Не привязаны
    к плану» — там фильтр по ПУСТОЙ привязке), а её сумма продолжала входить
    в «в закупках» категории — необъяснимое превышение плана.

    Миграция x9y8z7w6v5u4 добавила настоящий FK ON DELETE SET NULL — этого
    достаточно, чтобы битых ссылок больше не появлялось. Явный UPDATE ниже —
    вторая, независимая от наличия констрейнта в БД, страховка (в той же
    транзакции, до удаления строки): поведение не должно зависеть от того,
    жива ли FK в конкретном окружении.

    ЗАЩИТА ОТ ПОРЧИ ЧУЖИХ ЗАКУПОК (владелец, 2026-08-19): «Меню с кучей
    переключателей... я выбираю одну и привязываюсь сразу ко всем — это
    невозможно... надо просто оставить перечень плановых, для возможности их
    удаления и высвобождения денег» — CreateOrderView.vue теперь показывает
    read-only перечень плановых позиций категории с кнопкой удаления вместо
    привязки. Одна и та же плановая позиция может быть привязана к позициям
    НЕСКОЛЬКИХ разных закупок/заявок одновременно — удаление её из ОДНОЙ
    карточки закупки не должно молча отвязывать и обнулять план у чужих.
    purchase_id (закупка, из которой жмут «удалить») + заявка, породившая
    именно эту закупку (Purchase.wish_id), — единственные держатели, которых
    можно снять молча. Любой ДРУГОЙ держатель (другая закупка/заявка) блокирует
    удаление 409-м с перечнем — реестровый номер закупки и/или номер заявки,
    максимум 3, дальше «и ещё N»; в БД при этом ничего не меняется.
    Доступ — расширен под ту же матрицу, что и POST / (см.
    _check_planned_item_write_access) вместо жёсткой привязки к вкладке
    feo_categories: владелец явно попросил, чтобы удаление работало из
    карточки закупки/заявки, а не только из справочника ФЭО.

    ДЕФЕКТ 2 (владелец, 2026-08-20): «При создании заявки случайно создали
    плановую позицию неправильно, надо удалить, для этого не должно быть
    необходимости лезть куда-то ещё» — параметр wish_id (см. выше) добавлен по
    точной аналогии с purchase_id: заявка, из формы которой жмут «удалить»,
    и её собственные wish_items — «свой» держатель, снимается молча. Раньше
    own_wish_id вычислялся ТОЛЬКО из purchase_id → Purchase.wish_id, поэтому
    при удалении прямо из формы заявки (закупки ещё нет, purchase_id
    неоткуда взять) ссылка самой этой заявки всегда попадала в
    foreign_wishes и отдавала 409 — удалить только что созданную свою же
    плановую позицию было невозможно.
    """
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")
    _feo_cat_id = item.feo_category_id
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == _feo_cat_id)
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")
    await _check_planned_item_write_access(current_user, db, cat)

    # Корректировка утверждённой субсидии через проверку (02.10.2026): удаление
    # БЕЗ контекста заявки/закупки — прямая правка субсидии, гейт обязателен.
    # purchase_id/wish_id — «свои» держатели (см. докстринг эндпоинта выше) —
    # уже сами по себе доказывают, что удаление идёт из формы заявки/закупки,
    # а не из справочника ФЭО субсидии напрямую, поэтому гейт не дублируется.
    if purchase_id is None and wish_id is None:
        from app.services.subsidy_revision_guard import assert_direct_edit
        await assert_direct_edit(db, current_user, cat.subsidy_id)

    # Тело удаления (проверка чужих держателей, снятие ссылок, журнал ФЭО,
    # авто-версия плана) — app.services.feo_item_write (Правило №6).
    await feo_item_write.delete_planned_item(
        db, current_user, item, cat, purchase_id=purchase_id, wish_id=wish_id,
    )
    await db.commit()
    return {"ok": True}


# Re-export для обратной совместимости внешних потребителей (Правило №5, резка
# feo_planned_items.py, сессия 2026-09-08): map_purchase_item_to_planned и
# _WISH_STATUS_LABELS физически переехали в роутеры-соседи ниже, но
# backend/tests/test_planned_item_link_rules.py зовёт первую через
# `from app.routers import feo_planned_items as fpi_router` +
# fpi_router.map_purchase_item_to_planned(...), а app/routers/wish_convert.py
# импортирует _WISH_STATUS_LABELS напрямую из этого модуля — оба места НЕ
# переписываем (см. правила задачи), символы остаются доступны здесь же.
from app.routers.feo_planned_items_matching import map_purchase_item_to_planned  # noqa: E402,F401
from app.routers.feo_planned_items_reports import _WISH_STATUS_LABELS  # noqa: E402,F401
