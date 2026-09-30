"""Авансовый отчёт → авто-заявка (Wish source='advance_report').

Единственное место, где решается:
- какая форма договора ставится компаньону по умолчанию, когда у самой
  закупки contract_form не задан (поле скрыто на форме создания/правки для
  purchase_method='advance' — см. PurchaseContractParamsSection.vue,
  поэтому у авансовых закупок оно пустое почти всегда);
- как из PurchaseItemCreate-дампа (`item.model_dump()`) собрать kwargs для
  WishItem, включая привязку к плановой позиции (feo_planned_item_id/
  match_confirmed/over_plan) — раньше при копировании терялась, из-за чего
  компаньон показывал плашку «позиции не привязаны к плановой», хотя в самом
  авансовом всё привязано (жалоба владельца, заявка №88 / РЕЕ-2026-00962,
  2026-09-30).

Вызывается из routers/purchases.py в двух местах: create_purchase (первое
создание компаньона) и update_purchase (пересборка WishItems при правке уже
существующего авансового) — ПРАВИЛО №6, один источник вместо двух копий.
"""
from __future__ import annotations

from typing import Any


# Владелец: авансовые отчёты — россыпь разовых покупок (такси, канцтовары,
# ГСМ и т.п.), письменным рамочным договором никогда не оформляются. Из 9
# существующих форм (services/dictionaries.py::CONTRACT_FORM_LABELS) ни одна
# не означает буквально «без договора» — выбрана "goods_single" («Поставка —
# разовый договор»): ближе всего по смыслу к разовой покупке из перечня.
# Это соглашение по умолчанию, не жёсткая бизнес-норма — при другом
# предпочтении владельца менять только здесь (единственный источник).
ADVANCE_DEFAULT_CONTRACT_FORM = "goods_single"


def wish_item_kwargs_from_purchase_item(d: dict) -> dict[str, Any]:
    """Поля WishItem, которые компаньон авансового отчёта копирует из
    PurchaseItemCreate-дампа. НЕ включает wish_id/product_id-создание —
    это делает вызывающий код (product_id уже разрешён в d до вызова)."""
    return dict(
        item_name=d.get('item_name', ''),
        item_type=d.get('item_type'),
        quantity=d.get('quantity'),
        unit=d.get('unit'),
        unit_price=d.get('unit_price'),
        total_price=d.get('total_price'),
        country_origin=d.get('country_origin'),
        product_id=d.get('product_id'),
        feo_category_id=d.get('feo_category_id'),
        # Привязка к плановой позиции (Ур.5 ФЭО) — без неё PurchaseItemsEditor
        # считает позицию компаньона «не привязанной к плану» (itemsMissingPlan,
        # frontend/src/composables/items/useItemsBulkFeo.ts).
        feo_planned_item_id=d.get('feo_planned_item_id'),
        feo_planned_item_match_confirmed=bool(d.get('match_confirmed', False)),
        over_plan=bool(d.get('over_plan', False)),
        extra_attrs=d.get('extra_attrs') or {},
    )


def apply_wish_item_feo_link_to_purchase_item(pi, wi) -> None:
    """Зеркалит привязку к ФЭО ОДНОЙ позиции заявки (feo_category_id/
    feo_planned_item_id/over_plan) в связанную строку закупки `pi`.

    Сопоставление строк WishItem↔PurchaseItem — существующий hard link
    `purchase_items.wish_item_id` (миграция g1h2i3j4k5l6, колонка `wish_item_id`
    на модели PurchaseItem), тот же, которым уже пользуются
    app/services/wish_distribution.py и app/services/wish_multi_sync.py для
    обычных заявок. Отдельная колонка под эту связь НЕ заводится (ПРАВИЛО №6 —
    один механизм сопоставления на весь проект, а не второй для авансовых).

    До 2026-09-30 компаньон авансового отчёта этот link никогда не
    проставлял — create_purchase/update_purchase просто удаляли и пересоздавали
    WishItems при каждом сохранении закупки (см. вызовы ниже по коду этого
    модуля из purchases.py), поэтому обратной ссылки не было и построчная
    правка ФЭО согласующим в карточке заявки-компаньона (patch_wish_execution,
    WishItemFeoPatch) не долетала до purchase_items связанной закупки — а
    следующий PUT закупки эту рассинхронизацию заодно и закреплял бы (заявка
    №88 / закупка РЕЕ-2026-00962, прод, инцидент 2026-09-30: wish_item 4536/4529
    привязаны к новым плановым позициям 13116/13117, а purchase_item 3724/3726
    остались на старых 13091/13078). Теперь purchases.py проставляет
    wish_item_id при каждой пересборке WishItems, а patch_wish_execution вызывает
    эту функцию для каждой затронутой пары — единственное место, которое пишет
    три поля ниже со стороны заявки (ПРАВИЛО №6, не плодить вторую формулу).
    """
    pi.feo_category_id = wi.feo_category_id
    pi.feo_planned_item_id = wi.feo_planned_item_id
    pi.over_plan = bool(getattr(wi, 'over_plan', False))


def sync_wish_header_from_purchase(wish, purchase) -> list[str]:
    """subsidy_id/feo_category_id/event_id заявки-компаньона ← закупка,
    БЕЗУСЛОВНО (не только пустые поля — заявка ЗЕРКАЛО закупки при любом
    статусе, тот же принцип, что и для содержимого/цены/названия в
    routers/purchases.py::update_purchase, см. докстринг там).

    Вызывается из patch_purchase (автосейв карточки закупки) — единственный
    канал, которым фронт вообще шлёт subsidy_id (CreateOrderView.vue::
    serializeFormForAutosave), поэтому именно PATCH был реальным путём
    расхождения (прод, 2026-09-30: закупка РЕЕ-2026-00973/заявка №95,
    subsidy_id закупки менялся, заявка оставалась со старым/пустым значением).

    Возвращает список реально изменённых полей заявки (для ответа/лога,
    см. "wish_header_synced" в PATCH-ответе purchases.py).
    """
    changed: list[str] = []
    for f in ("subsidy_id", "feo_category_id", "event_id"):
        pv = getattr(purchase, f)
        if getattr(wish, f) != pv:
            setattr(wish, f, pv)
            changed.append(f)
    return changed


def apply_wish_header_to_purchase(purchase, wish) -> list[str]:
    """Обратное направление относительно sync_wish_header_from_purchase:
    subsidy_id/feo_category_id/event_id заявки-компаньона → закупка.

    Вызывается из wish_transitions.py::patch_wish_execution, когда
    согласующий (право wish.edit_feo) меняет субсидию/категорию ФЭО/
    мероприятие в карточке заявки-компаньона авансового отчёта
    (WishFormDialog.vue — поле «Субсидия» редактируемо для такого
    согласующего). Построчная привязка ФЭО уже зеркалится отдельно
    (apply_wish_item_feo_link_to_purchase_item выше) — здесь только шапка.

    Возвращает список реально изменённых полей закупки.
    """
    changed: list[str] = []
    for f in ("subsidy_id", "feo_category_id", "event_id"):
        wv = getattr(wish, f)
        if getattr(purchase, f) != wv:
            setattr(purchase, f, wv)
            changed.append(f)
    return changed


def sync_wish_contract_and_contractor(wish, purchase, creator) -> None:
    """contract_form/контрагент компаньона ← закупка (с фолбэками).

    Заполняет только пустые поля заявки (ручной выбор не перезаписывается).
    creator — автор авансового (Wish.created_by), не тот, кто сейчас сохраняет.
    - contract_form: с закупки, иначе ADVANCE_DEFAULT_CONTRACT_FORM.
    - contractor_id: с закупки, если задан.
    - contractor_name: ФИО (или логин) создателя закупки — ТОЛЬКО когда у
      закупки нет contractor_id (Purchase не хранит свободный
      contractor_name, поэтому без этого фолбэка «на кого оформлено» было бы
      вообще не видно на компаньоне).
    """
    # Только ПУСТЫЕ поля: правка авансового не смеет затирать то, что человек
    # выбрал в заявке руками (например, сотрудника-контрагента).
    if not wish.contract_form:
        wish.contract_form = purchase.contract_form or ADVANCE_DEFAULT_CONTRACT_FORM
    if not wish.contractor_id and not wish.contractor_name:
        if purchase.contractor_id:
            wish.contractor_id = purchase.contractor_id
        elif creator is not None:
            wish.contractor_name = getattr(creator, 'full_name', None) or getattr(creator, 'username', None)
