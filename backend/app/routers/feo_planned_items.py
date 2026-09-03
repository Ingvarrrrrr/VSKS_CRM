from decimal import Decimal, InvalidOperation
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update as sql_update, func as sqlfunc, or_ as sqlor
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES
from app.auth.permissions import require_tab, has_org_key, _has_key_in_any_org
from app.database import get_db
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.models.purchase_item import PurchaseItem
from app.models.purchase import Purchase
from app.models.product import Product
from app.models.contract_item import ContractItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.schemas.schemas import (
    FeoPlannedItemCreate, FeoPlannedItemOut, FeoComparisonOut, FeoActualItemOut, FeoStageOut,
    FeoPlannedItemBulkCreate, FeoPlannedItemBulkCreateResult,
)
from app.services.text_match import normalize as _norm_text, tokenize, stem, generic_progressive_match


def _safe_mul(a, b) -> Optional[Decimal]:
    if a is None or b is None:
        return None
    try:
        return Decimal(str(a)) * Decimal(str(b))
    except (InvalidOperation, TypeError):
        return None


def _safe_div(a, b) -> Optional[Decimal]:
    if a is None or b is None:
        return None
    try:
        b_dec = Decimal(str(b))
        if b_dec == 0:
            return None
        return Decimal(str(a)) / b_dec
    except (InvalidOperation, TypeError):
        return None


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


def _build_item_stages(
    pi: PurchaseItem,
    ci: Optional[ContractItem],
    cat: Optional[FeoCategory],
    plan_items_map: dict,
    cat_plan_fallback: Optional[dict] = None,
) -> list[FeoStageOut]:
    """Собирает цепочку стадий feo → plan → purchase → contract → accepted для одной
    фактической позиции (см. /comparison). Стадия попадает в массив, только если у
    неё есть хоть какие-то данные. Порядок — строго фиксированный.

    cat_plan_fallback — фолбэк для стадии «План», когда план переехал в записи
    внутри категории (FeoPlannedItem) и у категории cat.planned_quantity/
    planned_amount оба NULL: dict {"quantity", "unit_price", "amount"}, посчитанный
    ОДНИМ запросом на весь /comparison-эндпоинт (см. вызывающий код), а не в цикле
    по позициям — категория здесь всегда одна на запрос.
    """
    stages: list[FeoStageOut] = []

    # 1. ФЭО — из категории (общая для всех позиций этого запроса)
    if cat is not None and (cat.feo_quantity is not None or cat.feo_amount is not None or cat.budget is not None):
        feo_total = _safe_mul(cat.feo_quantity, cat.feo_amount)
        if feo_total is None:
            feo_total = cat.budget
        stages.append(FeoStageOut(
            key="feo", label="ФЭО",
            name=cat.name,
            quantity=cat.feo_quantity,
            unit=cat.feo_unit,
            unit_price=cat.feo_amount,
            total=feo_total,
        ))

    # 2. План — приоритет FeoPlannedItem (если позиция сопоставлена), иначе конечный
    # элемент дерева ФЭО (cat.planned_quantity/planned_amount — planned_amount ЦЕНА ЗА ЕД.)
    fpi = plan_items_map.get(pi.feo_planned_item_id) if pi.feo_planned_item_id else None
    if fpi is not None:
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=fpi.name,
            quantity=fpi.quantity,
            unit=fpi.unit,
            # Владелец (2026-09-02, см. FeoPlannedItem.unit_price): цена за единицу —
            # самостоятельное поле, НЕ amount/quantity. Раньше здесь тем же способом,
            # что и в /plan-positions, фабриковалась цифра из деления — тот же баг,
            # только в другой выдаче (стадия «План» карточки сравнения).
            unit_price=fpi.unit_price,
            total=fpi.amount,
        ))
    elif cat is not None and (cat.planned_quantity is not None or cat.planned_amount is not None):
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=cat.name,
            quantity=cat.planned_quantity,
            unit=cat.unit,
            unit_price=cat.planned_amount,
            total=_safe_mul(cat.planned_quantity, cat.planned_amount),
        ))
    elif cat is not None and cat_plan_fallback is not None:
        # План переехал в записи внутри категории — у мигрированных категорий-листьев
        # cat.planned_quantity/planned_amount оба пусты (NULL), план лежит в активных
        # FeoPlannedItem. Без этого фолбэка стадия «План» не добавляется вовсе, и в
        # цепочке ФЭО→План→Закупка→Договор→Приёмка выпадает целое звено, хотя план есть.
        stages.append(FeoStageOut(
            key="plan", label="План",
            name=cat.name,
            quantity=cat_plan_fallback.get("quantity"),
            unit=cat.unit,
            unit_price=cat_plan_fallback.get("unit_price"),
            total=cat_plan_fallback.get("amount"),
        ))

    # 3. Что выставляли на закупку — всегда есть (purchase_item сюда дошёл, значит есть item_name)
    stages.append(FeoStageOut(
        key="purchase", label="Что выставляли на закупку",
        name=pi.item_name,
        quantity=pi.quantity,
        unit=pi.unit,
        unit_price=pi.unit_price,
        total=pi.total_price,
    ))

    # 4. Номенклатура подрядчика — только если есть договорная строка
    if ci is not None:
        stages.append(FeoStageOut(
            key="contract", label="Номенклатура подрядчика",
            name=ci.name,
            quantity=ci.quantity,
            unit=ci.unit,
            unit_price=ci.unit_price,
            total=ci.total,
        ))

    # 5. Приняли — только если хоть что-то заполнено
    if (
        pi.accepted_name is not None or pi.accepted_quantity is not None or pi.accepted_unit is not None
        or pi.final_unit_price is not None or pi.final_total is not None
    ):
        stages.append(FeoStageOut(
            key="accepted", label="Приняли",
            name=pi.accepted_name,
            quantity=pi.accepted_quantity,
            unit=pi.accepted_unit,
            unit_price=pi.final_unit_price,
            total=pi.final_total,
        ))

    return stages


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


@router.get("/product-hint")
async def get_product_hint(
    product_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Подсказка для диалога «Добавить плановую позицию» (SubsidiesView.vue) при
    выборе товара из каталога — единица измерения + цена/её происхождение,
    ОДНИМ запросом.

    Переименован из product-unit-hint (владелец, 2026-09-01): изначально отдавал
    только unit, читая из истории закупок (см. ниже) — цену/дату/источник фронт
    брал из кандидата POST /products/match (useItemMatching.ts::MatchCandidate).
    НО те поля (price_updated_at/price_source/price_source_ref) в /products/match
    добавила ПАРАЛЛЕЛЬНАЯ сессия и ещё НЕ закоммитила (backend/app/routers/products.py
    — файл специально не трогаем, см. правила задачи) — на проде, где working tree
    чистый, кандидат отдаёт только price/photo_url, и подпись о цене всегда молчала
    бы («дата актуализации не указана»). Колонки price/price_updated_at/price_source/
    price_source_ref НА САМОЙ МОДЕЛИ Product УЖЕ закоммичены (app/models/product.py:
    25,40-42) — читаем их прямо оттуда, без зависимости от чужого незакоммиченного
    кода. Фронт использует ЭТОТ эндпоинт как основной источник цены/даты/источника,
    candidate.price — только запасной вариант на случай сетевой ошибки.

    unit (владелец, 2026-09-01): теперь у Product ЕСТЬ своё поле unit —
    приоритет ему (заполняется бэкфиллом/импортом/карточкой товара, см.
    app/services/product_unit.py). Если оно пусто — прежний фолбэк на
    последнюю единицу измерения, с которой товар фигурировал в позиции
    закупки (PurchaseItem.unit по product_id, самая свежая по id); null, если
    ни разу не покупался с явно указанной единицей — фронт тогда оставляет
    поле пустым."""
    # Колонки price_updated_at/price_source/price_source_ref появляются вместе с
    # отдельной работой по свежести цен и на момент этого кода могут ещё не
    # существовать ни в модели, ни в БД (прод отдавал 500: «type object 'Product'
    # has no attribute 'price_updated_at'»). Поэтому выбираем их ТОЛЬКО если они
    # реально объявлены в модели: цена и единица работают всегда, а дата/источник
    # появятся сами, как только колонки приедут — без правок здесь.
    _optional = [c for c in ("price_updated_at", "price_source", "price_source_ref")
                 if hasattr(Product, c)]
    _cols = [Product.price, Product.contract_price, Product.unit] + [getattr(Product, c) for c in _optional]
    product = (await db.execute(select(*_cols).where(Product.id == product_id))).first()

    # Приоритет (владелец, 2026-09-01): собственная Product.unit, если заполнена;
    # иначе — прежний фолбэк на самую свежую единицу из истории закупок.
    unit_val = (product.unit or None) if product is not None else None
    if not unit_val:
        unit_val = (await db.execute(
            select(PurchaseItem.unit)
            .where(
                PurchaseItem.product_id == product_id,
                PurchaseItem.unit.isnot(None),
                PurchaseItem.unit != "",
            )
            .order_by(PurchaseItem.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    if product is None:
        return {"unit": unit_val, "price": None, "price_updated_at": None, "price_source": None, "price_source_ref": None}

    best_price = product.contract_price if product.contract_price is not None else product.price
    _updated = getattr(product, "price_updated_at", None)
    return {
        "unit": unit_val,
        "price": float(best_price) if best_price is not None else None,
        "price_updated_at": _updated.isoformat() if _updated else None,
        "price_source": getattr(product, "price_source", None),
        "price_source_ref": getattr(product, "price_source_ref", None),
    }


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


@router.post("/map")
async def map_purchase_item_to_planned(
    purchase_item_id: int,
    planned_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Сопоставить purchase_item с плановой позицией. planned_item_id=null — снять сопоставление."""
    pi = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.id == purchase_item_id)
    )).scalar_one_or_none()
    if not pi:
        raise HTTPException(404, "Позиция закупки не найдена")

    if planned_item_id is not None:
        planned = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == planned_item_id)
        )).scalar_one_or_none()
        if not planned:
            raise HTTPException(404, "Плановая позиция не найдена")

        purchase = (await db.execute(
            select(Purchase).where(Purchase.id == pi.purchase_id)
        )).scalar_one_or_none()
        effective_cat_id = pi.feo_category_id if pi.feo_category_id is not None else (
            purchase.feo_category_id if purchase else None
        )

        # Этап 3 (владелец, 2026-09-02): до 2026-08-18 несовпадение категорий тут
        # отклонялось с 409; с 2026-08-18 по 2026-09-02 этот путь молча ПЕРЕНОСИЛ
        # позицию закупки в категорию плановой позиции — сумма не исчезала, но
        # ровно этим переносом создавалось расхождение «категория позиции ≠
        # категория шапки» (при feo_per_item=False), которое PATCH
        # /purchases/{id}/items/{item_id} для явного выбора плановой позиции как
        # раз запрещает — правило разъезжалось по двум путям. Приведено к тому
        # же правилу через общий хелпер (см. app/services/plan_autoassign.py):
        # обычному пользователю — отказ с объяснением, суперадмину — разрешение
        # + уведомление согласовавших/ответственного; категория позиции закупки
        # больше НЕ переносится молча — привязка живёт поверх существующей
        # категории, как и в PATCH.
        from app.services.plan_autoassign import check_planned_item_category_link
        await check_planned_item_category_link(
            db,
            purchase=purchase,
            item=pi,
            item_category_id=effective_cat_id,
            planned_category_id=planned.feo_category_id,
            planned_item_name=planned.name,
            current_user=current_user,
        )

        # НЕ вызываем здесь assert_no_unapproved_excess/другие гейты превышения:
        # это действие сопоставления факта с планом, а не новая трата денег.
    else:
        planned = None

    pi.feo_planned_item_id = planned_item_id

    # Зеркалим привязку в связанную позицию заявки — иначе заявка и закупка
    # расходятся (ровно баг с прода: wish_items.id=2583 остался с
    # feo_planned_item_id=123/категория 3688, пока purchase_items.id=2897
    # уехал на несуществующую плановую позицию 809/категорию 3710).
    if pi.wish_item_id is not None:
        wi = (await db.execute(
            select(WishItem).where(WishItem.id == pi.wish_item_id)
        )).scalar_one_or_none()
        if wi:
            wi.feo_planned_item_id = planned_item_id
            # Категорию позиции заявки больше не переносим следом за плановой
            # (см. комментарий выше про этап 3) — она следует тем же правилам,
            # что и категория позиции закупки: своя категория не переписывается
            # молча привязкой к плану.

    await db.commit()
    return {
        "ok": True,
        "purchase_item_id": purchase_item_id,
        "planned_item_id": planned_item_id,
        # Оставлено для обратной совместимости фронта (SubsidiesView.vue читает
        # это поле) — молчаливый перенос категории убран, поле теперь всегда null.
        "moved_to_category_id": None,
    }


# ---------------------------------------------------------------------------
# Похожая плановая позиция с подтверждением (Шаг 4 плана
# zany-fluttering-mountain.md): при заведении заявки, если в субсидии уже есть
# плановые позиции, предлагать похожие по имени и давать подтвердить/отвергнуть —
# ровно как сопоставление позиции с товаром каталога (products.py /match,
# InlineProductMatch.vue + useItemMatching.ts). Движок — общий
# app.services.text_match (вынесен из app.services.product_matcher, тот же
# алгоритм нормализации+токенов+стемминга+прогрессивного сужения).
# ---------------------------------------------------------------------------

async def _load_plan_catalog(db: AsyncSession, subsidy_id: int) -> list[dict]:
    """Каталог кандидатов для матчинга — тот же состав, что и в
    GET /feo-categories/plan-positions (единый источник «плановых позиций»,
    см. её докстринг): конечные категории ФЭО (лист дерева) с заполненным
    planned_quantity×planned_amount > 0 (kind='plan_position'|'feo_article'),
    плюс активные FeoPlannedItem этих листьев (kind='planned_item') — «может
    быть запланирована в ФЭО, а может только планово» (формулировка владельца).

    Не вызывает сам эндпоинт /plan-positions (тот считает ещё consumption/tree —
    не нужно для матчинга по имени), а строит облегчённую версию тех же строк:
    id/name/path/category_id/ancestor_ids/kind. path/ancestor_ids — те же
    хелперы app.services.feo_plan.build_category_path/build_ancestor_ids
    (read-only импорт, не дублируем).
    """
    from app.services.feo_plan import build_category_path, build_ancestor_ids

    all_cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not all_cats:
        return []

    cat_by_id = {c.id: c for c in all_cats}
    children_count: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            children_count[c.parent_id] = children_count.get(c.parent_id, 0) + 1
    leaves = [c for c in all_cats if children_count.get(c.id, 0) == 0]

    catalog: list[dict] = []
    for c in leaves:
        qty = float(c.planned_quantity) if c.planned_quantity is not None else 0.0
        unit_price = float(c.planned_amount) if c.planned_amount is not None else 0.0
        if qty * unit_price <= 0:
            continue
        kind = "plan_position" if (c.budget is None and c.feo_amount is None) else "feo_article"
        catalog.append({
            "id": c.id,
            "name": c.name or "",
            "path": build_category_path(c, cat_by_id),
            "category_id": c.id,
            "ancestor_ids": build_ancestor_ids(c, cat_by_id),
            "kind": kind,
        })

    if leaves:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem)
            .where(FeoPlannedItem.feo_category_id.in_([c.id for c in leaves]))
            .where(FeoPlannedItem.is_active == True)
        )).scalars().all()
        for it in fpi_rows:
            cat = cat_by_id.get(it.feo_category_id)
            catalog.append({
                "id": it.id,
                "name": it.name or "",
                "path": build_category_path(cat, cat_by_id) if cat else "",
                "category_id": it.feo_category_id,
                "ancestor_ids": build_ancestor_ids(cat, cat_by_id) if cat else [],
                "kind": "planned_item",
            })

    return catalog


class _FeoMatchCandidate(BaseModel):
    kind: str            # 'plan_position' | 'feo_article' | 'planned_item'
    id: int               # id FeoCategory (plan_position/feo_article) или FeoPlannedItem (planned_item)
    key: str               # `${kind}:${id}` — тот же составной ключ, что и в /plan-positions (фронт)
    name: str
    path: str
    category_id: int
    score: float
    # Требование /feo-planned-items/map (совпадение категорий обязательно) — кандидаты
    # из ЧУЖОЙ (относительно feo_category_id запроса) категории/ветки помечаются явно,
    # а не подмешиваются молча (см. докстринг match_planned_items).
    same_category: bool


class _FeoMatchResultItem(BaseModel):
    query: str
    status: str  # 'auto' | 'suggest' | 'create' — см. text_match.generic_progressive_match
    candidates: List[_FeoMatchCandidate]


class _FeoMatchRequest(BaseModel):
    queries: List[str]
    subsidy_id: int
    feo_category_id: Optional[int] = None
    limit: int = 5


class _FeoMatchResponse(BaseModel):
    results: List[_FeoMatchResultItem]


@router.post("/match", response_model=_FeoMatchResponse)
async def match_planned_items(
    body: _FeoMatchRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Score a list of wish-item name queries against the subsidy's plan positions
    (FeoCategory leaves with a plan + FeoPlannedItem) using the same token-based
    fuzzy matching as /api/products/match.

    Владелец: «когда заявки заведены, и если в субсидии уже есть плановая позиция,
    предлагать плановые позиции, похожие по имени... человек может подтвердить, что
    позиция выбрана правильно, а может отвергнуть и выбрать свою». Это ТОЛЬКО источник
    предложений — привязка (feo_planned_item_id/feo_category_id заявки) остаётся,
    как и раньше, через обычное сохранение заявки; см. POST /confirm-wish-plan-match
    для фиксации флага «подтверждено человеком».

    Кандидаты из ЧУЖОЙ (по отношению к feo_category_id запроса — включая её ветку
    предков) категории НЕ отфильтровываются молча — они присутствуют в том же списке
    candidates с same_category=false, фронт обязан показать их отдельной группой с
    пометкой (правило: /feo-planned-items/map требует совпадения категорий для
    фактической привязки purchase_item, так что «чужой» кандидат — это в лучшем
    случае наведение на существующую плановую позицию другой категории, а не то,
    что можно тихо подставить).
    """
    catalog = await _load_plan_catalog(db, body.subsidy_id)
    if not catalog:
        return _FeoMatchResponse(results=[
            _FeoMatchResultItem(query=q, status='create', candidates=[]) for q in body.queries
        ])

    indexed = [
        (entry, {stem(t) for t in tokenize(entry["name"])})
        for entry in catalog
    ]
    target_cat = body.feo_category_id
    top_k = max(1, min(body.limit, 10))

    results: list[_FeoMatchResultItem] = []
    for q in body.queries:
        if not q or not q.strip():
            results.append(_FeoMatchResultItem(query=q, status='create', candidates=[]))
            continue
        status, scored = generic_progressive_match(q, indexed)
        candidates: list[_FeoMatchCandidate] = []
        for entry, sc in scored[:top_k]:
            same_cat = True
            if target_cat is not None:
                same_cat = entry["category_id"] == target_cat or target_cat in (entry["ancestor_ids"] or [])
            candidates.append(_FeoMatchCandidate(
                kind=entry["kind"],
                id=entry["id"],
                key=f"{entry['kind']}:{entry['id']}",
                name=entry["name"],
                path=entry["path"],
                category_id=entry["category_id"],
                score=sc,
                same_category=same_cat,
            ))
        results.append(_FeoMatchResultItem(query=q, status=status, candidates=candidates))

    return _FeoMatchResponse(results=results)


class _ConfirmWishPlanMatchBody(BaseModel):
    wish_id: int
    kind: str            # 'plan_position' | 'feo_article' | 'planned_item'
    target_id: int


@router.post("/confirm-wish-plan-match")
async def confirm_wish_plan_match(
    body: _ConfirmWishPlanMatchBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Фиксирует флаг «плановую позицию подтвердил человек» (wish_items
    .feo_planned_item_match_confirmed, по образцу purchase_items.match_confirmed)
    после того, как заявка уже сохранена обычным путём (POST/PUT /wishes/ —
    ТОТ роутер не трогаем, см. план zany-fluttering-mountain.md шаг 4).

    feo_planned_item_id/feo_category_id сама заявка получает через обычное
    сохранение (WishesView.vue уже шлёт их в payload — см. wishFeoPlanSelection);
    этот эндпоинт — ТОЛЬКО про флаг подтверждения, прямой UPDATE в обход большого
    create_wish/update_wish (мирроит паттерн /feo-planned-items/map для purchase_item).

    kind='planned_item': подтверждаем ТОЛЬКО позиции заявки, у которых
    feo_planned_item_id уже равен target_id (защита от простановки флага не на ту
    строку, если что-то разошлось между сохранением и этим вызовом).
    kind='plan_position'|'feo_article': категория хранится на уровне самой заявки
    (wish.feo_category_id), а не на каждой позиции — подтверждаем все позиции заявки
    без per-item фильтра (per-item ФЭО в это состояние вообще не должен попадать,
    см. WishesView.vue — кнопка доступна только вне режима «разные ФЭО»).

    _auto_assign_planned_items (wishes.py, другой исполнитель) уже НЕ трогает позиции
    с непустым feo_planned_item_id независимо от этого флага — сам факт подтверждения
    человеком физически защищён до вызова этого эндпоинта; флаг — только видимый
    признак «откуда взялась привязка» (для UI/аудита), не гейт бизнес-логики.
    """
    wish = (await db.execute(select(Wish).where(Wish.id == body.wish_id))).scalar_one_or_none()
    if not wish:
        raise HTTPException(404, "Заявка не найдена")

    if body.kind == "planned_item":
        stmt = (
            sql_update(WishItem)
            .where(WishItem.wish_id == body.wish_id, WishItem.feo_planned_item_id == body.target_id)
            .values(feo_planned_item_match_confirmed=True)
        )
    else:
        stmt = (
            sql_update(WishItem)
            .where(WishItem.wish_id == body.wish_id)
            .values(feo_planned_item_match_confirmed=True)
        )
    result = await db.execute(stmt)
    await db.commit()
    return {"ok": True, "wish_id": body.wish_id, "updated": result.rowcount}


@router.get("/comparison", response_model=FeoComparisonOut)
async def get_comparison(
    feo_category_id: int = Query(...),
    subsidy_id: Optional[int] = Query(None),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Возвращает плановые позиции и фактические (из закупок) для сравнения.

    Требование владельца (2026-08-05): «Фактическое количество/цена/сумма должны начать
    отображаться после того, как закупка переведена в статус "Заказано", и если потом сменить
    значения на то, что фактически поставлено, после того как будут загружены данные из
    закрывающих документов». Реализовано полем fact_amount/fact_confirmed на каждой позиции —
    см. правила ниже. До «Заказано» (plan_schedule/work_in_progress/contracted) это ещё ПЛАН,
    а не факт, поэтому fact_amount=None.

    exclude_purchase_id/exclude_wish_id (план crystalline-soaring-heron.md, п.1): та же
    исключающая логика, что и в /feo-categories/plan-positions и /feo-planned-items/residuals
    (см. app.services.feo_plan.apply_wish_item_exclusion) — редактируемая сейчас закупка
    или заявка, чья закупка уже отражена в actual, не должна выглядеть задвоенной суммой,
    если вызывающий экран сам добавляет её позиции поверх (форма сконвертированной заявки).
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.services.feo_plan import purchase_item_fact_amount, FACT_CONFIRMED_STATUSES, apply_wish_item_exclusion

    # Плановые позиции — только активные (согласовано с /residuals, is_active=False скрыты).
    # Порядок — sort_order, потом id: владелец просил менять плановые позиции местами
    # внутри категории, и стрелки в панели субсидии пишут именно sort_order. Раньше здесь
    # стояло order_by(id), и панель (она читает ИМЕННО этот эндпоинт) порядок игнорировала:
    # перестановка сохранялась в БД, но на экране ничего не менялось. В соседнем
    # GET /feo-planned-items/ сортировка уже была правильной — расхождение и было багом.
    planned_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id == feo_category_id)
        .where(FeoPlannedItem.is_active == True)
        .order_by(FeoPlannedItem.sort_order.nulls_last(), FeoPlannedItem.id)
    )).scalars().all()

    # Фактические: purchase_items через COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id) —
    # без coalesce ломается режим «своя категория ФЭО для каждого товара» (Purchase.feo_per_item).
    effective_cat_id = sqlfunc.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
    stmt = (
        select(
            PurchaseItem,
            Purchase,
            ContractItem,
            PurchaseItem.product_id.label("_product_id"),
            Product.photo_data.isnot(None).label("_product_has_photo"),
            Product.photo_url.label("_photo_url"),
            Product.photo_link.label("_photo_link"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(ContractItem, ContractItem.source_item_id == PurchaseItem.id)
        .outerjoin(Product, PurchaseItem.product_id == Product.id)
        .where(effective_cat_id == feo_category_id)
        # Желания — ещё не подтверждённые хотелки; cancelled/split — вне жизненного цикла закупки.
        # Явное перечисление вместо `!= "wishes"`, чтобы cancelled/split не попадали в план/факт.
        .where(Purchase.status.in_(PLANNED_STATUSES))
        # Выравниваем с app.services.feo_plan.py — остановленные закупки не считаются
        # (решение владельца 2026-08-13).
        .where(Purchase.stopped_at.is_(None))
    )
    if subsidy_id is not None:
        stmt = stmt.where(Purchase.subsidy_id == subsidy_id)
    if exclude_purchase_id is not None:
        stmt = stmt.where(PurchaseItem.purchase_id != exclude_purchase_id)
    stmt = apply_wish_item_exclusion(stmt, exclude_wish_id)

    actual_rows = (await db.execute(stmt)).all()

    # Дедуп на случай, если у одной purchase_item окажется несколько ContractItem
    # (в норме source_item_id уникален на позицию; JOIN иначе размножит строку).
    ci_by_pi_id: dict[int, ContractItem] = {}
    _seen_pi_ids: set[int] = set()
    _dedup_rows = []
    for row in actual_rows:
        pi_id = row.PurchaseItem.id
        if row.ContractItem is not None and pi_id not in ci_by_pi_id:
            ci_by_pi_id[pi_id] = row.ContractItem
        if pi_id in _seen_pi_ids:
            continue
        _seen_pi_ids.add(pi_id)
        _dedup_rows.append(row)
    actual_rows = _dedup_rows

    # stages: категория одна на весь запрос (все строки уже отфильтрованы по
    # effective_cat_id == feo_category_id), плановые позиции — по id, встреченным
    # в actual_rows (включая неактивные — planned_rows выше содержит только активные).
    feo_cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == feo_category_id)
    )).scalar_one_or_none()

    # Фолбэк стадии «План» (_build_item_stages): план переехал в записи внутри
    # категории — если planned_quantity/planned_amount категории оба NULL, план
    # лежит в активных FeoPlannedItem. Считаем ОДНИМ запросом-агрегатом на весь
    # эндпоинт (категория тут всегда одна — feo_category_id из query), не в цикле
    # по фактическим позициям ниже.
    cat_plan_fallback: Optional[dict] = None
    if feo_cat is not None and feo_cat.planned_quantity is None and feo_cat.planned_amount is None:
        _fb_row = (await db.execute(
            select(
                sqlfunc.coalesce(sqlfunc.sum(FeoPlannedItem.amount), 0),
                sqlfunc.coalesce(sqlfunc.sum(FeoPlannedItem.quantity), 0),
            )
            .where(FeoPlannedItem.feo_category_id == feo_category_id)
            .where(FeoPlannedItem.is_active == True)
        )).one()
        _fb_amt = Decimal(str(_fb_row[0] or 0))
        _fb_qty = Decimal(str(_fb_row[1] or 0))
        if _fb_amt > 0 or _fb_qty > 0:
            cat_plan_fallback = {
                "quantity": _fb_qty if _fb_qty > 0 else None,
                "amount": _fb_amt if _fb_amt > 0 else None,
                "unit_price": (_fb_amt / _fb_qty) if _fb_qty > 0 else None,
            }

    _plan_item_ids = {row.PurchaseItem.feo_planned_item_id for row in actual_rows if row.PurchaseItem.feo_planned_item_id}
    plan_items_map: dict = {}
    if _plan_item_ids:
        _pi_rows = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id.in_(_plan_item_ids))
        )).scalars().all()
        plan_items_map = {p.id: p for p in _pi_rows}

    # Владелец (2026-08-18): «данные-то есть [в позициях закупок], почему они не
    # подтягиваются?» — плановая позиция без СВОЕГО item_type наследует тип от
    # связанных позиций закупок (см. FeoPlannedItemOut.item_type_effective/
    # item_type_inherited). Один сгруппированный запрос на ВСЕ плановые позиции
    # категории сразу (не в цикле по planned_rows — иначе N+1). Фильтры статуса/
    # stopped_at — те же, что и у actual_rows выше (PLANNED_STATUSES +
    # Purchase.stopped_at.is_(None)), чтобы «тип» не подтягивался из
    # отменённых/остановленных закупок.
    _planned_ids_all = [p.id for p in planned_rows]
    _inherited_type_map: dict[int, Optional[str]] = {}
    if _planned_ids_all:
        _type_rows = (await db.execute(
            select(PurchaseItem.feo_planned_item_id, PurchaseItem.item_type)
            .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
            .where(PurchaseItem.feo_planned_item_id.in_(_planned_ids_all))
            .where(Purchase.status.in_(PLANNED_STATUSES))
            .where(Purchase.stopped_at.is_(None))
            .distinct()
        )).all()
        _types_by_planned: dict[int, set] = {}
        for _fpi_id, _itype in _type_rows:
            if not _itype:
                continue
            _types_by_planned.setdefault(_fpi_id, set()).add(_itype)
        for _fpi_id, _types in _types_by_planned.items():
            # Один и тот же непустой тип у всех связанных позиций — наследуем.
            # Разные типы — не выдумываем за пользователя, отдаём None
            # (см. item_type_effective ниже: own или ничего).
            _inherited_type_map[_fpi_id] = next(iter(_types)) if len(_types) == 1 else None

    # Resolve contractor names
    from app.models.contractor import Contractor
    contractor_ids = {row.Purchase.contractor_id for row in actual_rows if row.Purchase.contractor_id}
    contractors = {}
    if contractor_ids:
        c_rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c.name for c in c_rows}

    # Пропорциональное распределение сумм уровня закупки (contract_price / acceptance_doc_amount)
    # между позициями. Считаем по ВСЕМ позициям закупки (не только этой категории) — при
    # feo_per_item одна закупка может охватывать несколько категорий ФЭО одновременно.
    purchase_ids = {row.Purchase.id for row in actual_rows}
    purchase_totals: dict = {}
    if purchase_ids:
        totals_rows = (await db.execute(
            select(
                PurchaseItem.purchase_id,
                sqlfunc.count(PurchaseItem.id),
                sqlfunc.coalesce(sqlfunc.sum(PurchaseItem.total_price), 0),
            )
            .where(PurchaseItem.purchase_id.in_(purchase_ids))
            .group_by(PurchaseItem.purchase_id)
        )).all()
        purchase_totals = {r[0]: (r[1], Decimal(str(r[2] or 0))) for r in totals_rows}

    actual_out = []
    for row in actual_rows:
        pi = row.PurchaseItem
        p = row.Purchase
        _product_id = row._product_id
        _product_has_photo = row._product_has_photo
        _photo_url = row._photo_url
        _photo_link = row._photo_link
        if _product_id is not None and _product_has_photo:
            product_photo = f"/api/products/{_product_id}/photo"
        elif _product_id is not None:
            product_photo = _photo_url or _photo_link or None
        else:
            product_photo = None

        items_count, items_sum = purchase_totals.get(p.id, (1, Decimal(str(pi.total_price or 0))))
        item_total = Decimal(str(pi.total_price or 0))
        if items_count > 1 and items_sum > 0:
            ratio = item_total / items_sum
        elif items_count > 1:
            ratio = Decimal(1) / Decimal(items_count)  # нет сумм для пропорции — делим поровну
        else:
            ratio = Decimal(1)

        # fact_amount/fact_confirmed/fact_allocated — единая формула, вынесена в
        # app.services.feo_plan.purchase_item_fact_amount, чтобы переиспользовать её
        # и в расчёте плановой суммы (ordered_consumption_by_category), без риска разъехаться.
        fact_amount, fact_allocated = purchase_item_fact_amount(pi, p, ratio, items_count)
        fact_confirmed = p.status in FACT_CONFIRMED_STATUSES
        # (plan_schedule / work_in_progress / contracted — это ещё ПЛАН, fact_amount=None)

        _ci = ci_by_pi_id.get(pi.id)
        _stages = _build_item_stages(pi, _ci, feo_cat, plan_items_map, cat_plan_fallback)

        actual_out.append(FeoActualItemOut(
            purchase_item_id=pi.id,
            item_name=pi.item_name,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total_price=pi.total_price,
            feo_planned_item_id=pi.feo_planned_item_id,
            purchase_id=p.id,
            purchase_number=p.purchase_number,
            registry_number=p.registry_number,
            purchase_status=p.status,
            wish_id=p.wish_id,
            contract_number=p.contract_number,
            contractor_name=contractors.get(p.contractor_id) if p.contractor_id else p.item_name,
            product_photo=product_photo,
            final_unit_price=pi.final_unit_price,
            final_total=pi.final_total,
            acceptance_doc_amount=p.acceptance_doc_amount,
            contract_price=p.contract_price,
            purchase_items_count=items_count,
            fact_amount=fact_amount,
            fact_confirmed=fact_confirmed,
            fact_allocated=fact_allocated,
            over_plan=bool(pi.over_plan),
            accepted_name=pi.accepted_name,
            accepted_quantity=pi.accepted_quantity,
            accepted_unit=pi.accepted_unit,
            stages=_stages,
        ))

    planned_out: list[FeoPlannedItemOut] = []
    for r in planned_rows:
        out = FeoPlannedItemOut.model_validate(r)
        _own_type = r.item_type
        if _own_type:
            out.item_type_effective = _own_type
            out.item_type_inherited = False
        else:
            _inherited = _inherited_type_map.get(r.id)
            out.item_type_effective = _inherited
            out.item_type_inherited = bool(_inherited)
        planned_out.append(out)

    return FeoComparisonOut(
        planned=planned_out,
        actual=actual_out,
    )


_WISH_STATUS_LABELS = {
    "draft": "Черновик",
    "submitted": "На согласовании",
    "approved": "Согласовано",
    "rejected": "Не согласовано",
    "converted": "Передано в исполнение",
}
"""Человекочитаемые подписи статуса заявки — зеркалит WishesView.vue (STATUS_LABELS,
не вынесен в общий backend-модуль, у wishes.py своего словаря нет). Используется
ТОЛЬКО GET /{item_id}/consumers ниже — остальной роутер заявочные статусы не
показывает."""


@router.get("/{item_id}/consumers")
async def get_planned_item_consumers(
    item_id: int,
    exclude_purchase_id: Optional[int] = Query(
        None,
        description="Та же закупка, что исключается при загрузке /feo-categories/plan-positions "
                     "и /feo-planned-items/residuals — чтобы редактируемая сейчас закупка не "
                     "выглядела потребителем самой себя, и сумма «съедено» совпадала с consumed.",
    ),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Расшифровка расхода плановой позиции (владелец, 2026-08-20): «Откуда у 14
    футболок... остаток 4512? Я ничего к ним не привязывал. Я не могу это найти.
    Нигде этого не видно...» — список плановых позиций показывает «план X ·
    выбрано Y · остаток Z» (FeoPlannedItemsSelect.vue), но КТО съел Y — нигде не
    видно. Боевой случай: у одной плановой позиции («Футболка Trisar (цвет
    олива) с нанесением», план 15 793,40 ₽) висели ДВЕ строки заявки №40 — сама
    заявка и её собственная закупка. Этот эндпоинт возвращает каждую позицию
    закупки/заявки, ссылающуюся на item_id (feo_planned_item_id), с суммой,
    статусом (по-русски) и данными для перехода — а не просто цифру.

    Фильтры и суммы — СТРОГО та же логика, что app.services.feo_plan
    .planned_item_consumption (используется /feo-categories/plan-positions и
    /feo-planned-items/residuals для того же числа `consumed`): позиция закупки
    учитывается, только если Purchase.status в PLANNED_STATUSES (значит, ещё не
    отменена/не «желание») И Purchase.stopped_at IS NULL И не исключена
    exclude_purchase_id/exclude_wish_id. Иначе цифра «съедено» здесь разошлась бы
    с той, что уже видна в списке позиций — ровно тот дефект, который чинится.

    Каждая позиция ЗАКУПКИ, ссылающаяся на item_id, попадает в ответ ВСЕГДА (даже
    если сейчас не учитывается в сумме — например, закупка отменена/остановлена);
    поле counts_towards_consumed показывает, входит ли она в consumed. Позиции
    ЗАЯВКИ (wish_items) сами по себе план НЕ резервируют (решение владельца
    2026-08-17 — см. planned_item_consumption), поэтому у них
    counts_towards_consumed всегда false; они показаны для полноты картины
    («заявка ещё не в закупке, но уже помечена этой плановой позицией»).

    Дедуп факт-конвертации (владелец: «заявка и закупка — это одна позиция»,
    см. plan_autoassign._fpi_reference_keys): если у позиции заявки есть
    порождённая ею позиция закупки (PurchaseItem.wish_item_id), которая ТОЖЕ
    ссылается на этот же item_id, — в ответе показывается ТОЛЬКО строка закупки
    (более свежие/актуальные данные), а не обе; иначе одна и та же позиция
    выглядела бы двумя потребителями и сумма/список задваивались бы. Сама связь
    видна через поле wish_id на строке закупки — оно указывает, из какой заявки
    та выросла.
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS as _PURCHASE_STATUS_LABELS
    from app.models.user import User

    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Плановая позиция не найдена")

    pi_rows = (await db.execute(
        select(PurchaseItem, Purchase)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(PurchaseItem.feo_planned_item_id == item_id)
        .order_by(PurchaseItem.id)
    )).all()
    wi_rows = (await db.execute(
        select(WishItem, Wish)
        .join(Wish, WishItem.wish_id == Wish.id)
        .where(WishItem.feo_planned_item_id == item_id)
        .order_by(WishItem.id)
    )).all()

    # Автор заявки — батч одним запросом (не полагаемся на Wish.creator lazy="joined"
    # автоподгрузку через plain select(Wish, WishItem), чтобы не зависеть от деталей
    # стратегии загрузки relationship при явном JOIN на два entity).
    creator_ids = {w.created_by for _wi, w in wi_rows if w.created_by is not None}
    creators: dict[int, str] = {}
    if creator_ids:
        u_rows = (await db.execute(
            select(User.id, User.full_name, User.username).where(User.id.in_(creator_ids))
        )).all()
        creators = {u.id: (u.full_name or u.username) for u in u_rows}

    # Та же «одна логическая позиция» (app.services.plan_autoassign._fpi_reference_keys /
    # app.services.feo_plan.apply_wish_item_exclusion) — исключаем строку закупки не
    # только по Purchase.wish_id, но и по PurchaseItem.wish_item_id, если он указывает
    # на WishItem исключаемой заявки, ссылающийся на ЭТУ ЖЕ плановую позицию (уже
    # загружено в wi_rows ниже — второго запроса не требуется).
    _excluded_wish_item_ids = (
        {wi.id for wi, w in wi_rows if w.id == exclude_wish_id} if exclude_wish_id is not None else set()
    )

    def _pi_counts(pi: PurchaseItem, purchase: Purchase) -> bool:
        if purchase.status not in PLANNED_STATUSES:
            return False
        if purchase.stopped_at is not None:
            return False
        if exclude_purchase_id is not None and purchase.id == exclude_purchase_id:
            return False
        if exclude_wish_id is not None and purchase.wish_id == exclude_wish_id:
            return False
        if pi.wish_item_id is not None and pi.wish_item_id in _excluded_wish_item_ids:
            return False
        return True

    converted_wish_item_ids = {pi.wish_item_id for pi, _p in pi_rows if pi.wish_item_id is not None}

    consumers: list[dict] = []
    total_consumed = Decimal("0")

    for pi, p in pi_rows:
        counts = _pi_counts(pi, p)
        amount = Decimal(str(pi.total_price)) if pi.total_price is not None else Decimal("0")
        if counts:
            total_consumed += amount
        consumers.append({
            "type": "purchase",
            "counts_towards_consumed": counts,
            "item_name": pi.item_name,
            "quantity": float(pi.quantity) if pi.quantity is not None else None,
            "unit": pi.unit,
            "amount": float(amount),
            "purchase_id": p.id,
            "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "purchase_subject": p.subject or p.item_name,
            "status": p.status,
            "status_label": _PURCHASE_STATUS_LABELS.get(p.status, p.status),
            "wish_id": p.wish_id,
        })

    for wi, w in wi_rows:
        # Уже представлена строкой закупки выше (см. докстринг: одна логическая
        # позиция) — не дублируем и не считаем сумму дважды.
        if wi.id in converted_wish_item_ids:
            continue
        amount = Decimal(str(wi.total_price)) if wi.total_price is not None else Decimal("0")
        consumers.append({
            "type": "wish",
            # Незаконвертированная заявка план не резервирует (владелец, 2026-08-17) —
            # см. докстринг planned_item_consumption. Показана только для полноты.
            "counts_towards_consumed": False,
            "item_name": wi.item_name,
            "quantity": float(wi.quantity) if wi.quantity is not None else None,
            "unit": wi.unit,
            "amount": float(amount),
            "wish_id": w.id,
            "wish_title": w.title,
            "status": w.status,
            "status_label": _WISH_STATUS_LABELS.get(w.status, w.status),
            "author_name": creators.get(w.created_by) if w.created_by is not None else None,
        })

    planned_amount = float(item.amount) if item.amount is not None else 0.0
    residual = planned_amount - float(total_consumed)

    return {
        "planned_item_id": item.id,
        "planned_item_name": item.name,
        "planned_amount": planned_amount,
        "consumed": float(total_consumed),
        "residual": residual,
        "consumers": consumers,
    }


@router.get("/residuals")
async def get_feo_residuals(
    subsidy_id: int = Query(...),
    exclude_purchase_id: Optional[int] = Query(None),
    exclude_wish_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Returns per-FeoPlannedItem residual for a given subsidy.
    Response: list of {feo_item_id, name, category_id, category_name, planned_amount,
                        used_amount, wish_used_amount, residual, linked_purchase_ids,
                        quantity, unit, used_quantity, residual_quantity}

    Optional ?exclude_purchase_id=X — excludes items of that purchase from
    used_amount and linked_purchase_ids. Use when editing an existing purchase
    to avoid double-counting its own rows.

    Optional ?exclude_wish_id=X — excludes purchases spawned by that wish
    from used_amount. Use when editing an existing wish to avoid showing its
    own привязка as already-consumed plan.

    Решение владельца (2026-08-17): незаконвертированные заявки (Wish) в
    остаток НЕ входят вообще — план расходуют только позиции, попавшие в
    план закупок. Поле wish_used_amount осталось в ответе и всегда равно
    0.0 — ради обратной совместимости фронта, который его читает.
    """
    from app.services.feo_plan import planned_item_consumption

    # All active planned items for this subsidy
    items_q = (
        select(FeoPlannedItem, FeoCategory.id.label("cat_id"), FeoCategory.name.label("cat_name"))
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(FeoPlannedItem.is_active == True)
        .order_by(FeoPlannedItem.id)
    )
    rows = (await db.execute(items_q)).all()

    if not rows:
        return []

    item_ids = [r.FeoPlannedItem.id for r in rows]

    # Общая логика расхода плановой позиции — переиспользуется GET /feo-categories/plan-positions,
    # чтобы оба эндпоинта считали одинаково (см. app/services/feo_plan.py).
    cons_map = await planned_item_consumption(db, item_ids, exclude_purchase_id, exclude_wish_id)

    result = []
    for r in rows:
        item = r.FeoPlannedItem
        planned = float(item.amount or 0)
        planned_qty = float(item.quantity or 0)
        c = cons_map.get(item.id, {"used": 0.0, "used_qty": 0.0, "wish_used": 0.0, "linked_purchase_ids": []})
        used = c["used"]
        used_qty = c["used_qty"]
        wish_used = c["wish_used"]
        result.append({
            "feo_item_id": item.id,
            "name": item.name,
            "category_id": item.feo_category_id,
            "category_name": r.cat_name,
            "planned_amount": planned,
            "used_amount": used,
            "wish_used_amount": wish_used,
            "residual": planned - used,
            "linked_purchase_ids": c["linked_purchase_ids"],
            "quantity": planned_qty,
            "unit": item.unit,
            "used_quantity": used_qty,
            "residual_quantity": planned_qty - used_qty,
        })

    return result
