from decimal import Decimal, InvalidOperation
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


def _fmt_money(v) -> str:
    """Человекочитаемая сумма для текста 409-ответа дедупа (см. create_planned_item).
    Округление до целого — как fmt() на фронте (FeoPlannedItemsSelect.vue), это
    только для сообщения человеку, структурные суммы уходят в detail отдельными
    полями с полной точностью (str(Decimal), без округления)."""
    if v is None:
        return "—"
    try:
        n = int(Decimal(str(v)).quantize(Decimal("1")))
    except (InvalidOperation, TypeError):
        return "—"
    return f"{n:,}".replace(",", " ") + " ₽"


def _fmt_qty(qty, unit) -> str:
    if qty is None:
        return "—"
    try:
        q = Decimal(str(qty))
        q_str = str(q.quantize(Decimal("1")) if q == q.to_integral_value() else q)
    except (InvalidOperation, TypeError):
        q_str = str(qty)
    return f"{q_str} {unit}".strip() if unit else q_str


def normalize_item_type(v: Optional[str]) -> Optional[str]:
    """Признак «Товар/Услуга/Работа» плановой позиции (блок 1, план
    zany-fluttering-mountain.md) — приводит свободный ввод (в т.ч. импорт ФЭО)
    к одному из трёх нижнерегистрных значений, как в purchase_items.item_type/
    wish_items.item_type. Пусто/непонятное значение → None (поле необязательное).
    Экспортируется — используется импортом ФЭО (тот же нормализатор, не дублируем).
    """
    if not v:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if s.startswith("тов"):
        return "товар"
    if s.startswith("усл"):
        return "услуга"
    if s.startswith("раб"):
        return "работа"
    return None


def _apply_payment_fields(item: FeoPlannedItem, data: FeoPlannedItemCreate) -> None:
    """
    W1b: Apply payment schedule fields and enforce the amount consistency rule:
      monthly mode → amount = monthly_amount * months_count (if both provided).
      one_time mode → amount taken as-is from data.
    """
    item.payment_mode = data.payment_mode
    item.planned_date = data.planned_date
    item.monthly_start_date = data.monthly_start_date
    item.months_count = data.months_count
    item.monthly_amount = data.monthly_amount

    if data.payment_mode == "monthly":
        if data.monthly_amount is not None and data.months_count is not None:
            item.amount = Decimal(str(data.monthly_amount)) * data.months_count
        # else: keep whatever amount was already set (data.amount or existing value)
    else:
        # one_time: honour the manually supplied amount
        item.amount = data.amount

router = APIRouter(prefix="/api/feo-planned-items", tags=["feo_planned_items"])


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

    # Задача владельца «план ≠ факт» (шаг D, сессия 2026-08-06): защита от повторения
    # К2 (боевые 16 760 000 — две активные плановые позиции с одинаковым именем под
    # одной категорией). Дедуп по (категория, нормализованное имя) — точное совпадение,
    # НИКАКОГО fuzzy (правило проекта, шаг 4 плана zany-fluttering-mountain.md: нечёткое
    # сравнение допустимо только для предложения, которое подтверждает человек; дедуп при
    # создании — строго точное совпадение). Нормализация — общий app.services.text_match
    # .normalize (единственный источник, не дублируем ad-hoc trim+lower — Python-side
    # сравнение вместо SQL lower(trim(...)), т.к. normalize() дополнительно убирает
    # пунктуацию/двойные пробелы, что SQL-выражение не делает — расхождение исказило бы
    # дедуп). wishes.py._auto_assign_planned_items использует свой trim+lower (тот файл
    # не трогаем — параллельная задача другого исполнителя), но эта функция теперь общая.
    _norm_name = _norm_text(data.name or "")
    if _norm_name:
        _candidates = (await db.execute(
            select(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id == data.feo_category_id,
                FeoPlannedItem.is_active == True,
            )
        )).scalars().all()
        existing_item = next((it for it in _candidates if _norm_text(it.name or "") == _norm_name), None)
        # Жалоба владельца (сессия 2026-08-19): раньше здесь молча делали
        # `return existing_item` — введённые пользователем количество/сумма
        # выбрасывались, новая строка тихо привязывалась к чужой позиции без
        # единого сигнала (боевой пример: футболки 14 шт/15 793,40 ₽ против
        # новых 10 шт/11 281 ₽ — разное нанесение, разные позиции). Дедуп
        # остаётся (защита от повторного клика/двойного сабмита и от боевого
        # случая К2 — см. докстринг выше), но теперь это осознанный выбор
        # человека: 409 с данными обеих позиций, allow_duplicate_name=True
        # пропускает дедуп и создаёт вторую позицию с тем же именем.
        if existing_item is not None and not data.allow_duplicate_name:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"В этой категории уже есть плановая позиция с таким названием: "
                        f"«{existing_item.name}» — {_fmt_qty(existing_item.quantity, existing_item.unit)} "
                        f"на {_fmt_money(existing_item.amount)}. Вы вводите: "
                        f"{_fmt_qty(data.quantity, data.unit)} на {_fmt_money(data.amount)}. "
                        f"Привязать к существующей или создать отдельную?"
                    ),
                    "error_code": "planned_item_duplicate_name",
                    "existing_item_id": existing_item.id,
                    "existing_item_name": existing_item.name,
                    "existing_item_quantity": str(existing_item.quantity) if existing_item.quantity is not None else None,
                    "existing_item_unit": existing_item.unit,
                    "existing_item_amount": str(existing_item.amount) if existing_item.amount is not None else None,
                    "new_quantity": str(data.quantity) if data.quantity is not None else None,
                    "new_unit": data.unit,
                    "new_amount": str(data.amount) if data.amount is not None else None,
                },
            )
        # existing_item is not None здесь означает allow_duplicate_name=True —
        # дедуп осознанно пропущен, ниже создаётся вторая позиция с тем же именем.

    # Происхождение (is_feo_breakdown/is_internal_plan) — см. _can_edit_feo_origin:
    # тот, кто заводит позицию без вкладки feo_categories (только через
    # wish.edit_feo/wishes/purchases), не может проставить признак — поля
    # тихо остаются дефолтным False/False колонки, а не 403 на весь запрос.
    _origin_kwargs = {}
    if await _can_edit_feo_origin(current_user, db):
        _origin_kwargs = {
            "is_feo_breakdown": data.is_feo_breakdown,
            "is_internal_plan": data.is_internal_plan,
        }

    item = FeoPlannedItem(
        feo_category_id=data.feo_category_id,
        name=data.name,
        quantity=data.quantity,
        unit=data.unit,
        # Цена за единицу (владелец, 2026-09-02) — см. докстринг
        # FeoPlannedItem.unit_price / assert_tz_not_over_plan. NULL = не задана,
        # amount тогда сам по себе итоговая сумма (не делим на quantity).
        unit_price=data.unit_price,
        notes=data.notes,
        is_active=data.is_active,
        sort_order=data.sort_order,
        item_type=normalize_item_type(data.item_type),
        # auto_created — НЕ принимается на вход (это точечное создание человеком
        # через UI), остаётся дефолтным False колонки.
        **_origin_kwargs,
    )
    _apply_payment_fields(item, data)
    db.add(item)
    _sid = cat.subsidy_id
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await db.flush()
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/bulk", response_model=FeoPlannedItemBulkCreateResult)
async def create_planned_items_bulk(
    body: FeoPlannedItemBulkCreate,
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
    """
    if not body.items:
        raise HTTPException(400, "Список позиций пуст")
    if len(body.items) > 500:
        raise HTTPException(400, "Слишком много позиций за один раз (максимум 500)")

    cat_ids = {it.feo_category_id for it in body.items}
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.id.in_(cat_ids))
    )).scalars().all()
    cat_by_id = {c.id: c for c in cats}
    missing = cat_ids - set(cat_by_id)
    if missing:
        raise HTTPException(404, f"Категория ФЭО не найдена: {', '.join(str(m) for m in sorted(missing))}")

    existing_by_cat: dict[int, list[FeoPlannedItem]] = {}
    if cat_ids:
        existing_rows = (await db.execute(
            select(FeoPlannedItem).where(
                FeoPlannedItem.feo_category_id.in_(cat_ids),
                FeoPlannedItem.is_active == True,
            )
        )).scalars().all()
        for r in existing_rows:
            existing_by_cat.setdefault(r.feo_category_id, []).append(r)

    max_sort_by_cat: dict[int, int] = {}
    for cid, rows in existing_by_cat.items():
        vals = [r.sort_order for r in rows if r.sort_order is not None]
        max_sort_by_cat[cid] = max(vals) if vals else 0

    created: list[FeoPlannedItem] = []
    dedup_seen: dict[tuple[int, str], FeoPlannedItem] = {}
    touched_subsidies: set[int] = set()

    for data in body.items:
        cat = cat_by_id[data.feo_category_id]
        norm_name = _norm_text(data.name or "")
        dedup_key = (data.feo_category_id, norm_name)
        existing_item = None
        if norm_name:
            if dedup_key in dedup_seen:
                existing_item = dedup_seen[dedup_key]
            else:
                existing_item = next(
                    (it for it in existing_by_cat.get(data.feo_category_id, [])
                     if _norm_text(it.name or "") == norm_name),
                    None,
                )
        if existing_item is not None:
            created.append(existing_item)
            dedup_seen[dedup_key] = existing_item
            continue

        sort_order = data.sort_order
        if sort_order is None:
            max_sort_by_cat[data.feo_category_id] = max_sort_by_cat.get(data.feo_category_id, 0) + 1
            sort_order = max_sort_by_cat[data.feo_category_id]

        item = FeoPlannedItem(
            feo_category_id=data.feo_category_id,
            name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            notes=data.notes,
            is_active=data.is_active,
            sort_order=sort_order,
            item_type=normalize_item_type(data.item_type),
            # auto_created — НЕ принимается на вход, см. докстринг эндпоинта.
            # is_feo_breakdown/is_internal_plan — этот эндпоинт целиком за
            # require_tab('feo_categories') (см. декоратор функции), поэтому,
            # в отличие от одиночного create_planned_item, права проверять
            # отдельно не нужно (см. _can_edit_feo_origin).
            is_feo_breakdown=data.is_feo_breakdown,
            is_internal_plan=data.is_internal_plan,
        )
        _apply_payment_fields(item, data)
        db.add(item)
        created.append(item)
        if norm_name:
            dedup_seen[dedup_key] = item
        if cat.subsidy_id is not None:
            touched_subsidies.add(cat.subsidy_id)

    await db.flush()

    if touched_subsidies:
        from app.routers.purchases import _create_plan_graph_version
        for sid in touched_subsidies:
            await _create_plan_graph_version(
                subsidy_id=sid, db=db, user=current_user,
                note="Авто-версия: массовое создание плановых позиций",
            )

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
    _feo_cat_id = item.feo_category_id
    item.name = data.name
    item.quantity = data.quantity
    item.unit = data.unit
    # PUT здесь — ПОЛНАЯ замена, как и у quantity/amount/unit выше (см. докстринг
    # PATCHABLE-паттерна ниже у item_type/is_feo_breakdown) — любой вызывающий код
    # (movePlannedItemToCategory/savePlannedItemSortOrder/saveEditPlannedItem в
    # SubsidiesView.vue) обязан слать unit_price существующей позиции явно, иначе
    # он молча обнулится. Все три места фронта обновлены вместе с этим полем.
    item.unit_price = data.unit_price
    item.notes = data.notes
    item.is_active = data.is_active
    item.sort_order = data.sort_order
    # Тип позиции — единственное поле, которое НЕ обнуляется молчанием клиента.
    # PUT здесь полная замена, а вызовов у него много (перенос в другую категорию,
    # смена порядка, правка из карточки, внешние клиенты) — любой из них, не
    # приславший item_type, стирал бы выбранный человеком тип. Правило проекта:
    # выбранное на предыдущем этапе не меняется само. Явный item_type: null в теле
    # запроса по-прежнему очищает поле — это осознанное действие.
    if "item_type" in data.model_fields_set:
        item.item_type = normalize_item_type(data.item_type)
    # Происхождение (владелец, 2026-09-01) — тот же паттерн, что и у item_type
    # чуть выше: PUT здесь полная замена, у роутера много вызывающих
    # (movePlannedItemToCategory/savePlannedItemSortOrder/clearCategoryManualPlan
    # в SubsidiesView.vue шлют существующие поля позиции, но про НОВЫЕ два поля
    # ничего не знают) — без model_fields_set-guard любой такой вызов молча
    # сбросил бы уже выставленный признак в False. Доступ уже ограничен целиком
    # require_tab('feo_categories') у этого эндпоинта — отдельной проверки, как
    # в create_planned_item (_can_edit_feo_origin), здесь не нужно.
    if "is_feo_breakdown" in data.model_fields_set:
        item.is_feo_breakdown = data.is_feo_breakdown
    if "is_internal_plan" in data.model_fields_set:
        item.is_internal_plan = data.is_internal_plan
    _apply_payment_fields(item, data)

    # БАГ (владелец, 2026-08-13): «нажал на кнопку переноса, выбрал категорию,
    # написало "Позиция перенесена", но на самом деле ничего не перенеслось» —
    # feo_category_id здесь раньше вообще не присваивался, хотя старая категория
    # читалась выше в _feo_cat_id. Ответ 200 рапортовал об успехе вхолостую.
    if data.feo_category_id != _feo_cat_id:
        old_cat = (
            await db.execute(select(FeoCategory).where(FeoCategory.id == _feo_cat_id))
        ).scalar_one_or_none() if _feo_cat_id is not None else None
        new_cat = (
            await db.execute(select(FeoCategory).where(FeoCategory.id == data.feo_category_id))
        ).scalar_one_or_none()
        if not new_cat:
            raise HTTPException(404, "Категория ФЭО назначения не найдена")
        if old_cat is not None and old_cat.subsidy_id != new_cat.subsidy_id:
            raise HTTPException(
                409,
                f"Категория «{old_cat.name}» относится к другой субсидии, чем «{new_cat.name}» — "
                "перенос плановой позиции между субсидиями невозможен.",
            )
        # Перенос — ПЕРЕКЛАДЫВАНИЕ, а не новая трата: сумма позиции не растёт, она
        # просто уезжает в другую категорию той же субсидии. Намеренно НЕ гоняем
        # здесь assert_no_unapproved_excess — то же послабление, что и в
        # purchases.py::patch_purchase_item для смены feo_category_id позиции
        # закупки (см. её докстринг про боевой случай 3710→3691): блокировать
        # нужно только реальный ПРИРОСТ суммы, а не сам факт переноса.
        # Позиции закупок И заявок, уже привязанные к этой плановой позиции,
        # обязаны переехать вместе с ней — иначе план уедет в новую категорию, а
        # расход (purchase_items/wish_items) останется числиться в старой, и
        # план≠факт разъедется ровно там, где его чинили. Общая логика (тоже
        # используется автопереносом вслед за сменой категории у самой позиции
        # заявки/закупки) — см. app/services/plan_autoassign.py::move_planned_item_to_category.
        from app.services.plan_autoassign import move_planned_item_to_category
        await move_planned_item_to_category(db, item, data.feo_category_id)

    _sid = (await db.execute(
        select(FeoCategory.subsidy_id).where(FeoCategory.id == item.feo_category_id)
    )).scalar_one_or_none()
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
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
    _sid = cat.subsidy_id

    own_purchase_id = purchase_id
    # Держатели-«свои»: заявка, чью закупку удаляют (Purchase.wish_id), И/ИЛИ
    # заявка, из формы которой жмут «удалить» напрямую (wish_id параметр) —
    # объединяем в множество, обе ситуации не исключают друг друга.
    own_wish_ids: set[int] = set()
    if purchase_id is not None:
        _wish_from_purchase = (await db.execute(
            select(Purchase.wish_id).where(Purchase.id == purchase_id)
        )).scalar_one_or_none()
        if _wish_from_purchase is not None:
            own_wish_ids.add(_wish_from_purchase)
    if wish_id is not None:
        own_wish_ids.add(wish_id)

    pi_holder_rows = (await db.execute(
        select(Purchase.id, Purchase.registry_number)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .distinct()
    )).all()
    wi_holder_rows = (await db.execute(
        select(Wish.id, Wish.title)
        .join(WishItem, WishItem.wish_id == Wish.id)
        .where(WishItem.feo_planned_item_id == item_id)
        .distinct()
    )).all()

    foreign_purchases = [(pid, reg) for pid, reg in pi_holder_rows if pid != own_purchase_id]
    foreign_wishes = [(wid, title) for wid, title in wi_holder_rows if wid not in own_wish_ids]

    if foreign_purchases or foreign_wishes:
        holders = [f"закупка {reg or ('№' + str(pid))}" for pid, reg in foreign_purchases]
        holders += [f"заявка №{wid}" for wid, _title in foreign_wishes]
        shown = holders[:3]
        more = len(holders) - len(shown)
        holders_text = ", ".join(shown) + (f" и ещё {more}" if more > 0 else "")
        raise HTTPException(
            409,
            f"Плановую позицию «{item.name}» использует не только эта закупка: "
            f"{holders_text}. Сначала снимите привязку там — из этой карточки "
            "удалять нельзя.",
        )

    await db.execute(
        sql_update(PurchaseItem)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .values(feo_planned_item_id=None)
    )
    await db.execute(
        sql_update(WishItem)
        .where(WishItem.feo_planned_item_id == item_id)
        .values(feo_planned_item_id=None)
    )
    await db.delete(item)
    if _sid is not None:
        from app.routers.purchases import _create_plan_graph_version
        await db.flush()
        await _create_plan_graph_version(subsidy_id=_sid, db=db, user=current_user, note="Авто-версия: изменение плановых позиций")
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
