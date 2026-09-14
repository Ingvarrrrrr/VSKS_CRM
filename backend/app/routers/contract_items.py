"""Phase 27.1: contract_items CRUD router.

7 endpoints scoped under /api/purchases/{pid}/contract-items:
  GET    /                       — list contract items for a purchase
  POST   /                       — create a single contract item
  PUT    /                       — bulk replace all contract items (atomic delete-then-insert)
  PATCH  /{item_id}               — partial update a single contract item
  DELETE /{item_id}               — delete a single contract item
  POST   /copy-from-purchase      — D-01/«Перенести все позиции из ТЗ»: copy all
                                     purchase_items → contract_items 1↔1 (перезаписывает
                                     существующие договорные позиции — подтверждение
                                     показывает фронт, см. PurchaseItemsEditor.vue)
  POST   /copy-names-from-purchase — Волна 4 п.22 «Подставить названия из ТЗ»: меняет
                                     ТОЛЬКО name у уже существующих договорных позиций,
                                     сопоставленных с позицией ТЗ через source_item_id —
                                     количество/цена/сумма/товар не трогаются.

D-17-симметрия: все endpoints используют require_tab("purchases") — новых action'ов нет.
CD-3: router зарегистрирован в __init__.py ПЕРЕД purchases.router (catch-all guard).

Волна 4 п.18 (владелец): при сохранении договорных позиций (PUT/PATCH/POST)
сравниваем с их позицией закупки/ТЗ (по source_item_id) — цена за единицу/
количество/сумма ОТДЕЛЬНО, строго `>`. Превышение не проходит молча — как и
превышение плана ФЭО, оно уходит на согласование (тот же механизм
PlanExcessApproval, ПРАВИЛО №6 — второй способ хранения согласований не
заводится). См. app.services.contract_excess_approval, единственное место,
где формула сравнения и текст отказа определены.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab
from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.user import User
from app.product_matcher import find_matching_product
from app.routers.purchases import _recalc_contract_price_from_contract_items
from app.schemas.schemas import ContractItemCreate, ContractItemOut, ContractItemUpdate
# Правка прод-инцидента (сессия 2026-09-01, см. app/services/contract_item_link.py):
# stale source_item_id, отброшенный ниже в replace_all_contract_items, не должен
# оставлять позицию без ФЭО-категории навсегда — relink пытается найти ту же
# плановую позицию по имени/цене/порядку среди позиций ЭТОЙ закупки.
from app.services.contract_item_link import relink_contract_items
from app.services.contract_excess_approval import enforce_contract_excess_approval

router = APIRouter(prefix="/api/purchases/{pid}/contract-items", tags=["contract_items"])


async def _purchase_items_by_id(db: AsyncSession, pid: int) -> dict:
    """Текущие PurchaseItem закупки, картой по id — общий helper для гейта
    п.18 (ПРАВИЛО №6: один запрос, не дублировать по эндпоинтам)."""
    rows = await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    return {pi.id: pi for pi in rows.scalars().all()}


@router.get("", response_model=List[ContractItemOut],
            dependencies=[Depends(require_tab("purchases"))])
async def list_contract_items(pid: int, db: AsyncSession = Depends(get_db)):
    """List all contract items for a purchase, ordered by id."""
    result = await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == pid)
        .order_by(ContractItem.id)
    )
    return result.scalars().all()


@router.post("", response_model=ContractItemOut, status_code=201,
             dependencies=[Depends(require_tab("purchases"))])
async def create_contract_item(pid: int, data: ContractItemCreate,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """Create a single contract item for a purchase. Triggers D-07 auto-recalc."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})
    payload = data.model_dump(exclude_none=True)
    # D-08-симметрия: Fuzzy auto-link product if missing.
    # Purchase не имеет .org_id напрямую (org — через subsidy); каталог товаров
    # общий для всех орг (см. bulk replace_all_contract_items ниже — тот же
    # паттерн), поэтому поиск без org_id. Раньше здесь падало с AttributeError
    # ('Purchase' object has no attribute 'org_id') — 500 при любом POST с name.
    if not payload.get("product_id") and payload.get("name"):
        matched = await find_matching_product(db, payload["name"])
        if matched:
            payload["product_id"] = matched.id
            payload["match_confirmed"] = False
    # Волна 4 п.18: одна новая строка договора — сравниваем ДО вставки, чтобы
    # отказ не оставил висящих изменений (session.close() откатит flush, но
    # так безопаснее и явнее).
    if payload.get("source_item_id"):
        purchase_items_map = await _purchase_items_by_id(db, pid)
        await enforce_contract_excess_approval(
            db, [ContractItemCreate(**payload)], purchase_items_map,
            subsidy_id=p.subsidy_id, current_user=current_user,
            context_label=f"добавление позиции договора закупки №{p.purchase_number or p.id}",
            fallback_category_id=p.feo_category_id,
        )
    ci = ContractItem(purchase_id=pid, **payload)
    db.add(ci)
    await db.commit()
    await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return ci


@router.put("", response_model=List[ContractItemOut],
            dependencies=[Depends(require_tab("purchases"))])
async def replace_all_contract_items(pid: int, items: List[ContractItemCreate],
                                      db: AsyncSession = Depends(get_db),
                                      current_user: User = Depends(get_current_user)):
    """Bulk replace — atomic delete-then-insert (паттерн purchases.py bulk replace)."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})

    # phase26-dd: validate source_item_id existence — фронт может слать ID
    # старых purchase_items, которые уже удалены в update_purchase bulk replace.
    # ВАЖНО: фильтр по purchase_id == pid обязателен — без него id чужой
    # закупки прошёл бы валидацию как «существующий» (прод-инцидент, сессия
    # 2026-09-01, см. app/services/contract_item_link.py).
    #
    # ⚠️ Волна 4 п.18: этот блок теперь выполняется ДО delete(ContractItem) ниже
    # (раньше был после) — нужен ГЕЙТ excess-проверки (см. ниже), который обязан
    # сработать ДО мутации БД, иначе 409 оставит закупку без старых договорных
    # позиций и без новых.
    src_ids = {it.source_item_id for it in items if getattr(it, 'source_item_id', None)}
    existing_src_ids: set = set()
    purchase_items_map: dict = {}
    if src_ids:
        rows = await db.execute(
            select(PurchaseItem).where(
                PurchaseItem.id.in_(src_ids),
                PurchaseItem.purchase_id == pid,
            )
        )
        purchase_items_map = {pi.id: pi for pi in rows.scalars().all()}
        existing_src_ids = set(purchase_items_map.keys())

    # Волна 4 п.18: сравниваем ПРЕДЛАГАЕМЫЕ строки с их позицией закупки/ТЗ ДО
    # удаления старых договорных позиций — если превышение не согласовано,
    # 409 бросается здесь, и ни одна старая строка ещё не тронута (delete ниже
    # не выполнится). Строки со stale/чужим source_item_id для сравнения не
    # участвуют (effective None — та же логика отбрасывания, что и в цикле
    # создания ниже, ПРАВИЛО №6: один и тот же критерий «валиден ли
    # source_item_id», не два разных).
    _check_items = []
    for it in items:
        if it.source_item_id and it.source_item_id in existing_src_ids:
            _check_items.append(it)
        else:
            _check_items.append(ContractItemCreate(
                **{**it.model_dump(exclude_none=True), "source_item_id": None}
            ))
    await enforce_contract_excess_approval(
        db, _check_items, purchase_items_map,
        subsidy_id=p.subsidy_id, current_user=current_user,
        context_label=f"сохранение позиций договора закупки №{p.purchase_number or p.id}",
        fallback_category_id=p.feo_category_id,
    )

    await db.execute(delete(ContractItem).where(ContractItem.purchase_id == pid))

    created = []
    for it in items:
        payload = it.model_dump(exclude_none=True)
        # Drop stale source_item_id silently — purchase_item уже не существует
        # (или принадлежит чужой закупке). Позиция не остаётся без категории
        # навсегда — relink_contract_items ниже пытается найти замену по
        # имени/цене/порядку среди позиций ЭТОЙ закупки.
        if payload.get("source_item_id") and payload["source_item_id"] not in existing_src_ids:
            payload.pop("source_item_id", None)
        if not payload.get("product_id") and payload.get("name"):
            # 27.4-16: Purchase не имеет .org_id напрямую (org через subsidy).
            # Поиск без org_id — каталог общий для всех орг.
            matched = await find_matching_product(db, payload["name"])
            if matched:
                payload["product_id"] = matched.id
                payload["match_confirmed"] = False
        ci = ContractItem(purchase_id=pid, **payload)
        db.add(ci)
        created.append(ci)
    await db.flush()
    _relinked_count = await relink_contract_items(db, pid)
    if _relinked_count:
        import logging as _log
        _log.getLogger(__name__).info(
            "relink_contract_items: восстановлено %d связей source_item_id для закупки #%s (replace_all_contract_items)",
            _relinked_count, pid,
        )
    await db.commit()
    for ci in created:
        await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return created


@router.patch("/{item_id}", response_model=ContractItemOut,
              dependencies=[Depends(require_tab("purchases"))])
async def patch_contract_item(pid: int, item_id: int, data: ContractItemUpdate,
                               db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    """Partial update a single contract item. Triggers D-07 auto-recalc."""
    ci = await db.get(ContractItem, item_id)
    if not ci or ci.purchase_id != pid:
        raise HTTPException(404, detail={"code": "CONTRACT_ITEM_NOT_FOUND",
                                          "message": f"Позиция договора #{item_id} не найдена"})
    payload = data.model_dump(exclude_unset=True)

    # Волна 4 п.18: собираем эффективные значения ПОСЛЕ патча (merge с текущими
    # полями ci), но ДО setattr на реальном объекте — если превышение не
    # согласовано, 409 бросается раньше, чем что-либо изменится.
    _effective_source_id = payload.get("source_item_id", ci.source_item_id)
    if _effective_source_id:
        p = await db.get(Purchase, pid)
        pi = await db.get(PurchaseItem, _effective_source_id)
        if p is not None and pi is not None and pi.purchase_id == pid:
            _check_item = ContractItemCreate(
                source_item_id=_effective_source_id,
                name=payload.get("name", ci.name),
                quantity=payload.get("quantity", ci.quantity),
                unit=payload.get("unit", ci.unit),
                unit_price=payload.get("unit_price", ci.unit_price),
                total=payload.get("total", ci.total),
            )
            await enforce_contract_excess_approval(
                db, [_check_item], {_effective_source_id: pi},
                subsidy_id=p.subsidy_id, current_user=current_user,
                context_label=f"правка позиции договора закупки №{p.purchase_number or p.id}",
                fallback_category_id=p.feo_category_id,
            )

    for k, v in payload.items():
        setattr(ci, k, v)
    await db.commit()
    await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return ci


@router.delete("/{item_id}", status_code=204,
               dependencies=[Depends(require_tab("purchases"))])
async def delete_contract_item(pid: int, item_id: int,
                                db: AsyncSession = Depends(get_db)):
    """Delete a single contract item. Triggers D-07 auto-recalc."""
    ci = await db.get(ContractItem, item_id)
    if not ci or ci.purchase_id != pid:
        raise HTTPException(404, detail={"code": "CONTRACT_ITEM_NOT_FOUND",
                                          "message": f"Позиция договора #{item_id} не найдена"})
    await db.delete(ci)
    await db.commit()
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return None


@router.post("/copy-from-purchase", response_model=List[ContractItemOut],
             dependencies=[Depends(require_tab("purchases"))])
async def copy_from_purchase_items(pid: int, db: AsyncSession = Depends(get_db)):
    """D-01 / Волна 4 п.22 «Перенести все позиции из ТЗ» — 1↔1 копия
    purchase_items → contract_items (название/количество/цена/сумма/товар/
    доп. атрибуты).

    Перезаписывает существующие contract_items для этой закупки — фронт
    (PurchaseItemsEditor.vue) обязан спросить подтверждение и показать,
    сколько договорных позиций будет стёрто, ПЕРЕД вызовом этого эндпоинта
    (см. владелец, Волна 4 п.22 — переименование и разделение прежней кнопки
    «Скопировать из заявки» на две; см. также
    POST /copy-names-from-purchase ниже — «Подставить названия из ТЗ», которая
    трогает ТОЛЬКО name и не требует подтверждения).
    Возвращает 422 если у закупки нет purchase_items.

    Не проверяется гейтом п.18 (assert/enforce_contract_excess_approval) —
    копия 1↔1 по построению не может превысить исходную позицию (ci.total ==
    pi.total_price и т.д.), сравнивать не с чем.
    """
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})
    items_res = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
        .order_by(PurchaseItem.id)
    )
    purchase_items = items_res.scalars().all()
    if not purchase_items:
        raise HTTPException(
            422,
            detail={
                "code": "NO_PURCHASE_ITEMS",
                "message": (
                    "В заявке нет позиций для копирования. Добавьте позиции в раздел «Заявка» "
                    "или импортируйте КП через кнопку «Импорт из файла/QR»."
                ),
            }
        )
    # Overwrite existing contract_items
    await db.execute(delete(ContractItem).where(ContractItem.purchase_id == pid))
    created = []
    for pi in purchase_items:
        ci = ContractItem(
            purchase_id=pid,
            source_item_id=pi.id,
            product_id=pi.product_id,
            name=pi.item_name,
            quantity=pi.quantity,
            unit=pi.unit,
            unit_price=pi.unit_price,
            total=pi.total_price,
            extra_attrs=getattr(pi, 'extra_attrs', None) or {},
            match_confirmed=True,
        )
        db.add(ci)
        created.append(ci)
    await db.commit()
    for ci in created:
        await db.refresh(ci)
    # D-07 recalc
    await _recalc_contract_price_from_contract_items(pid, db)
    return created


@router.post("/copy-names-from-purchase",
             dependencies=[Depends(require_tab("purchases"))])
async def copy_names_from_purchase_items(pid: int, db: AsyncSession = Depends(get_db)):
    """Волна 4 п.22 «Подставить названия из ТЗ» — меняет ТОЛЬКО `name` у уже
    существующих договорных позиций, сопоставленных со своей позицией ТЗ/
    закупки. Количество/цена/сумма/товар (product_id) НЕ трогаются — в отличие
    от /copy-from-purchase выше, здесь ничего не удаляется и не пересоздаётся.

    Сопоставление — ИСКЛЮЧИТЕЛЬНО через ContractItem.source_item_id, тот же
    канонический канал, что использует весь остальной проект (ФЭО-путь в
    печатных документах, факт ФЭО, relink после update_purchase) — см.
    app.services.contract_item_link. Вторая эвристика (по порядку строк, по
    имени и т.п.) здесь намеренно НЕ заводится (ПРАВИЛО №6): перед сравнением
    вызывается relink_contract_items — та же функция, что чинит связи после
    любого пересоздания purchase_items — и её решение принимается как
    окончательное. При неоднозначности relink оставляет source_item_id пустым
    (её собственный принцип «неоднозначно — NULL», не подставляем чужое имя).

    Договорные позиции, для которых source_item_id так и не разрешился
    (неоднозначность соответствия ИЛИ позиция добавлена в договор вручную
    сверх ТЗ), НЕ трогаются — молча портить состав нельзя. Их id/имя
    перечисляются в ответе (`unmatched`), а `composition_mismatch` явно
    показывает, разошлось ли число строк ТЗ и договора — фронт обязан
    показать это человеку, а не проглотить.
    """
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, detail={"code": "PURCHASE_NOT_FOUND",
                                          "message": f"Закупка #{pid} не найдена"})

    purchase_items_map = await _purchase_items_by_id(db, pid)
    if not purchase_items_map:
        raise HTTPException(
            422,
            detail={
                "code": "NO_PURCHASE_ITEMS",
                "message": "В заявке нет позиций — подставлять названия неоткуда.",
            },
        )

    ci_res = await db.execute(
        select(ContractItem).where(ContractItem.purchase_id == pid).order_by(ContractItem.id)
    )
    contract_items = list(ci_res.scalars().all())
    if not contract_items:
        raise HTTPException(
            422,
            detail={
                "code": "NO_CONTRACT_ITEMS",
                "message": "В договоре нет позиций — сначала перенесите позиции из ТЗ.",
            },
        )

    # relink_contract_items мутирует те же ORM-объекты, что уже загружены в
    # contract_items выше (SQLAlchemy identity map в пределах одной сессии,
    # без commit между вызовами) — повторный SELECT не нужен, .source_item_id
    # уже отражает восстановленные связи сразу после await.
    await relink_contract_items(db, pid)

    updated_count = 0
    unmatched: list[dict] = []
    for ci in contract_items:
        pi = purchase_items_map.get(ci.source_item_id) if ci.source_item_id else None
        if pi is None:
            unmatched.append({"id": ci.id, "name": ci.name})
            continue
        if ci.name != pi.item_name:
            ci.name = pi.item_name
            updated_count += 1

    await db.commit()
    for ci in contract_items:
        await db.refresh(ci)

    return {
        "items": [ContractItemOut.model_validate(ci).model_dump() for ci in contract_items],
        "updated_count": updated_count,
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
        "purchase_items_total": len(purchase_items_map),
        "contract_items_total": len(contract_items),
        "composition_mismatch": len(purchase_items_map) != len(contract_items),
    }
