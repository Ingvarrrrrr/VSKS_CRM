"""Перенос заявки в План закупок и обратно: создание/синхронизация закупок из
позиций заявки, откат из плана, сброс цепочки согласования.

Вынесено из app/routers/wishes.py (Правило №5, модульность; сессия 2026-09-06,
разрезание wishes.py по образцу purchases.py → purchase_ops.py/purchase_*.py)
БЕЗ ИЗМЕНЕНИЯ ПОВЕДЕНИЯ. Это САМЫЙ частый путь, которым ТЗ заявки становится
закупкой — используется из wishes.py (approve_wish/force_wish_status/update_wish/
delete_wish), wish_transitions.py, wish_convert.py, wish_approvals.py (decide) и
app/services/wish_advance_conversion.py.

Сервис НЕ импортирует роутеры на уровне модуля — app/routers/wishes.py
импортирует ИЗ этого файла (_withdraw_wish_from_plan/_reset_approvals/
_distribute_wish_to_purchases) на уровне модуля, поэтому обратный импорт здесь
завёл бы цикл. Хелперы ядра (_is_meaningful_item/_ensure_feo_categories_assigned/
_ensure_needed_dates/_eff_date/_wish_linked_purchases) импортируются ЛЕНИВО
внутри функций — тем же приёмом, каким сам wishes.py лениво тянет
purchases.py/purchase_export.py/purchase_budget.py во избежание цикла
роутер↔роутер.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_event import PurchaseMember
from app.models.feo_category import FeoCategory
from app.routers.purchase_members import _create_assignment_chat_room
from app.services.feo_plan import assert_tz_not_over_plan, compute_feo_plan_tree
# Владелец (2026-09-02): превышение ТЗ над её КОНКРЕТНОЙ плановой позицией на
# пути «заявка согласуется → закупка создаётся» больше не 409 — вместо отказа
# регистрируется запрос на согласование (см. докстринг модуля, ПОЧЕМУ это не
# правка feo_plan.py и не второй параллельный механизм превышения).
from app.services.tz_excess_approval import collect_tz_over_plan_violations, register_tz_excess_approvals
# _auto_assign_planned_items вынесена в app.services.plan_autoassign (владелец,
# 2026-08-12, «закупка сама становится планом»): нужна ТАКЖЕ из purchases.py для
# закупок, созданных/меняемых в обход заявки. Поведение НЕ менялось при переносе —
# см. полный докстринг в app/services/plan_autoassign.py::auto_assign_planned_items.
# Alias сохраняет имя со старым подчёркиванием — все вызовы ниже по файлу не тронуты.
from app.services.plan_autoassign import (
    auto_assign_planned_items as _auto_assign_planned_items,
    backfill_item_type_from_plan as _backfill_item_type_from_plan,
)


async def _sync_purchase_from_wish(wish, purchases: list, db: AsyncSession) -> Optional[dict]:
    """Повторное согласование заявки (вернули в черновик/отклонили → поправили →
    согласовали заново) приводит УЖЕ СУЩЕСТВУЮЩУЮ закупку заявки к её текущему
    состоянию — предмет и состав позиций (владелец, план crystalline-soaring-
    heron.md, п.2). Прод-находка: РЕЕ-2026-00898 сохранила предмет заявки №40 на
    момент ПЕРВОГО переноса, хотя заявку потом правили (в т.ч. предмет) и
    согласовывали заново — `_distribute_wish_to_purchases` в ветке «защита от
    дублей» раньше только продвигала статус скрытой закупки, ничего не сверяя.

    Вызывается из `_distribute_wish_to_purchases`/`convert_wish` ТОЛЬКО когда у
    заявки уже есть закупка(и) — по построению это повторный проход. Правка
    wish.items вне пути «вернуть в черновик» заблокирована на статусе 'converted'
    (см. гейт в update_wish), так что к моменту вызова любое расхождение состава —
    легитимная правка, сделанная, пока заявка была НЕ converted; правило «после
    согласования правят в закупке» этим не нарушается.

    len(purchases) != 1 — заявка когда-то распределена канбаном на НЕСКОЛЬКО
    закупок (split=True, approve_distribution) — без сохранённого сопоставления
    «группа → закупка» синхронизация неоднозначна, поэтому не выполняется вовсе
    (возвращает None, поведение как до этой задачи). Обычное согласование
    (split=False) — всегда ОДНА закупка, это подавляющее большинство случаев,
    включая описанный на проде.

    Гейт по стадии — тот же принцип и те же тексты, что `_withdraw_wish_from_plan`
    выше: закупка ушла дальше «Плана закупок» (TZ_FROZEN_STATUSES) — состав и
    предмет НЕ трогаются, причина возвращается в `blocked_reason` с номером и
    стадией по-русски (не HTTPException — согласование заявки уже состоялось,
    отказывать в нём из-за стадии закупки владелец не просил).

    Возвращает контракт `purchase_sync` (см. план, зафиксирован для фронта):
    {purchase_id, registry_number, subject_before, subject_after, items_added,
    items_removed, items_changed, items_conflicted, items_kept_manual,
    blocked_reason}. None — нечего/некого синхронизировать (0 или 2+ закупок).
    Commit НЕ делает — это на вызывающем (как и весь _distribute_wish_to_purchases).
    """
    if len(purchases) != 1:
        return None
    from app.routers.purchases import TZ_FROZEN_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS
    # Ленивый импорт (во избежание цикла роутер↔сервис, см. докстринг модуля):
    # _is_meaningful_item/_ensure_feo_categories_assigned/_ensure_needed_dates/
    # _eff_date живут в ядре app/routers/wishes.py.
    from app.routers.wishes import (
        _is_meaningful_item,
        _ensure_feo_categories_assigned,
        _ensure_needed_dates,
        _eff_date,
    )

    p = purchases[0]

    if p.status in TZ_FROZEN_STATUSES:
        label = _STATUS_LABELS.get(p.status, p.status)
        return {
            "purchase_id": p.id,
            "registry_number": p.registry_number,
            "subject_before": p.subject,
            "subject_after": p.subject,
            "items_added": [],
            "items_removed": [],
            "items_changed": [],
            "items_conflicted": [],
            "items_kept_manual": [],
            "blocked_reason": (
                f"Закупка №{p.purchase_number or p.id} «{p.subject or p.item_name or ''}» "
                f"уже на стадии «{label}» — обновить предмет и состав из заявки нельзя. "
                "Дальнейшие изменения вносите прямо в закупке."
            ),
        }

    items_res = await db.execute(select(WishItem).where(WishItem.wish_id == wish.id))
    _all_wish_items = items_res.scalars().all()
    wish_items = [it for it in _all_wish_items if _is_meaningful_item(it)]
    # Дефект 2 (QA): ВСЕ id позиций заявки (включая «незначимые» — пустые
    # заготовки), не только meaningful — по ним отличаем «строка когда-то
    # пришла из заявки» от «заведена вручную прямо в закупке» ниже.
    _all_wish_item_ids = {it.id for it in _all_wish_items}

    # Те же гейты, что при первом переносе (_distribute_wish_to_purchases ниже) —
    # новая/изменившаяся позиция обязана иметь категорию ФЭО и дату потребности
    # прежде чем попасть в закупку.
    await _ensure_feo_categories_assigned(wish, wish_items, db)
    await _ensure_needed_dates(wish, db, wish_items)
    await _auto_assign_planned_items(
        wish_items, wish.feo_category_id, db, note=f"повторным согласованием заявки №{wish.id}",
    )
    # Владелец (2026-09-02): ТЗ дороже своей плановой позиции больше НЕ 409 здесь —
    # согласование заявки не блокируется, превышение регистрируется как запрос на
    # согласование уполномоченным (см. app.services.tz_excess_approval и вызывающий
    # код ниже — _distribute_wish_to_purchases/convert_wish регистрируют запрос
    # ПОСЛЕ этого вызова, используя _tz_excess_violations_sync, ту же схему, что
    # у purchase_sync/excess_warnings). Собранное здесь — НЕ бросает, только копит.
    wish._tz_excess_violations_sync = await collect_tz_over_plan_violations(
        db, wish_items, fallback_category_id=wish.feo_category_id,
    )

    pitems_res = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )
    existing_items = pitems_res.scalars().all()

    # Дефект 1 (QA, 2026-08-21): сопоставление «старая позиция закупки → текущая
    # позиция заявки» ДВУХСТУПЕНЧАТО. Ступень 1 — по жёсткой связи wish_item_id
    # (переживает переименование позиции в НЕ-draft статусах заявки — update_wish
    # правит WishItem по id in-place там, см. докстринг функции выше). Ступень 2 —
    # по нормализованному имени (app.services.text_match.normalize, та же
    # функция, что и в plan_autoassign.auto_assign_planned_items) — ТОЛЬКО для
    # позиций закупки, не разобранных на ступени 1 (правка в статусе 'draft' идёт
    # «удалить все WishItem → создать заново» — id теряются целиком, имя остаётся
    # единственным якорем). Без ступени 1 переименование позиции читалось как
    # «удалить строку закупки → создать новую» и стирало ручные поля закупки
    # (contractor_id/contractor_name/contractor_inn/receipt_id/match_confirmed/
    # final_unit_price и пр.) — тот самый дефект.
    from app.services.text_match import normalize as _normalize_name

    _existing_by_wid: dict[int, PurchaseItem] = {}
    _unmatched_existing: list[PurchaseItem] = []
    for pi in existing_items:
        if pi.wish_item_id is not None and pi.wish_item_id in _all_wish_item_ids:
            _existing_by_wid[pi.wish_item_id] = pi
        else:
            _unmatched_existing.append(pi)

    _existing_pool: dict[str, list[PurchaseItem]] = {}
    for pi in _unmatched_existing:
        key = _normalize_name(pi.item_name or "")
        _existing_pool.setdefault(key, []).append(pi)

    _wish_contractor_obj = None
    if getattr(wish, 'contractor_id', None):
        from app.models.contractor import Contractor as _Contractor
        _wish_contractor_obj = await db.get(_Contractor, wish.contractor_id)

    items_added: list[dict] = []
    items_removed: list[dict] = []
    items_changed: list[dict] = []
    items_conflicted: list[dict] = []
    items_kept_manual: list[dict] = []
    synced_items: list[PurchaseItem] = []

    def _fmt(qty, price, total) -> str:
        return f"{qty or 0} × {price or 0} ₽ = {float(total or 0):.2f} ₽"

    # Дефект 3 (QA): поля с сохранённым «снимком ТЗ на момент переноса» —
    # planned_* движется вместе с текущим значением ТОЛЬКО пока его не трогали
    # руками в закупке (правило проекта «после согласования правят в закупке»).
    # Признак ручной правки — текущее значение отличается от снимка; тогда поле
    # НЕ перезаписывается из заявки (ни значение, ни сам снимок), а расхождение
    # возвращается в items_conflicted, чтобы фронт показал его человеку вместо
    # молчаливого отката.
    _tracked_fields = (
        ("quantity", "planned_quantity"),
        ("unit_price", "planned_unit_price"),
        ("total_price", "planned_total"),
    )

    for wi in wish_items:
        pi = _existing_by_wid.pop(wi.id, None)
        if pi is None:
            _key = _normalize_name(wi.item_name or "")
            _bucket = _existing_pool.get(_key)
            pi = _bucket.pop(0) if _bucket else None
        if pi is None:
            new_pi = PurchaseItem(
                purchase_id=p.id,
                product_id=wi.product_id,
                item_name=wi.item_name,
                item_type=wi.item_type,
                quantity=wi.quantity,
                unit=wi.unit,
                unit_price=wi.unit_price,
                total_price=wi.total_price,
                planned_quantity=wi.quantity,
                planned_unit_price=wi.unit_price,
                planned_total=wi.total_price,
                country_origin=wi.country_origin,
                feo_category_id=wi.feo_category_id,
                feo_planned_item_id=wi.feo_planned_item_id,
                over_plan=getattr(wi, 'over_plan', False),
                needed_date=_eff_date(wish, wi),
                wish_item_id=wi.id,
                vat_rate=getattr(wi, 'vat_rate', None),
                contractor_id=(_wish_contractor_obj.id if _wish_contractor_obj else None),
                contractor_inn=(_wish_contractor_obj.inn if _wish_contractor_obj else None),
                contractor_name=(
                    _wish_contractor_obj.name if _wish_contractor_obj
                    else getattr(wish, 'contractor_name', None)
                ),
            )
            db.add(new_pi)
            synced_items.append(new_pi)
            items_added.append({
                "name": wi.item_name, "quantity": float(wi.quantity or 0), "amount": float(wi.total_price or 0),
            })
            continue

        _before_qty, _before_price, _before_total = pi.quantity, pi.unit_price, pi.total_price
        _name_changed = (pi.item_name or "") != (wi.item_name or "")

        _any_field_changed = _name_changed
        for field, snap_field in _tracked_fields:
            cur_val = float(getattr(pi, field) or 0)
            snap_val = float(getattr(pi, snap_field) or 0)
            wish_val = float(getattr(wi, field) or 0)
            _manually_edited = abs(cur_val - snap_val) > 0.005
            if _manually_edited:
                if abs(cur_val - wish_val) > 0.005:
                    items_conflicted.append({
                        "name": wi.item_name, "field": field,
                        "in_purchase": cur_val, "in_wish": wish_val,
                    })
                # Не трогаем ни значение, ни снимок — ручная правка остаётся как есть.
                continue
            if abs(cur_val - wish_val) > 0.005:
                _any_field_changed = True
            setattr(pi, field, getattr(wi, field))
            setattr(pi, snap_field, getattr(wi, field))

        if _any_field_changed:
            items_changed.append({
                "name": wi.item_name,
                "was": _fmt(_before_qty, _before_price, _before_total),
                "now": _fmt(pi.quantity, pi.unit_price, pi.total_price),
            })
        pi.item_name = wi.item_name
        pi.item_type = wi.item_type or pi.item_type
        pi.unit = wi.unit
        pi.country_origin = wi.country_origin
        pi.feo_category_id = wi.feo_category_id
        pi.feo_planned_item_id = wi.feo_planned_item_id
        pi.over_plan = getattr(wi, 'over_plan', False)
        pi.vat_rate = getattr(wi, 'vat_rate', None)
        pi.needed_date = _eff_date(wish, wi)
        # Ре-линковка (см. комментарий у _existing_by_wid/_existing_pool выше):
        # правка в 'draft' пересоздаёт WishItem с новым id — восстанавливаем hard
        # link на АКТУАЛЬНЫЙ id, иначе связь «заявка ↔ строка закупки» (W1,
        # используется W-diff/exclude_wish_id/_fpi_reference_keys) обрывается
        # молча при первом же возврате в черновик, даже когда содержимое позиции
        # не менялось.
        pi.wish_item_id = wi.id
        synced_items.append(pi)

    # Дефект 2 (QA): позиции закупки, оставшиеся непарными, удаляются ТОЛЬКО
    # если реально пришли из заявки (wish_item_id указывает на позицию ЭТОЙ
    # заявки — включая «незначимые», см. _all_wish_item_ids выше — просто её
    # больше нет среди текущих значимых позиций заявки, автор убрал/обнулил её).
    # Строки, заведённые закупщиком прямо в закупке (wish_item_id пуст или
    # указывает не на эту заявку), НИКОГДА не трогаются — они возвращаются
    # отдельным списком items_kept_manual, чтобы пользователь видел, что они
    # остались, а не решил, что их «забыли».
    # _existing_by_wid, оставшийся непустым после основного цикла (см. .pop()
    # там) — записи, чей wish_item_id указывает на РЕАЛЬНУЮ позицию этой заявки,
    # но она перестала быть «значимой» (обнулена) и в wish_items не попала;
    # по тому же правилу это тоже «пришла из заявки» → в общий проход удаления.
    _leftover_buckets = list(_existing_pool.values()) + [[pi] for pi in _existing_by_wid.values()]
    for _bucket in _leftover_buckets:
        for pi in _bucket:
            if pi.wish_item_id is not None and pi.wish_item_id in _all_wish_item_ids:
                items_removed.append({
                    "name": pi.item_name, "quantity": float(pi.quantity or 0), "amount": float(pi.total_price or 0),
                })
                await db.delete(pi)
            else:
                items_kept_manual.append({
                    "name": pi.item_name, "quantity": float(pi.quantity or 0), "amount": float(pi.total_price or 0),
                })

    if synced_items:
        await _backfill_item_type_from_plan(synced_items, db)

    _subject_before = p.subject
    title = (wish.title or "").strip() or f"Заявка #{wish.id}"
    p.subject = title
    p.item_name = title
    if getattr(wish, 'contractor_id', None) and not p.contractor_id:
        p.contractor_id = wish.contractor_id

    await db.flush()

    # ПРАВИЛО №6 (2026-09-05): единственный писатель денежных колонок — p
    # гарантированно не заморожена (ранний return выше по TZ_FROZEN_STATUSES),
    # см. purchase_money_writer.py.
    from app.services.purchase_money_writer import recalc_purchase_money
    await recalc_purchase_money(db, p)
    await db.flush()

    return {
        "purchase_id": p.id,
        "registry_number": p.registry_number,
        "subject_before": _subject_before,
        "subject_after": p.subject,
        "items_added": items_added,
        "items_removed": items_removed,
        "items_changed": items_changed,
        "items_conflicted": items_conflicted,
        "items_kept_manual": items_kept_manual,
        "blocked_reason": None,
    }


async def _distribute_wish_to_purchases(wish, db, current_user, purchase_status: str = "plan_schedule", split: bool = True) -> list[int]:
    """Создаёт закупки (status='plan_schedule' — «План закупок») из позиций заявки по группам колонок,
    копирует позиции, добавляет участников и чаты, ставит purchase.wish_id.
    split=False (быстрое одобрение / полное согласование цепочкой): одна закупка со ВСЕМИ позициями,
    без разбиения по категориям — разбиение только при явном распределении через канбан.
    Возвращает список id созданных закупок. Транзакцию/commit НЕ делает — это на вызывающем.
    Защита от дублей: если по заявке уже есть закупки (purchases.wish_id == wish.id) — НИЧЕГО не создаёт и возвращает их id."""
    from sqlalchemy.orm import selectinload as sil
    from app.models.product import Product
    # Ленивый импорт (во избежание цикла роутер↔сервис, см. докстринг модуля):
    # хелперы ядра app/routers/wishes.py.
    from app.routers.wishes import (
        _is_meaningful_item,
        _ensure_feo_categories_assigned,
        _ensure_needed_dates,
        _eff_date,
    )

    # Защита от дублей: если по заявке уже есть закупки — ничего не создаём,
    # но скрытые до одобрения (status='wishes') продвигаем в целевой статус
    existing = (await db.execute(
        select(Purchase).where(Purchase.wish_id == wish.id)
    )).scalars().all()
    if existing:
        # Авансовый: статус не меняем — закупка живёт в своём статусе независимо.
        # Purchase создаётся РАНЬШЕ самой заявки (purchases.py, ветка is_advance) —
        # обычный путь копирования WishItem → PurchaseItem сюда не доходит, поэтому
        # инвариант «закупки вне плана не бывает» (шаг 3, владелец 2026-08-07)
        # применяем здесь напрямую к PurchaseItem закупки, иначе авансовые отчёты
        # остались бы вне плана навсегда.
        if getattr(wish, 'source', None) == 'advance_report':
            adv_items_res = await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id.in_([p.id for p in existing]))
            )
            adv_items = adv_items_res.scalars().all()
            if adv_items:
                await _auto_assign_planned_items(
                    adv_items, wish.feo_category_id, db,
                    note=f"авансовым отчётом (заявка №{wish.id})",
                )
                await db.flush()
            return [p.id for p in existing]
        # W2-гейт: проверяем даты и категорию ФЭО ПЕРЕД продвижением скрытых закупок
        # в целевой статус — это тоже момент «попадания в План закупок» (владелец,
        # 2026-08-11): скрытые (status='wishes') закупки ещё не в плане.
        wishes_purchases = [p for p in existing if p.status == "wishes"]
        if wishes_purchases:
            items_res = await db.execute(select(WishItem).where(WishItem.wish_id == wish.id))
            items_for_gate = [it for it in items_res.scalars().all() if _is_meaningful_item(it)]
            await _ensure_feo_categories_assigned(wish, items_for_gate, db)
            await _ensure_needed_dates(wish, db, items_for_gate)
        for p in existing:
            if p.status == "wishes":
                p.status = purchase_status
        # Владелец (план crystalline-soaring-heron.md, п.2, 2026-08-21): «после
        # согласования заявку правят в закупке, а не в заявке» — верно, ПОКА
        # заявка остаётся converted (правка wish.items на этом статусе заблокирована,
        # см. гейт в update_wish). Но владелец наблюдал ОБРАТНОЕ на проде: заявку
        # ВОЗВРАЩАЛИ в черновик (там правка снова разрешена), меняли предмет и
        # состав, согласовывали ЗАНОВО — а закупка (РЕЕ-2026-00898) осталась со
        # старым предметом, потому что раньше эта ветка (существующая закупка —
        # "защита от дублей" сработала) молчала: только продвигала статус, ничего
        # не сверяла. Единственный путь СЮДА с изменившимися items — именно
        # «вернули в черновик → поправили → согласовали заново» (иначе items не
        # изменить), так что синхронизация здесь НЕ нарушает правило «после
        # согласования — только в закупке»: она реагирует именно на легитимную
        # правку, сделанную, пока заявка была НЕ converted.
        wish._purchase_sync = await _sync_purchase_from_wish(wish, existing, db)
        wish._tz_excess_approvals = await register_tz_excess_approvals(
            db, getattr(wish, "_tz_excess_violations_sync", []) or [],
            subsidy_id=wish.subsidy_id, current_user=current_user,
            context_label=f"повторное согласование заявки №{wish.id}",
        )
        return [p.id for p in existing]

    # Preload wish items with products for category resolution
    res = await db.execute(
        select(WishItem)
        .options(sil(WishItem.product))
        .where(WishItem.wish_id == wish.id)
    )
    items_full = res.scalars().all()

    # Задача 3: строки-заготовки (без названия и без сумм/количества) — фронт
    # создаёт их заранее для будущего ввода — не должны попадать в План закупок.
    items_full = [it for it in items_full if _is_meaningful_item(it)]

    # Гейт ФЭО (владелец, 2026-08-11): позиция без категории (или со ссылкой на
    # удалённую из справочника) не должна попасть в План закупок — раньше эта же
    # ветка молча обнуляла битую ссылку и создавала закупку без ФЭО (предупреждением
    # postfactum через wish._convert_warning). Именно так реальная заявка №32
    # «Приобретение Пикапов» лишилась категории, а созданная из неё закупка
    # осталась сиротой вне всех планов ФЭО. См. docstring _ensure_feo_categories_assigned.
    await _ensure_feo_categories_assigned(wish, items_full, db)

    # Backfill product_id + category by item_name for legacy wish_items
    # (created before product_id was persisted on wish_items).
    missing = [it for it in items_full if not it.product_id and (it.item_name or "").strip()]
    name_to_product: dict[str, Product] = {}
    if missing:
        names = list({(it.item_name or "").strip() for it in missing})
        pres = await db.execute(select(Product).where(Product.name.in_(names)))
        for p in pres.scalars().all():
            name_to_product[(p.name or "").strip().lower()] = p
        for it in missing:
            hit = name_to_product.get((it.item_name or "").strip().lower())
            if hit:
                it.product_id = hit.id

    def _resolve_key(it: WishItem) -> str:
        """target_column_key → product.category → name-matched product.category → '__uncategorized__'"""
        if it.target_column_key:
            return it.target_column_key
        if it.product_id and it.product and it.product.category:
            return it.product.category
        hit = name_to_product.get((it.item_name or "").strip().lower())
        if hit and hit.category:
            return hit.category
        return "__uncategorized__"

    groups: dict[str, list] = {}
    if split:
        for it in items_full:
            groups.setdefault(_resolve_key(it), []).append(it)
    elif items_full:
        groups["__all__"] = list(items_full)

    if not groups:
        raise HTTPException(status_code=400, detail="Нет позиций для распределения")

    # W2: Гейт обязательности дат потребности при переносе в План закупок.
    # Авансовые пропускаются (тот же принцип, что и в submit_wish/update_wish,
    # см. их комментарии «W2: проверяем плановые даты (авансовые пропускаем)») —
    # раньше эта функция сюда доходила ТОЛЬКО для НЕ-авансовых заявок (авансовый
    # авто-companion всегда имел готовую закупку и уходил в ветку «existing» выше
    # до этой строки); реформация заявки в авансовый отчёт (services/wish_advance_conversion.py)
    # — первый путь, где source == 'advance_report' реально доходит досюда без
    # существующей закупки, и без этого исключения ловил бы гейт, которого для
    # авансовых отчётов нигде больше нет.
    if getattr(wish, 'source', None) != 'advance_report':
        await _ensure_needed_dates(wish, db, items_full)

    # Инвариант «закупки вне плана не бывает» (владелец, 2026-08-07, план
    # zany-fluttering-mountain.md шаг 3): раньше автозаведение плановой позиции
    # срабатывало ТОЛЬКО для over_plan=true — обычная позиция без привязки
    # молча «съедала» план листа, не будучи привязанной ни к какой FeoPlannedItem
    # (отсюда осиротевшие строки в дереве ФЭО). Теперь — КАЖДАЯ позиция без явной
    # привязки (feo_planned_item_id ещё не проставлен — ни автоподбором, ни
    # пользователем) при переносе в План закупок порождает НОВУЮ FeoPlannedItem
    # (или находит существующую по точному совпадению имени — дедуп ниже) и
    # привязывается к ней; над_плановая надбавка (over_plan) сбрасывается — сама
    # позиция становится обычной плановой. Явный выбор пользователя (уже
    # проставленный feo_planned_item_id, в т.ч. подтверждённый матчинг) НЕ
    # перебивается — эти позиции сюда не попадают.
    # Дедуп по (категория, нормализованное имя trim+lower) — как в импорте Excel Ур.5
    # (feo_categories.py), но с нормализацией, т.к. источник — свободный ввод в заявке.
    # Эта ветка недостижима при повторном согласовании: закупки уже существуют, и
    # выполнение уходит в ветку `if existing:` выше, до сюда не доходя (идемпотентность).
    await _auto_assign_planned_items(
        items_full, wish.feo_category_id, db, note=f"заявкой №{wish.id}",
    )

    # Шаг 5 «ТЗ не выше плана» (владелец, 2026-08-07, план zany-fluttering-mountain.md):
    # _distribute_wish_to_purchases — это общий путь создания закупок из заявки
    # (approve_wish, force_wish_status('converted'), сам convert_wish воспроизводит
    # тот же порядок отдельно, см. его код), т.е. САМОЕ частое место, где ТЗ
    # превращается в закупку. Раньше здесь проверялось только превышение бюджета
    # ФЭО (assert_no_unapproved_excess ниже) — позиция дороже своей плановой строки
    # проходила без единого отказа. Порядок трёх шагов ОБЯЗАТЕЛЕН и именно такой:
    #   1) автозаведение (_auto_assign_planned_items выше) — ДО проверки цены,
    #      иначе у большинства позиций feo_planned_item_id ещё пуст и проверять
    #      не с чем (assert_tz_not_over_plan — no-op без плана, любая цена прошла бы);
    #   2) «ТЗ не выше плана» (здесь) — точечная причина отказа по КОНКРЕТНОЙ
    #      позиции (кол-во/цена/сумма), самая частная и понятная формулировка;
    #   3) превышение ФЭО (assert_no_unapproved_excess ниже) — по КАТЕГОРИИ
    #      целиком, уже ПОСЛЕ того как автозаведение нарастило план категории
    #      всеми новыми позициями; это самая общая причина отказа, ей место
    #      последней, чтобы пользователь сначала увидел, какая именно позиция
    #      виновата, а не абстрактное «превышен бюджет категории».
    # over_plan=true — сознательно сверх плана (тот же обход, что и в
    # _sync_wish_items_to_purchases/update_wish/purchases.py) — пропускаем.
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): позиции, привязанные
    # к ОДНОЙ и той же плановой позиции, накапливаются в пределах ЭТОЙ заявки
    # (та же группировка, что у assert_tz_batch_not_over_plan) — иначе две строки
    # в сумме превышают план, каждая проходя поодиночке.
    # Владелец (2026-09-02): больше НЕ 409 здесь — «это же заявка согласуется, это
    # согласуется её необходимость... финансист видит, что люди просят, и решает».
    # Собираем нарушения (не бросаем), регистрируем запрос на согласование ПОСЛЕ
    # фактического создания закупок ниже (см. wish._tz_excess_approvals) — тот же
    # порядок, что и у excess_warnings (см. _collect_excess_warnings).
    _tz_violations = await collect_tz_over_plan_violations(
        db, items_full, fallback_category_id=wish.feo_category_id,
    )

    # Владелец (2026-08-12): «Когда заявка идёт с превышением, ... она должна
    # уходить [в закупку], но на закупке должен быть значок, что она заблокирована
    # из-за превышения. Должна быть возможность передвижки, уменьшения». Раньше
    # здесь стоял assert_no_unapproved_excess — согласование заявки, создающее
    # закупки целиком отказывало 409, пока превышение (в т.ч. на ПРЕДКЕ категории)
    # не согласовано или не убрано, и никакого способа перенести/уменьшить позиции
    # ПОСЛЕ создания закупки не было. Теперь action не блокируется — вместо этого
    # ниже, ПОСЛЕ фактического создания закупок (когда план уже вырос), собираем
    # excess_warnings по каждой затронутой категории ФЭО (и её предкам) — см.
    # _collect_excess_warnings. Здесь только группируем позиции по листовой
    # категории (per-item feo_category_id, fallback — категория заявки целиком).
    _cat_items: dict[int, list[dict]] = {}
    for _wi in items_full:
        _cid = _wi.feo_category_id or wish.feo_category_id
        if _cid:
            _cat_items.setdefault(_cid, []).append({
                "name": _wi.item_name, "amount": float(_wi.total_price or 0),
            })

    # Контрагент заявки (владелец, 2026-08-17) — резолвим один раз на всю
    # конвертацию (не per-группу), чтобы название контрагента попало и в
    # PurchaseItem.contractor_name каждой позиции (mirrors purchases.py PUT,
    # см. её докстринг «Phase 26-Z» — тот же паттерн проставления контрагента
    # позициям без своего). Только заполняем — сами позиции только что созданы,
    # перетирать нечего.
    _wish_contractor_obj = None
    if getattr(wish, 'contractor_id', None):
        from app.models.contractor import Contractor as _Contractor
        _wish_contractor_obj = await db.get(_Contractor, wish.contractor_id)

    created_purchase_ids: list[int] = []
    for column_key, items_in_col in groups.items():
        total_nmck = sum(float(i.total_price or 0) for i in items_in_col)
        display_key = "Не определено" if column_key == "__uncategorized__" else column_key
        title = (wish.title or "").strip() or f"Заявка #{wish.id}"
        subject = title if column_key == "__all__" else f"{title} — {display_key}"
        total_qty_grp = sum(float(i.quantity or 0) for i in items_in_col)

        # W2: шапочная delivery_date — если все позиции группы имеют одну дату
        effective_dates = {_eff_date(wish, wi) for wi in items_in_col}
        effective_dates.discard(None)
        group_delivery_date = effective_dates.pop() if len(effective_dates) == 1 else None

        # C1: авансовый отчёт → фиксируем тип; обычная заявка → single
        _is_advance_wish = (getattr(wish, 'source', None) == 'advance_report')
        _purchase_method = 'advance' if _is_advance_wish else 'single'
        _payment_basis_type = 'advance_report' if _is_advance_wish else None
        p = Purchase(
            wish_id=wish.id,
            subsidy_id=wish.subsidy_id,
            feo_category_id=wish.feo_category_id,
            event_id=getattr(wish, 'event_id', None),  # «Мероприятие»
            item_name=title,
            subject=subject,
            planned_quantity=total_qty_grp or wish.quantity,
            planned_total_price=total_nmck,
            total_nmck=total_nmck,
            nmck=total_nmck,
            status=purchase_status,
            # B1: исполнитель = executor_id (без фолбэка на инициатора)
            assigned_user_id=getattr(wish, 'executor_id', None),
            # B1: служебка «на чьё имя» = assigned_to заявки
            service_note_to_user_id=wish.assigned_to,
            execution_term=getattr(wish, 'execution_deadline', None),  # B-exec
            service_note_text=wish.justification,
            service_note_by=wish.created_by,
            delivery_date=group_delivery_date,  # W2: единая дата для группы
            purchase_method=_purchase_method,
            payment_basis_type=_payment_basis_type,
            feo_per_item=bool(getattr(wish, 'feo_per_item', False)),
            vat_mode=(getattr(wish, 'vat_mode', None) or 'uniform'),
            # Контрагент заявки (владелец, 2026-08-17) — переезжает в закупку,
            # если указан. Purchase свежесозданный (contractor_id ещё пуст) —
            # «не перетирать уже заданное» тут выполняется автоматически.
            contractor_id=getattr(wish, 'contractor_id', None),
        )
        db.add(p)
        await db.flush()  # get p.id
        created_purchase_ids.append(p.id)

        for wi in items_in_col:
            pi = PurchaseItem(
                purchase_id=p.id,
                product_id=wi.product_id,
                item_name=wi.item_name,
                item_type=wi.item_type,
                quantity=wi.quantity,
                unit=wi.unit,
                unit_price=wi.unit_price,
                total_price=wi.total_price,
                # Снимок плана (Шаг 1 «план ≠ факт»): зафиксировать ТЗ заявки как план
                # позиции ОТДЕЛЬНО от unit_price/total_price (которые дальше могут
                # мутировать при правке цены по итогам закупки) — дерево ФЭО обязано
                # читать planned_*, а не текущую unit_price/total_price.
                planned_quantity=wi.quantity,
                planned_unit_price=wi.unit_price,
                planned_total=wi.total_price,
                country_origin=wi.country_origin,
                feo_category_id=wi.feo_category_id,  # B9: per-item feo
                feo_planned_item_id=wi.feo_planned_item_id,  # расходуем уже запланированную позицию, не задваиваем план
                over_plan=getattr(wi, 'over_plan', False),
                needed_date=_eff_date(wish, wi),  # W2: наследование эффективной даты
                wish_item_id=wi.id,  # W1: hard link to source WishItem
                vat_rate=getattr(wi, 'vat_rate', None),
                # Контрагент заявки — на каждую позицию (см. резолв _wish_contractor_obj
                # выше). Если контрагента в справочнике ещё нет — свободный ввод
                # contractor_name (второе поле у Wish, ровно для этого случая).
                contractor_id=(_wish_contractor_obj.id if _wish_contractor_obj else None),
                contractor_inn=(_wish_contractor_obj.inn if _wish_contractor_obj else None),
                contractor_name=(
                    _wish_contractor_obj.name if _wish_contractor_obj
                    else getattr(wish, 'contractor_name', None)
                ),
            )
            db.add(pi)
        await db.flush()

        # ПРАВИЛО №6 (2026-09-06): единственный писатель денежных колонок —
        # planned_total_price/total_nmck/nmck выше уже посчитаны как Σ items_in_col
        # (та же арифметика, что recalc_purchase_money даст из только что
        # вставленных PurchaseItem), но проведены МИМО писателя — прогоняем
        # через него, чтобы contract_price/будущие правила централизованно
        # применялись и здесь, а не только там, где это явно вызывалось раньше.
        from app.services.purchase_money_writer import recalc_purchase_money as _recalc_purchase_money_dwtp
        await _recalc_purchase_money_dwtp(db, p)

        # Add wish author as purchase member (viewer role) so they can see the purchase
        if wish.created_by and wish.created_by != current_user.id:
            db.add(PurchaseMember(
                purchase_id=p.id,
                user_id=wish.created_by,
                role="viewer",
                added_by_id=current_user.id,
                consent_pending=False,
            ))
        # Also add assigned_to as member if different from author and current_user
        if wish.assigned_to and wish.assigned_to not in (wish.created_by, current_user.id):
            db.add(PurchaseMember(
                purchase_id=p.id,
                user_id=wish.assigned_to,
                role="viewer",
                added_by_id=current_user.id,
                consent_pending=False,
            ))
        await db.flush()

        # Create chat room per purchase if there is an assignee different from current user
        if wish.assigned_to and wish.assigned_to != current_user.id:
            org_id = getattr(current_user, 'org_id', None) or wish.org_id
            await _create_assignment_chat_room(
                db, current_user.id, wish.assigned_to,
                org_id,
                f"Закупка: {p.subject}",
            )

    if created_purchase_ids and not wish.purchase_id:
        wish.purchase_id = created_purchase_ids[0]

    # После создания закупок (план уже вырос) — собрать предупреждения о
    # превышении вместо блокировки, см. комментарий у _cat_items выше.
    wish._excess_warnings = await _collect_excess_warnings(db, wish.subsidy_id, _cat_items)
    # Владелец (2026-09-02): регистрируем запрос(ы) на согласование превышения ТЗ
    # над плановой позицией (см. _tz_violations выше и app.services.tz_excess_approval) —
    # ПОСЛЕ создания закупок, чтобы список запросов был виден сразу в ответе API.
    wish._tz_excess_approvals = await register_tz_excess_approvals(
        db, _tz_violations, subsidy_id=wish.subsidy_id, current_user=current_user,
        context_label=f"согласование заявки №{wish.id}",
    )

    return created_purchase_ids


async def _collect_excess_warnings(
    db: AsyncSession, subsidy_id: Optional[int], cat_items: dict[int, list[dict]],
) -> list[dict]:
    """Владелец (2026-08-12): «Когда заявка идёт с превышением, ... она должна
    уходить [в закупку], но на закупке должен быть значок, что она заблокирована
    из-за превышения. Должна быть возможность передвижки, уменьшения» — согласование
    заявки больше НЕ блокируется несогласованным превышением плана ФЭО
    (assert_no_unapproved_excess убран из путей создания закупок из заявки, см.
    вызывающий код), а вместо отказа собирает ПРЕДУПРЕЖДЕНИЯ, по одному на каждую
    затронутую категорию ФЭО (включая ПРЕДКОВ — та же цепочка parent_id, что и в
    assert_no_unapproved_excess, но без исключения).

    cat_items — {feo_category_id (лист, куда попала позиция заявки): [{"name","amount"}, ...]}.
    Вызывать ПОСЛЕ того как закупки/позиции уже созданы и flush()-нуты (до
    commit) — иначе compute_feo_plan_tree не увидит новый план и excess будет
    занижен на сумму этого самого действия.

    Возвращает список (дубли по category_id схлопнуты):
      {"category_id", "category_name", "budget", "plan_after", "excess_amount", "items"}
    Пустой список, если превышения нет или category_ids/subsidy_id отсутствуют.
    """
    if not cat_items or not subsidy_id:
        return []
    tree = await compute_feo_plan_tree(db, [subsidy_id])
    if not tree:
        return []

    warnings_by_cat: dict[int, dict] = {}
    for leaf_cid, items in cat_items.items():
        if leaf_cid not in tree or not items:
            continue
        # Цепочка «узел → предки» через parent_id (снизу вверх) — как в
        # assert_no_unapproved_excess, но собираем предупреждения, а не бросаем 409.
        chain_ids: list[int] = []
        cur_id: Optional[int] = leaf_cid
        seen: set[int] = set()
        while cur_id is not None and cur_id not in seen and cur_id in tree:
            seen.add(cur_id)
            chain_ids.append(cur_id)
            cur_id = tree[cur_id]["parent_id"]
        for cid in chain_ids:
            node = tree[cid]
            excess = node.get("excess_over_feo") or node.get("excess_amount") or 0.0
            if excess <= 0.005 or node.get("excess_approved"):
                continue
            entry = warnings_by_cat.get(cid)
            if entry is None:
                cat_row = await db.get(FeoCategory, cid)
                entry = {
                    "category_id": cid,
                    "category_name": cat_row.name if cat_row else f"#{cid}",
                    "budget": node.get("budget"),
                    "plan_after": float((node.get("plan") or 0.0) + (node.get("over") or 0.0)),
                    "excess_amount": float(excess),
                    "items": [],
                }
                warnings_by_cat[cid] = entry
            entry["items"].extend(items)
    return list(warnings_by_cat.values())


async def _sync_wish_items_to_purchases(wish, db: AsyncSession) -> None:
    """УСТАРЕЛО, БОЛЬШЕ НЕ ВЫЗЫВАЕТСЯ (владелец, 2026-08-13): «после согласования
    заявку править нельзя, только в закупке» — единственный вызывающий код
    (_distribute_wish_to_purchases, ветка повторного одобрения уже
    конвертированной заявки) отключён, т.к. правка wish.items теперь
    запрещена на статусе 'converted' (см. гейт в update_wish). Оставлено в
    коде на случай будущего отката решения — НЕ удалять просто так.

    Синхронизирует позиции заявки в связанные закупки (не в TZ_FROZEN_STATUSES).

    Для каждой закупки НЕ в TZ_FROZEN_STATUSES: каждая PurchaseItem с wish_item_id
    находит соответствующий WishItem и копирует item_name/unit/unit_price/quantity/total_price.
    Затем пересчитывает суммы закупки.

    Асимметрия (владелец, 2026-08-07, план zany-fluttering-mountain.md, шаг 5):
    раньше здесь стоял CONTRACTED_STATUSES (contracted/ordered/delivered/paid) —
    на «Ведётся работа» (work_in_progress) правка заявки по-прежнему могла
    двигать цену/кол-во позиции закупки, хотя прямой PATCH той же позиции
    (purchases.py:patch_purchase_item) её уже замораживает по TZ_FROZEN_STATUSES.
    Заморозка ТЗ обходилась правкой заявки. Приведено к одному набору статусов —
    TZ_FROZEN_STATUSES (импорт из purchases.py, локально — во избежание цикла
    роутер↔роутер).
    """
    from app.routers.purchases import TZ_FROZEN_STATUSES as _TZ_FROZEN_STATUSES
    # Ленивый импорт (во избежание цикла роутер↔сервис, см. докстринг модуля).
    from app.routers.wishes import _wish_linked_purchases

    wish_item_map = {wi.id: wi for wi in (wish.items or [])}
    if not wish_item_map:
        return
    purchases = await _wish_linked_purchases(wish.id, db)
    for p in purchases:
        if p.status in _TZ_FROZEN_STATUSES:
            continue
        pitems_res = await db.execute(
            select(PurchaseItem).where(
                PurchaseItem.purchase_id == p.id,
                PurchaseItem.wish_item_id.isnot(None),
            )
        )
        pitems = pitems_res.scalars().all()
        changed = False
        for pi in pitems:
            wi = wish_item_map.get(pi.wish_item_id)
            if wi is None:
                continue
            _new_qty = wi.quantity
            _new_price = wi.unit_price
            _new_total = (wi.unit_price or 0) * (wi.quantity or 0)
            # Шаг 5 «цена ТЗ не выше плановой»: та же позиция, тот же гейт, что и
            # у прямого PATCH — правка через заявку не должна быть лазейкой.
            # over_plan=true — сознательно сверх плана, пропускаем (см. purchases.py).
            if not getattr(wi, 'over_plan', False):
                await assert_tz_not_over_plan(
                    db,
                    feo_planned_item_id=wi.feo_planned_item_id,
                    feo_category_id=wi.feo_category_id,
                    quantity=_new_qty,
                    unit_price=_new_price,
                    total_price=_new_total,
                    item_name=wi.item_name,
                )
            pi.item_name = wi.item_name
            pi.unit = wi.unit
            pi.unit_price = _new_price
            pi.quantity = _new_qty
            pi.total_price = _new_total
            # Снимок плана (Шаг 1): позиция ещё НЕ ушла из плана закупок (проверено
            # выше — p.status not in TZ_FROZEN_STATUSES), поэтому правка заявки
            # по-прежнему двигает и «текущую» цену, и зафиксированный план вместе —
            # план не заморожен, пока закупка не объявлена (Шаг 2).
            pi.planned_quantity = wi.quantity
            pi.planned_unit_price = wi.unit_price
            pi.planned_total = (wi.unit_price or 0) * (wi.quantity or 0)
            pi.feo_category_id = wi.feo_category_id
            pi.feo_planned_item_id = wi.feo_planned_item_id
            pi.over_plan = getattr(wi, 'over_plan', False)
            pi.vat_rate = getattr(wi, 'vat_rate', None)
            changed = True
        if changed:
            # Признак «Товар/Услуга/Работа» (блок 1): наследуется от плановой
            # позиции, если у самой позиции закупки он ещё не задан (уже
            # заполненный — не трогаем).
            await _backfill_item_type_from_plan(pitems, db)
            p.feo_per_item = bool(getattr(wish, 'feo_per_item', False))
            p.vat_mode = getattr(wish, 'vat_mode', None) or 'uniform'
            await db.flush()
            # ПРАВИЛО №6 (2026-09-05): пересчёт сумм закупки — единственный
            # писатель денежных колонок (см. purchase_money_writer.py). p уже
            # гарантированно не заморожена (проверка `p.status in
            # _TZ_FROZEN_STATUSES: continue` в начале цикла выше), сумму
            # передаём None — писатель сам посчитает Σ purchase_items.total_price.
            from app.services.purchase_money_writer import recalc_purchase_money
            await recalc_purchase_money(db, p)
            await db.flush()


async def _withdraw_wish_from_plan(wish_id: int, db: AsyncSession, *, action_text: str) -> None:
    """Убирает закупки заявки из плана закупок — обратная операция к
    _distribute_wish_to_purchases.

    Жёсткий гейт (владелец, 2026-08-07): если хоть одна связанная закупка ушла
    дальше «Плана закупок» (work_in_progress/contracted/ordered/delivered/paid),
    откат заявки ЗАПРЕЩЁН — HTTPException(409) с перечислением номеров, предметов
    и стадий. Проверка идёт ДО любых мутаций, поэтому при блокировке ни одна
    закупка заявки не трогается (частичного отката не бывает).
    Закупки, оставшиеся в 'plan_schedule' (и только они), возвращаются в скрытый
    статус 'wishes' — не удаляются: сохраняются история, файлы, чаты и связь
    с заявкой; при повторном одобрении гейт вернёт их в план.
    `action_text` — что именно не удаётся сделать («вернуть в черновик»,
    «отклонить», «удалить», ...) — подставляется в текст 409 вызывающей точкой,
    чтобы сообщение звучало по-русски для конкретного действия.
    Commit НЕ делает — это на вызывающем.
    """
    from app.routers.purchase_budget import PLANNED_STATUSES
    from app.routers.purchase_export import _STATUS_LABELS
    # Ленивый импорт (во избежание цикла роутер↔сервис, см. докстринг модуля).
    from app.routers.wishes import _wish_linked_purchases

    purchases = await _wish_linked_purchases(wish_id, db)
    blockers: list[str] = []
    for p in purchases:
        if p.status != "plan_schedule" and p.status in PLANNED_STATUSES:
            # work_in_progress/contracted/ordered/delivered/paid — стадия ушла дальше
            # «Плана закупок», откат запрещён.
            label = _STATUS_LABELS.get(p.status, p.status)
            blockers.append(f"№{p.purchase_number or p.id} «{p.item_name or ''}» на стадии «{label}»")
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Заявку нельзя {action_text}: закупка " + "; ".join(blockers)
                + ". Сначала отмените её в реестре закупок."
            ),
        )
    changed = False
    for p in purchases:
        if p.status == "plan_schedule":
            p.status = "wishes"
            changed = True
        # status == 'wishes' и прочие (например 'cancelled') — не трогаем
    if changed:
        await db.flush()


async def _reset_approvals(wish_id: int, db: AsyncSession, keep_user_id: Optional[int] = None) -> None:
    """Сбрасывает решения согласующих цепочки обратно в pending.

    keep_user_id (владелец, 2026-08-19: «нужно, чтобы было видно, кто
    отклонил») — строка ЭТОГО согласующего НЕ трогается: у него остаются
    status='rejected', decided_at, decided_by_user_id, comment, чтобы после
    сброса остальных было видно, кто именно отклонил заявку. Остальные — как
    раньше, в pending."""
    from app.models.wish_approval import WishApproval
    approvals = (await db.execute(
        select(WishApproval).where(WishApproval.wish_id == wish_id)
    )).scalars().all()
    for a in approvals:
        if keep_user_id is not None and a.user_id == keep_user_id:
            continue
        a.status = "pending"
        a.decided_at = None
        a.decided_by_user_id = None
        a.decided_by_username = None
        a.comment = None
    if approvals:
        await db.flush()
