"""Точечное редактирование ОДНОЙ позиции закупки: привязка товара каталога,
частичный PATCH (название/кол-во/цена/ФЭО), разбивка на части, удаление.

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения. Все пути здесь имеют вид "/{pid}/items/{item_id}[...]" — минимум
два сегмента сверх "{pid}", поэтому НЕ конфликтуют с bare "/{pid}" catch-all
ядра purchases.py, порядок регистрации в routes.py не важен.
"""
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.product import Product
from app.models.feo_category import FeoCategory
from app.models.user import User
from app.auth.jwt import get_current_user, ADMIN_ROLES
from app.services.feo_plan import assert_no_unapproved_excess, assert_tz_not_over_plan, assert_tz_batch_not_over_plan
from app.services.plan_autoassign import auto_assign_planned_items, move_or_detach_planned_item, deactivate_if_orphaned
from app.services.plan_graph_versions import _create_plan_graph_version
from app.services.item_contractor import set_item_contractor
from app.routers.purchases import _has_purchase_write_access, _recalc_purchase_totals, TZ_FROZEN_STATUSES

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


class _SetProductBody(BaseModel):
    product_id: Optional[int] = None  # None — снять привязку


@router.post("/{pid}/items/{item_id}/set-product")
async def set_item_product(
    pid: int,
    item_id: int,
    body: _SetProductBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """27.4-14: точечная запись PurchaseItem.product_id без full PUT.
    Вызывается фронтом сразу после «Добавить в каталог» / выбора товара,
    чтобы привязка пережила F5 без необходимости нажимать общий «Сохранить»."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    if body.product_id is not None:
        prod = await db.get(Product, body.product_id)
        if not prod:
            raise HTTPException(404, "Товар каталога не найден")
        it.product_id = body.product_id
        it.match_confirmed = True
    else:
        it.product_id = None
    await db.commit()
    return {"ok": True, "item_id": item_id, "product_id": it.product_id}


class _ItemPatchBody(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    feo_category_id: Optional[int] = None
    clear_feo_category: bool = False
    # Владелец (2026-08-18, прод-инцидент — «Огнетушитель ОУ-2» перенесён в новую
    # категорию, auto_assign_planned_items не нашёл точное совпадение имени и молча
    # завёл вторую плановую позицию рядом с уже подходящей): явный выбор плановой
    # позиции пользователем в диалоге «Редактировать позицию» — приоритет над
    # автоподбором. Optional[int] с default=None НЕ различает «поле не прислали» и
    # «прислали null» — различаем через `body.model_fields_set` (см. эндпоинт ниже):
    # null, присланный явно, значит «осознанно оставить без плановой позиции».
    feo_planned_item_id: Optional[int] = None
    # Шаг 2 «план ≠ факт» (сессия 2026-08-06): осознанный обход заморозки ТЗ —
    # только ADMIN_ROLES, только явным флагом в теле запроса, пишется в EntityChange.
    admin_override: bool = False


@router.patch("/{pid}/items/{item_id}")
async def patch_purchase_item(
    pid: int,
    item_id: int,
    body: _ItemPatchBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Точечная правка позиции (название/кол-во/цена/ФЭО-привязка) без full PUT закупки."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    # W3 (сужено — принцип владельца, 2026-08-18): «когда перевели в Закупку,
    # редактироваться должно в Закупке — зачем перебрасывает в заявку?». Пока
    # закупка ещё на стадии `wishes` (скрытая закупка-заготовка, которую видно
    # только через дашборд ФЭО, — план закупок её ещё не видел) источник
    # правды остаётся заявка, поэтому правка позиции здесь запрещена. С
    # момента, когда закупка попала в план закупок (`plan_schedule` и дальше),
    # источник правды — сама закупка: правка идёт прямо тут, а не редиректом в
    # заявку (раньше запрет действовал для ЛЮБОГО статуса — правка открывалась
    # в диалоге, но 409'ила при сохранении, тупик с другим текстом). Смена
    # категории ФЭО (feo_category_id / clear_feo_category) была разрешена уже
    # тогда — остаётся разрешена и здесь. Ниже по коду продолжает работать
    # своя, отдельная заморозка ТЗ (TZ_FROZEN_STATUSES) — именно она теперь
    # настоящий ограничитель для объявленных закупок, и её сообщение понятное
    # («закупка объявлена, ТЗ зафиксировано»), а не молчаливый редирект.
    if it.wish_item_id is not None and p.status == "wishes":
        substantive_keys = set(body.model_dump(exclude_unset=True).keys()) - {"feo_category_id", "clear_feo_category"}
        if substantive_keys:
            raise HTTPException(
                409,
                f"Позиция привязана к заявке #{p.wish_id} — редактируйте её в заявке",
            )
    # Шаг 2 «план ≠ факт» (сессия 2026-08-06): заморозка ТЗ с момента объявления
    # закупки. Приоритет ниже гейта W3 выше (тот уже отсёк позиции, привязанные к
    # заявке, — для них редактирование в принципе идёт через заявку, а не сюда).
    # Здесь — отдельная проверка для позиций БЕЗ привязки к заявке (созданных
    # прямо в закупке) и как страховка на случай снятия W3 в будущем.
    _old_qty = _old_price = None
    # Владелец (2026-09-04): «если человек всё удалил из поля и там пусто — значит
    # ничего нет в этом поле». Optional[...]=None НЕ отличает «поле не прислали» от
    # «прислали null» — различаем через body.model_fields_set (тот же приём уже
    # применён для feo_planned_item_id ниже, см. _explicit_planned_item_chosen). Не
    # прислали → не трогаем; прислали null → явная очистка (запись NULL).
    _qty_set = "quantity" in body.model_fields_set
    _price_set = "unit_price" in body.model_fields_set
    _unit_set = "unit" in body.model_fields_set
    _wants_tz_change = _qty_set or _price_set
    if _wants_tz_change and p.status in TZ_FROZEN_STATUSES:
        if body.admin_override and current_user.role in ADMIN_ROLES:
            _old_qty, _old_price = it.quantity, it.unit_price
        else:
            from app.routers.purchase_export import _STATUS_LABELS
            stage = _STATUS_LABELS.get(p.status, p.status)
            raise HTTPException(
                409,
                f"Закупка №{p.purchase_number or p.id} объявлена (стадия «{stage}») — ТЗ зафиксировано. "
                "Цену по итогам закупки внесите в подстроке «Договор» позиции.",
            )
    # Владелец (2026-08-12, «закупка сама становится планом»): категорию ФЭО
    # применяем ДО расчётных проверок ниже (Шаг 5 и Шаг 4), а не после них, как
    # было раньше, — так гейты и автозаведение плана видят актуальную категорию.
    # Перенос позиции в ДРУГУЮ категорию (боевой случай — категория 3716
    # «Приобретение брендированных футболок» получила закупку без единой
    # плановой позиции) означает, что старая привязка feo_planned_item_id
    # принадлежит прежней категории и в категории-получателе может не быть
    # ничего — очищаем её и заводим/находим план в новой категории тем же
    # общим сервисом, что и wishes.py (app/services/plan_autoassign.py).
    _cat_id_before_patch = it.feo_category_id
    _category_changing = False
    if body.clear_feo_category:
        if it.feo_category_id is not None:
            _category_changing = True
        it.feo_category_id = None
    elif body.feo_category_id is not None:
        cat = await db.get(FeoCategory, body.feo_category_id)
        if not cat:
            raise HTTPException(404, "Категория ФЭО не найдена")
        if p.subsidy_id and cat.subsidy_id != p.subsidy_id:
            raise HTTPException(422, "Категория ФЭО относится к другой субсидии")
        if body.feo_category_id != it.feo_category_id:
            _category_changing = True
        it.feo_category_id = body.feo_category_id
    # Синхронизировать feo_category_id с WishItem при category-only правке wish-позиции
    if it.wish_item_id is not None and (body.clear_feo_category or body.feo_category_id is not None):
        from app.models.wish_item import WishItem as _WishItem
        wi = await db.get(_WishItem, it.wish_item_id)
        if wi is not None:
            wi.feo_category_id = it.feo_category_id
    # Плановые позиции следуют за сменой категории (владелец, 2026-08-17):
    # если у переносимой позиции есть СОБСТВЕННАЯ плановая позиция (никто
    # больше на неё не ссылается — см. move_or_detach_planned_item), она
    # переезжает в новую категорию ВМЕСТЕ с этой позицией — та же строка, тот
    # же id, история не теряется. Если позиция — не единственный владелец
    # плановой строки (общий план на несколько закупок/заявку и её уже
    # сконвертированную закупку), плановая строка НЕ трогается, привязка
    # переносимой позиции снимается, а предупреждение уходит в ответ явно
    # (см. _plan_transfer_warning в теле ответа ниже).
    # Владелец (2026-08-18): пользователь выбрал плановую позицию САМ (диалог
    # «Редактировать позицию», FeoPlannedItemsSelect) — приоритет над автоподбором
    # по имени. `"feo_planned_item_id" in body.model_fields_set` отличает «поле не
    # прислали» (прежнее поведение, автоподбор ниже) от «прислали, в т.ч. null»
    # (осознанный выбор/снятие выбора человеком). При явном выборе НЕ вызываем ни
    # move_or_detach_planned_item, ни auto_assign_planned_items — иначе они, отработав
    # по СТАРОЙ привязке it.feo_planned_item_id (переезд/автоподбор смотрят именно на
    # неё), либо молча переедут/создадут не то, что выбрал человек, либо (что хуже)
    # move_or_detach_planned_item отработает первым и его результат применится ДО
    # явного выбора и будет им тут же перезаписан — вычислять его вообще незачем.
    _explicit_planned_item_chosen = "feo_planned_item_id" in body.model_fields_set
    _plan_transfer_warning: Optional[str] = None
    if not _explicit_planned_item_chosen:
        if _category_changing and it.feo_planned_item_id is not None:
            if it.feo_category_id is not None:
                _plan_transfer_warning = await move_or_detach_planned_item(db, it, it.feo_category_id)
            else:
                # clear_feo_category: категории больше нет — плановой позиции
                # переезжать некуда, привязка просто снимается (как и раньше).
                _old_fpi_id = it.feo_planned_item_id
                it.feo_planned_item_id = None
                it.over_plan = False
                from app.models.feo_planned_item import FeoPlannedItem as _FPI
                _old_fpi = await db.get(_FPI, _old_fpi_id)
                await deactivate_if_orphaned(db, _old_fpi)
        if _category_changing and it.feo_category_id is not None and it.feo_planned_item_id is None:
            # auto_assign_planned_items смотрит на текущие item_name/quantity/
            # total_price позиции — если это ЖЕ тело правки одновременно меняет и
            # название/кол-во/цену (мутируются НИЖЕ), новая плановая позиция (если
            # заводится с нуля) фиксирует снимок ДО этих правок; для типичного
            # случая «просто перенести позицию в другую категорию» разницы нет.
            await auto_assign_planned_items(
                [it], it.feo_category_id, db,
                note=f"переносом позиции в закупке №{p.purchase_number or p.id}",
            )
    else:
        from app.models.feo_planned_item import FeoPlannedItem as _FPIExplicit
        _old_fpi_id_explicit = it.feo_planned_item_id
        if body.feo_planned_item_id is not None:
            _chosen_fpi = await db.get(_FPIExplicit, body.feo_planned_item_id)
            if not _chosen_fpi:
                raise HTTPException(404, "Плановая позиция не найдена")
            # Деактивированная плановая позиция исключена из UI-подбора
            # (/feo-categories/plan-positions фильтрует is_active == True), но
            # явный выбор идёт по id и обходит этот фильтр. Привязка к погашенной
            # позиции делает сумму невидимой для
            # plan_consumption_by_category(exclude_planned_item_linked=True) —
            # позиция числится «привязанной к плану», а плана нет. Находка QA
            # 2026-08-18.
            if not _chosen_fpi.is_active:
                raise HTTPException(
                    409,
                    f"Плановая позиция «{_chosen_fpi.name}» деактивирована (удалена из плана), "
                    f"привязка к ней невозможна — выберите действующую или создайте новую.",
                )
            # Этапы 2-3 (владелец, 2026-09-02): проверка совпадения категорий (или
            # потомка) + разрешение суперадмину с уведомлением вынесены в общий
            # хелпер — тот же, что зовёт POST /feo-planned-items/map (см.
            # app/services/plan_autoassign.py::check_planned_item_category_link),
            # чтобы правило не разъезжалось по двум копиям. Эффективная категория
            # позиции — своя (it.feo_category_id), а если её нет — категория шапки
            # (тот же фолбэк, что использует _item_feo_mismatch).
            from app.services.plan_autoassign import check_planned_item_category_link
            _effective_item_cat_id = it.feo_category_id or p.feo_category_id
            await check_planned_item_category_link(
                db,
                purchase=p,
                item=it,
                item_category_id=_effective_item_cat_id,
                planned_category_id=_chosen_fpi.feo_category_id,
                planned_item_name=_chosen_fpi.name,
                current_user=current_user,
            )
            it.feo_planned_item_id = body.feo_planned_item_id
            it.over_plan = False
        else:
            # Явный null — пользователь снял выбор, осознанно оставляем без плана.
            it.feo_planned_item_id = None
            it.over_plan = False
        # Старая привязка (если была и реально сменилась) больше не имеет прежнего
        # владельца — если она была заведена автоматически и осиротела, деактивируем
        # (тот же порядок уборки, что и у move_or_detach_planned_item/clear-ветки выше).
        if _old_fpi_id_explicit is not None and _old_fpi_id_explicit != it.feo_planned_item_id:
            _old_fpi_explicit = await db.get(_FPIExplicit, _old_fpi_id_explicit)
            await deactivate_if_orphaned(db, _old_fpi_explicit)
    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): проверяем ДО записи
    # цены/кол-ва — прогнозные значения (patch частичный, недостающие берём из
    # текущей строки). admin_override (та же роль/флаг, что и для заморозки ТЗ
    # выше) — осознанный обход, как и у остальных гейтов превышения плана.
    # feo_planned_item_id/feo_category_id берём УЖЕ ФИНАЛЬНЫМИ с it (категория и
    # автозаведение применены выше).
    if _wants_tz_change and not (body.admin_override and current_user.role in ADMIN_ROLES):
        _prospective_qty = body.quantity if _qty_set else it.quantity
        _prospective_price = body.unit_price if _price_set else it.unit_price
        _prospective_total = (_prospective_qty or Decimal("0")) * (_prospective_price or Decimal("0"))
        # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): PATCH правит ОДНУ
        # позицию — «братья» (другие строки ЭТОЙ ЖЕ закупки на ту же плановую
        # позицию) лежат в БД, а не в памяти, как у create/PUT. Считаем их сумму
        # отдельным запросом и передаём как sibling_quantity/sibling_total, иначе
        # эта позиция пройдёт гейт поодиночке, даже если вместе с братьями план
        # уже превышен (см. assert_tz_batch_not_over_plan в feo_plan.py).
        _sib_qty = Decimal("0")
        _sib_total = Decimal("0")
        if it.feo_planned_item_id is not None:
            _sib_row = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(PurchaseItem.quantity), 0),
                        func.coalesce(func.sum(PurchaseItem.total_price), 0),
                    ).where(
                        PurchaseItem.purchase_id == pid,
                        PurchaseItem.feo_planned_item_id == it.feo_planned_item_id,
                        PurchaseItem.id != it.id,
                        func.coalesce(PurchaseItem.over_plan, False).is_(False),
                    )
                )
            ).one()
            _sib_qty = Decimal(str(_sib_row[0] or 0))
            _sib_total = Decimal(str(_sib_row[1] or 0))
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=it.feo_planned_item_id,
            feo_category_id=it.feo_category_id,
            quantity=_prospective_qty,
            unit_price=_prospective_price,
            total_price=_prospective_total,
            item_name=body.item_name if body.item_name is not None else it.item_name,
            sibling_quantity=_sib_qty,
            sibling_total=_sib_total,
        )
    # Задача владельца, план zany-fluttering-mountain.md п.4 (2026-08-10): точечная
    # правка позиции — тоже «добавление позиции в категорию» (рост суммы позиции
    # ИЛИ смена её категории ФЭО на другую) — увеличивающее план действие. Раньше
    # здесь проверялось только «ТЗ не выше своей плановой позиции» (assert_tz_not_over_plan
    # выше) — сторону «категория не превышает финансирование ФЭО» (assert_no_unapproved_excess)
    # этот эндпоинт вообще не видел. Считаем ДО и ПОСЛЕ отдельно от _wants_tz_change
    # выше — смена ТОЛЬКО feo_category_id (без правки qty/price) тоже обязана
    # пройти гейт, а _wants_tz_change в этом случае False. Старая категория —
    # _cat_id_before_patch (снята ДО применения категории выше), новая — it.feo_category_id
    # (уже финальная).
    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # см. комментарий у create_purchase. Отдаётся в ответе как excess_warnings
    # (этот эндпоинт возвращает plain dict, не PurchaseOut — см. return ниже).
    _excess_warnings: list[dict] = []
    if not (body.admin_override and current_user.role in ADMIN_ROLES):
        _old_item_cat_id = _cat_id_before_patch
        _old_item_total = Decimal(str(it.total_price or 0))
        _new_item_cat_id = it.feo_category_id
        if _qty_set or _price_set:
            _new_qty_g = body.quantity if _qty_set else it.quantity
            _new_price_g = body.unit_price if _price_set else it.unit_price
            _new_item_total = (_new_qty_g or Decimal("0")) * (_new_price_g or Decimal("0"))
        else:
            _new_item_total = _old_item_total
        if _new_item_cat_id:
            _item_delta = _new_item_total - _old_item_total
            if _new_item_cat_id == _old_item_cat_id:
                if _item_delta > 0:
                    _excess_warnings.extend(
                        await assert_no_unapproved_excess(db, _new_item_cat_id, adding_amount=_item_delta)
                    )
            else:
                # Владелец (2026-08-12): «Когда заявка идёт с превышением ... должна
                # быть возможность передвижки, уменьшения». Боевой случай — позиции
                # «Перчатки нитриловые» нельзя было перенести 3710→3691, потому что у
                # их общего предка 3676 висело непогашенное превышение, хотя перенос
                # не тратит ни рубля сверху и как раз чинит перерасход категории-
                # источника. Смена категории — ПЕРЕКЛАДЫВАНИЕ, а не новая трата: сумма
                # уходит из старой категории (там это путь возврата в рамки плана — не
                # блокируется) и появляется в новой БЕЗ прироста суммарно по субсидии.
                # Блокируем ТОЛЬКО реальный прирост денег (если позиция одновременно с
                # переездом ещё и подорожала) — против НОВОЙ категории, а не всю сумму
                # позиции целиком.
                if _item_delta > 0:
                    _excess_warnings.extend(
                        await assert_no_unapproved_excess(db, _new_item_cat_id, adding_amount=_item_delta)
                    )
    if body.item_name is not None:
        name = body.item_name.strip()
        if not name:
            raise HTTPException(422, "Название позиции не может быть пустым")
        it.item_name = name
    if _qty_set:
        it.quantity = body.quantity
    if _unit_set:
        it.unit = (body.unit.strip() or None) if body.unit is not None else None
    if _price_set:
        it.unit_price = body.unit_price
    if _qty_set or _price_set:
        qty = it.quantity or Decimal("0")
        price = it.unit_price or Decimal("0")
        it.total_price = qty * price
        # Снимок плана (Шаг 1 «план ≠ факт»): пока закупка в статусе «План закупок» —
        # правка кол-ва/цены двигает и снимок плана вместе с ТЗ (план ещё формируется).
        # С «Ведётся работа» и далее сюда попасть можно только через admin_override
        # (гейт TZ_FROZEN_STATUSES выше) — снимок плана в этом случае намеренно НЕ
        # трогаем: план обязан остаться зафиксированным даже при осознанном обходе
        # заморозки ТЗ администратором.
        if p.status == "plan_schedule":
            it.planned_quantity = it.quantity
            it.planned_unit_price = it.unit_price
            it.planned_total = it.total_price
    # Зеркалим правку обратно в позицию заявки (принцип владельца, 2026-08-18):
    # раз W3 выше больше не запрещает править позицию прямо в закупке для
    # закупок, ушедших в план (см. комментарий у W3), позиция закупки и
    # связанная wish_items начнут расходиться — ровно тот дефект, на который
    # жаловался владелец («заявка показывает одну плановую позицию, дашборд
    # другую»). Симметрично зеркалированию в POST /api/feo-planned-items/map
    # (app/routers/feo_planned_items.py::map_purchase_item_to_planned).
    # Синхронизируем ТОЛЬКО то, что реально пришло/изменилось этим запросом —
    # не переписывать в заявке то, чего не трогали (выбранное на предыдущем
    # этапе не меняется само). _category_changing/it.feo_planned_item_id уже
    # финальные на этом месте (категория и автоподбор плана применены выше).
    if it.wish_item_id is not None:
        _patch_keys = set(body.model_dump(exclude_unset=True).keys())
        _qty_or_price_changed = "quantity" in _patch_keys or "unit_price" in _patch_keys
        # Явный выбор плановой позиции (см. _explicit_planned_item_chosen выше) тоже
        # обязан зеркалиться в WishItem — иначе он мирроится только при СМЕНЕ
        # категории, а «выбрал другую плановую позицию внутри той же категории»
        # (типичный случай диалога «Редактировать позицию») расходится с заявкой.
        if _patch_keys & {"item_name", "quantity", "unit", "unit_price"} or _category_changing or _explicit_planned_item_chosen:
            from app.models.wish_item import WishItem as _WishItem
            wi = await db.get(_WishItem, it.wish_item_id)
            if wi is not None:
                if "item_name" in _patch_keys:
                    wi.item_name = it.item_name
                if "quantity" in _patch_keys:
                    wi.quantity = it.quantity
                if "unit" in _patch_keys:
                    wi.unit = it.unit
                if "unit_price" in _patch_keys:
                    wi.unit_price = it.unit_price
                if _qty_or_price_changed:
                    wi.total_price = it.total_price
                if _category_changing or _explicit_planned_item_chosen:
                    wi.feo_category_id = it.feo_category_id
                    wi.feo_planned_item_id = it.feo_planned_item_id
    await db.flush()
    await _recalc_purchase_totals(p, db)
    if p and p.subsidy_id:
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение позиций закупки #{p.purchase_number or p.id}")
    # Шаг 2 «план ≠ факт»: admin_override обошёл заморозку ТЗ на объявленной
    # закупке — фиксируем в EntityChange, чтобы правка была видна в истории.
    if body.admin_override and current_user.role in ADMIN_ROLES and p.status in TZ_FROZEN_STATUSES:
        try:
            from app.models.entity_change import EntityChange as _EC
            if _old_qty is not None and str(_old_qty) != str(it.quantity):
                db.add(_EC(
                    entity_type='purchase_item', entity_id=it.id, field_name='quantity',
                    old_value=str(_old_qty), new_value=str(it.quantity),
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
            if _old_price is not None and str(_old_price) != str(it.unit_price):
                db.add(_EC(
                    entity_type='purchase_item', entity_id=it.id, field_name='unit_price',
                    old_value=str(_old_price), new_value=str(it.unit_price),
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        except Exception as _exc:
            import logging as _log
            _log.getLogger(__name__).warning("entity_change record failed for purchase_item admin_override: %s", _exc)
    await db.commit()
    return {
        "ok": True, "item_id": it.id, "item_name": it.item_name,
        "quantity": float(it.quantity or 0), "unit": it.unit,
        "unit_price": float(it.unit_price or 0), "total_price": float(it.total_price or 0),
        "feo_category_id": it.feo_category_id,
        "feo_planned_item_id": it.feo_planned_item_id,
        "planned_quantity": float(it.planned_quantity) if it.planned_quantity is not None else None,
        "planned_unit_price": float(it.planned_unit_price) if it.planned_unit_price is not None else None,
        "planned_total": float(it.planned_total) if it.planned_total is not None else None,
        # Плановые позиции следуют за сменой категории: не None, если плановая
        # позиция была общей с другими закупками/заявкой и её пришлось
        # отвязать вместо переезда (см. move_or_detach_planned_item) — фронт
        # обязан показать это пользователю, а не проглатывать молча.
        "plan_transfer_warning": _plan_transfer_warning,
        # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
        # см. assert_no_unapproved_excess (feo_plan.py) и комментарий у вызовов выше.
        "excess_warnings": _excess_warnings,
    }


class _ItemSplitPart(BaseModel):
    quantity: Decimal
    feo_category_id: Optional[int] = None
    feo_planned_item_id: Optional[int] = None


class _ItemSplitBody(BaseModel):
    parts: list[_ItemSplitPart]


def _split_by_quantity(
    total,
    original_qty: Decimal,
    quantities: list[Decimal],
    precision: Decimal,
) -> list[Optional[Decimal]]:
    """Раскладывает `total` на доли, пропорциональные `quantities` от `original_qty`
    — владелец (2026-08-18, разбивка позиции закупки, см. split_purchase_item).

    `total is None` → весь результат None (снимка/поля не было — незачем его
    придумывать). Последняя доля получает остаток (`total − Σ предыдущих`), а не
    свою пропорциональную долю — иначе округление до `precision` может увести
    сумму долей от исходного `total` на копейки («баланс копейка в копейку»).
    """
    if total is None:
        return [None] * len(quantities)
    total_d = Decimal(str(total))
    n = len(quantities)
    shares: list[Decimal] = []
    running = Decimal("0")
    for i, q in enumerate(quantities):
        if i < n - 1:
            share = (total_d * q / original_qty).quantize(precision)
            shares.append(share)
            running += share
        else:
            shares.append(total_d - running)
    return shares


@router.post("/{pid}/items/{item_id}/split")
async def split_purchase_item(
    pid: int,
    item_id: int,
    body: _ItemSplitBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разбивка ОДНОЙ позиции закупки на несколько частей по разным категориям
    ФЭО / плановым позициям — владелец (2026-08-18, закупка №890 «Огнетушители»,
    status=ordered): 66 шт нужно разложить 41+25 по разным ФЭО, а добавление
    НОВОЙ позиции в проведённую/поставленную закупку справедливо запрещено
    (см. TZ_FROZEN_STATUSES у patch_purchase_item).

    Ключевое отличие от patch_purchase_item: разбивка НЕ меняет ни Σ количества,
    ни Σ суммы позиции (66 остаются 66, 54 318 ₽ остаются 54 318 ₽) — меняется
    только распределение по категориям/плановым позициям. Поэтому TZ_FROZEN_STATUSES
    ЗДЕСЬ СОЗНАТЕЛЬНО НЕ ПРИМЕНЯЕТСЯ (в отличие от patch_purchase_item) — заморозка
    защищает от изменения зафиксированного ТЗ, а не от его перекладки по одной и
    той же сумме между категориями.

    Порядок: СНАЧАЛА все проверки (включая гейт «ТЗ не выше плана» на
    получившийся набор частей целиком), ПОТОМ любые мутации/db.add — при отказе
    на любом шаге в сессии нет ни одной применённой правки (общий паттерн ORM-
    сессии в этом роутере: без явного db.commit() правки не переживают закрытие
    сессии, но здесь валидация вынесена перед мутациями even more строго — чтобы
    не зависеть от этого поведения).
    """
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    parts = body.parts
    if len(parts) < 2:
        raise HTTPException(400, "Для разбивки нужно минимум 2 части")
    for idx, part in enumerate(parts, start=1):
        if part.quantity is None or part.quantity <= 0:
            raise HTTPException(400, f"Количество части {idx} должно быть больше нуля")

    original_qty = Decimal(str(it.quantity or 0))
    quantities = [Decimal(str(pt.quantity)) for pt in parts]
    parts_qty_sum = sum(quantities, Decimal("0"))
    if parts_qty_sum != original_qty:
        raise HTTPException(
            409,
            f"Сумма количества частей ({parts_qty_sum}) не равна количеству позиции «{it.item_name}» "
            f"({original_qty}) — разбивка не меняет ни количество, ни сумму позиции, только распределение "
            "по категориям ФЭО.",
        )

    # Категории/плановые позиции частей — те же проверки и формулировки ошибок,
    # что и в patch_purchase_item (см. ветки feo_category_id / _explicit_planned_item_chosen).
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    for idx, part in enumerate(parts, start=1):
        if part.feo_category_id is not None:
            cat = await db.get(FeoCategory, part.feo_category_id)
            if not cat:
                raise HTTPException(404, f"Категория ФЭО части {idx} не найдена")
            if p.subsidy_id and cat.subsidy_id != p.subsidy_id:
                raise HTTPException(422, f"Категория ФЭО части {idx} относится к другой субсидии")
        if part.feo_planned_item_id is not None:
            fpi = await db.get(_FPI, part.feo_planned_item_id)
            if not fpi:
                raise HTTPException(404, f"Плановая позиция части {idx} не найдена")
            if not fpi.is_active:
                raise HTTPException(
                    409,
                    f"Плановая позиция «{fpi.name}» (часть {idx}) деактивирована (удалена из плана), "
                    "привязка к ней невозможна — выберите действующую или создайте новую.",
                )
            if part.feo_category_id is None or fpi.feo_category_id != part.feo_category_id:
                _fpi_cat_name = (await db.execute(
                    select(FeoCategory.name).where(FeoCategory.id == fpi.feo_category_id)
                )).scalar_one_or_none() or f"#{fpi.feo_category_id}"
                if part.feo_category_id is not None:
                    _target_cat_name = (await db.execute(
                        select(FeoCategory.name).where(FeoCategory.id == part.feo_category_id)
                    )).scalar_one_or_none() or f"#{part.feo_category_id}"
                else:
                    _target_cat_name = "без категории ФЭО"
                raise HTTPException(
                    409,
                    f"Плановая позиция «{fpi.name}» относится к категории «{_fpi_cat_name}», "
                    f"а часть {idx} — к категории «{_target_cat_name}». Выберите плановую позицию той же категории.",
                )

    # Договорные строки (contract_items.source_item_id == item_id): решение
    # владельца (2026-08-18) — разбить в ТОЙ ЖЕ пропорции количества. Если строк
    # больше одной, однозначного правила разложения нет («какая из двух строк
    # какую часть представляет?») — отказываем, а не гадаем.
    from app.models.contract_item import ContractItem
    contract_rows = (await db.execute(
        select(ContractItem).where(ContractItem.source_item_id == item_id)
    )).scalars().all()
    if len(contract_rows) > 1:
        raise HTTPException(
            409,
            f"К позиции «{it.item_name}» привязано {len(contract_rows)} строк договора — "
            "разбивка позиций с несколькими договорными строками не поддерживается.",
        )

    # unit_price всех частей — как у исходной позиции (правило 4: не принимается
    # из тела вовсе). total_price части = quantity × unit_price, последняя часть
    # добирает остаток (исходный total_price − сумма предыдущих) — так Σ total
    # сходится копейка в копейку даже при округлении quantity × unit_price.
    unit_price = it.unit_price if it.unit_price is not None else Decimal("0")
    original_total = Decimal(str(it.total_price or 0))
    n = len(parts)
    part_totals: list[Decimal] = []
    _running_total = Decimal("0")
    for i, q in enumerate(quantities):
        if i < n - 1:
            t = (q * unit_price).quantize(Decimal("0.01"))
            part_totals.append(t)
            _running_total += t
        else:
            part_totals.append(original_total - _running_total)

    # Снимок плана — пропорционально quantity; planned_unit_price копируется как
    # есть (не пересчитывается), planned_total — тем же правилом остатка, что и total_price.
    planned_quantities = _split_by_quantity(it.planned_quantity, original_qty, quantities, Decimal("0.0001"))
    planned_totals = _split_by_quantity(it.planned_total, original_qty, quantities, Decimal("0.01"))
    # НДС-поля и final_total — тоже денежные величины, зависящие от суммы позиции;
    # раскладываем той же пропорцией с остатком у последней части, иначе у новых
    # частей осталась бы сумма НДС/факт-итог ВСЕЙ исходной позиции целиком.
    vat_amounts = _split_by_quantity(it.vat_amount, original_qty, quantities, Decimal("0.01"))
    total_with_vats = _split_by_quantity(it.total_with_vat, original_qty, quantities, Decimal("0.01"))
    final_totals = _split_by_quantity(it.final_total, original_qty, quantities, Decimal("0.01"))

    # Гейт «ТЗ не выше плана» — на получившийся набор частей ЦЕЛИКОМ, через уже
    # существующий assert_tz_batch_not_over_plan (правило 8): он группирует по
    # feo_planned_item_id и накапливает, чтобы две части на одну плановую позицию
    # считались вместе, а не проходили гейт поодиночке. Лёгкие объекты
    # (SimpleNamespace), а не реальные ORM-строки — проверка идёт ДО каких-либо
    # мутаций/db.add (см. docstring выше).
    from types import SimpleNamespace
    _check_rows = [
        SimpleNamespace(
            item_name=it.item_name,
            quantity=quantities[i],
            unit_price=unit_price,
            total_price=part_totals[i],
            feo_planned_item_id=parts[i].feo_planned_item_id,
            feo_category_id=parts[i].feo_category_id,
            # over_plan исходной позиции наследуется частями (не сбрасывается в
            # False) — разбивка не меняет ни количество, ни сумму позиции в
            # целом, значит уже согласованное превышение плана не растёт;
            # assert_tz_batch_not_over_plan пропускает строки с over_plan=True
            # целиком (см. её docstring), поэтому легитимная разбивка
            # согласованной сверх-плана позиции не должна получать 409
            # (находка QA 2026-08-18).
            over_plan=bool(it.over_plan),
        )
        for i in range(n)
    ]
    await assert_tz_batch_not_over_plan(db, _check_rows, fallback_category_id=it.feo_category_id)

    # --- Все проверки пройдены — дальше только мутации. ---

    # Снимок «прочих» полей исходной позиции ДО мутации — копируется в новые части.
    # accepted_name/accepted_quantity/accepted_unit (стадия «Приняли») сознательно
    # НЕ копируются в новые части: это факт приёмки уже поставленного количества,
    # привязанный к конкретной приёмке, а не к распределению по ФЭО — слепое
    # копирование задвоило бы принятое количество на бумаге. Остаётся только у
    # исходной строки (первая часть).
    _src_item_name = it.item_name
    _src_item_type = it.item_type
    _src_unit = it.unit
    _src_product_id = it.product_id
    _src_country_origin = it.country_origin
    _src_contractor_id = it.contractor_id
    _src_contractor_inn = it.contractor_inn
    _src_contractor_name = it.contractor_name
    _src_match_confirmed = it.match_confirmed
    _src_vat_rate = it.vat_rate
    _src_receipt_id = it.receipt_id
    _src_needed_date = it.needed_date
    _src_final_unit_price = it.final_unit_price
    _src_planned_unit_price = it.planned_unit_price

    # Часть 1 — мутируем исходную строку: id, история (EntityChange), wish_item_id
    # и прочие ссылки сохраняются (правило: «исходная строка сохраняется»).
    it.quantity = quantities[0]
    it.total_price = part_totals[0]
    it.feo_category_id = parts[0].feo_category_id
    it.feo_planned_item_id = parts[0].feo_planned_item_id
    # over_plan НЕ сбрасывается — см. комментарий у _check_rows выше
    # (находка QA 2026-08-18): количество/сумма позиции не меняются разбивкой,
    # значит и статус согласованного превышения плана остаётся тем же.
    it.planned_quantity = planned_quantities[0]
    it.planned_total = planned_totals[0]
    it.vat_amount = vat_amounts[0]
    it.total_with_vat = total_with_vats[0]
    it.final_total = final_totals[0]

    created_items: list[PurchaseItem] = [it]
    for i in range(1, n):
        new_item = PurchaseItem(
            purchase_id=pid,
            product_id=_src_product_id,
            item_name=_src_item_name,
            item_type=_src_item_type,
            quantity=quantities[i],
            unit=_src_unit,
            unit_price=unit_price,
            total_price=part_totals[i],
            final_unit_price=_src_final_unit_price,
            final_total=final_totals[i],
            planned_quantity=planned_quantities[i],
            planned_unit_price=_src_planned_unit_price,
            planned_total=planned_totals[i],
            country_origin=_src_country_origin,
            feo_planned_item_id=parts[i].feo_planned_item_id,
            feo_category_id=parts[i].feo_category_id,
            match_confirmed=_src_match_confirmed,
            vat_rate=_src_vat_rate,
            vat_amount=vat_amounts[i],
            total_with_vat=total_with_vats[i],
            receipt_id=_src_receipt_id,
            needed_date=_src_needed_date,
            # W1 (hard link заявка↔строка закупки): одна позиция заявки не может
            # соответствовать двум строкам закупки — у НОВЫХ частей wish_item_id
            # всегда NULL, привязку к заявке «наследует» только исходная строка.
            wish_item_id=None,
            # over_plan наследуется от исходной позиции — см. комментарий у
            # _check_rows выше (находка QA 2026-08-18).
            over_plan=bool(it.over_plan),
        )
        # ПРАВИЛО №6 (группа D5, QA round 2): единственный писатель —
        # item_contractor.set_item_contractor (не голый contractor_id=.../
        # contractor_inn=.../contractor_name=... в конструкторе выше).
        set_item_contractor(new_item, contractor_id=_src_contractor_id, inn=_src_contractor_inn, name=_src_contractor_name)
        db.add(new_item)
        created_items.append(new_item)
    await db.flush()  # получить id новых позиций — нужны для source_item_id договорных строк и ответа

    # Договорные строки (максимум одна — отказ выше при 2+, правило владельца):
    # разбиваются в ТОЙ ЖЕ пропорции quantity, что и сама позиция закупки. Сумма
    # договора не меняется — та же логика остатка у последней части.
    new_contract_ids: list[int] = []
    if contract_rows:
        cr = contract_rows[0]
        cr_quantities = _split_by_quantity(cr.quantity, original_qty, quantities, Decimal("0.0001"))
        cr_totals = _split_by_quantity(cr.total, original_qty, quantities, Decimal("0.01"))
        cr.quantity = cr_quantities[0]
        cr.total = cr_totals[0]
        # source_item_id у исходной строки договора не меняется (it.id тот же).
        for i in range(1, n):
            new_cr = ContractItem(
                purchase_id=pid,
                source_item_id=created_items[i].id,
                contract_id=cr.contract_id,
                product_id=cr.product_id,
                name=cr.name,
                quantity=cr_quantities[i],
                unit=cr.unit,
                unit_price=cr.unit_price,
                total=cr_totals[i],
                vat_rate=cr.vat_rate,
                match_confirmed=cr.match_confirmed,
            )
            db.add(new_cr)
            new_contract_ids.append(new_cr)
        await db.flush()
        new_contract_ids = [c.id for c in new_contract_ids]

    await _recalc_purchase_totals(p, db)
    if p.subsidy_id:
        await _create_plan_graph_version(
            subsidy_id=p.subsidy_id, db=db, user=current_user,
            note=f"Авто-версия: разбивка позиции закупки #{p.purchase_number or p.id}",
        )

    # История — тем же способом, что patch_purchase_item (EntityChange), с
    # осмысленным описанием («разбита позиция N на M частей»); ошибка записи
    # истории не должна ронять уже прошедшую валидацию операцию (см. try/except
    # у admin_override-ветки patch_purchase_item выше).
    try:
        from app.models.entity_change import EntityChange as _EC
        _parts_desc = "; ".join(
            f"#{ci.id}: {q} шт / {t} ₽" for ci, q, t in zip(created_items, quantities, part_totals)
        )
        db.add(_EC(
            entity_type='purchase_item', entity_id=item_id, field_name='split',
            old_value=f"1 позиция «{_src_item_name}»: {original_qty} шт / {original_total} ₽",
            new_value=f"разбита на {n} частей — {_parts_desc}",
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
        ))
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed for purchase_item split: %s", _exc)

    await db.commit()
    for ci in created_items:
        await db.refresh(ci)

    return {
        "ok": True,
        "item_ids": [ci.id for ci in created_items],
        "parts": [
            {
                "item_id": ci.id,
                "quantity": float(ci.quantity or 0),
                "total_price": float(ci.total_price or 0),
                "feo_category_id": ci.feo_category_id,
                "feo_planned_item_id": ci.feo_planned_item_id,
            }
            for ci in created_items
        ],
        "contract_item_ids": new_contract_ids,
    }


@router.delete("/{pid}/items/{item_id}")
async def delete_purchase_item(
    pid: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Удаление одной позиции закупки с пересчётом сумм."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    # W3: позиция привязана к заявке — удалять только через заявку
    if p is not None and p.wish_id is not None:
        raise HTTPException(
            409,
            f"Позиция привязана к заявке #{p.wish_id} — редактируйте её в заявке",
        )
    await db.delete(it)
    await db.flush()
    if p:
        await _recalc_purchase_totals(p, db)
    if p and p.subsidy_id:
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение позиций закупки #{p.purchase_number or p.id}")
    await db.commit()
    return {"ok": True, "deleted_item_id": item_id}
