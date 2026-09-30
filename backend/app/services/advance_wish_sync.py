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
