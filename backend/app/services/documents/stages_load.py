"""generate_document stage 1-3: validate doc_type, load purchase, framework/gate checks.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Behavior must stay byte-for-byte identical to the pre-split code — see
services/documents/generate.py for the call order.
"""
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.routers.purchases import is_framework_head, _generate_temp_contract_number
from app.services.documents.doc_types import DOC_TYPES, CONTRACT_FAMILY_DOC_TYPES
from app.services.documents.templates import (
    _resolve_doc_template_path,
    _require_vat_rate_for_doc,
    _require_purchase_method_for_doc,
)
from app.services.documents.contexts import (
    _require_contract_items_for_doc,
    _require_tz_duplicates_resolved_for_doc,
)
from app.services.documents.formatting import _resolve_responsible_person_update

import os


def validate_doc_type(doc_type: str):
    """Stage 1: unknown doc_type / globally-missing template → 400 / 404."""
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}. Доступны: {', '.join(DOC_TYPES)}")

    # Резолв шаблона: субсидийный override нужен по subsidy_id закупки, которая
    # ещё не загружена — на этом шаге резолвим без него (subsidy_id=None), только
    # чтобы рано отбить полностью отсутствующий шаблон (глобальный + fallback).
    # Полный резолв (с субсидийным override) повторяется ниже, после загрузки p.
    template_path, template_file, filename_base = _resolve_doc_template_path(doc_type, None)
    if not os.path.exists(template_path):
        raise HTTPException(
            404,
            f"Шаблон '{template_file}' не найден. "
            f"Поместите файл в backend/templates/{template_file}"
        )
    return template_path, template_file, filename_base


async def load_purchase_and_relations(db: AsyncSession, pid: int) -> Purchase:
    """Stage 2: load Purchase with eager-loaded relations needed downstream."""
    from app.models.contract_item import ContractItem as _ContractItem  # Phase 27.1 CD-5
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.contract_items).selectinload(_ContractItem.product),  # Phase 27.1 CD-5: eager-load for docxtpl context (including ci.product)
            selectinload(Purchase.assigned_user),  # B-dedup: для авто-инициалов responsible_person
            selectinload(Purchase.service_note_author),  # fallback «Ответственный исполнитель» = автор СЗ
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    return p


async def apply_responsible_person_update(p: Purchase, responsible_name: Optional[str], db: AsyncSession) -> None:
    # Запоминаем выбранного ответственного (см. _resolve_responsible_person_update
    # выше) — чтобы он подставлялся сам при следующей генерации и не «терялся».
    _new_responsible_person = _resolve_responsible_person_update(p.responsible_person, responsible_name)
    if _new_responsible_person is not None:
        p.responsible_person = _new_responsible_person
        await db.commit()


async def framework_contract_guard(p: Purchase, doc_type: str, db: AsyncSession) -> None:
    """Stage 3: framework-head temp contract number + doc-type gates (409/422 etc)."""
    # Владелец (2026-08-31): рамочная голова может подписываться («лист
    # согласования») раньше, чем станут известны реальные номер и дата
    # договора — при первом формировании договорного документа для такой
    # закупки без contract_number система присваивает технический номер
    # («ВРЕМ-{№закупки}») и сегодняшнюю дату, отмечая их флагом
    # contract_number_is_temporary для последующей актуализации (см.
    # POST /api/purchases/{pid}/actualize-contract-number). Уже заполненный
    # пользователем contract_number НЕ трогаем.
    if doc_type in CONTRACT_FAMILY_DOC_TYPES and is_framework_head(p) and not p.contract_number:
        p.contract_number = await _generate_temp_contract_number(p, db)
        p.contract_date = date.today()
        p.contract_number_is_temporary = True
        # async_session(expire_on_commit=False) — объект и его eager-loaded
        # relationships (items/contract_items/...) остаются в памяти как есть,
        # refresh() здесь не нужен и опасен (expire + возможный lazy-load вне
        # async greenlet при последующем чтении relationship ниже по коду).
        await db.commit()

    # Требование владельца («Плановые не равно Договор»): для договорных
    # типов документа позиции/суммы обязаны быть заполнены в ContractItem —
    # никакого молчаливого отката на plan/НМЦК. Гейт стоит максимально рано,
    # до тяжёлых запросов ниже.
    _require_contract_items_for_doc(p, doc_type)
    # Решение владельца (21.09, W3): документ, печатающий строки purchase_items
    # (любой doc_type не из CONTRACT_FAMILY_DOC_TYPES, и рамочная голова без
    # ContractItem — см. _build_contract_items_context D-08 fallback), не
    # формируется, пока дубли строк ТЗ не решены явно (merge/keep). Договорной
    # doc_type с уже заполненными ContractItem их не использует вовсе —
    # проверка здесь не нужна, чтобы не блокировать несвязанный документ.
    if doc_type not in CONTRACT_FAMILY_DOC_TYPES or not getattr(p, "contract_items", None):
        _require_tz_duplicates_resolved_for_doc(p)
    _require_purchase_method_for_doc(p, doc_type)
    _require_vat_rate_for_doc(p, doc_type)


_CONTRACT_FORM_TO_DOC_TYPE = {
    "services": "contract_services",
    "services_food": "contract_services_food",
    "services_accommodation": "contract_services_accommodation",
    "services_accommodation_food": "contract_services_accommodation_food",
    "services_transport": "contract_services_transport",
    "services_flight": "contract_services_flight",
    "services_train": "contract_services_train",
    "goods_single": "contract_goods_single",
    "gph_individual": "contract_gph_individual",
    "gph_individual_rid": "contract_gph_individual_rid",
    "repair_vehicle": "contract_repair_vehicle",
    "repair_framework": "contract_repair_framework",
}


def resolve_effective_contract_doc_type(doc_type: str, p=None) -> str:
    """Если запрошен устаревший общий 'contract' или 'contract_tz',
    перенаправляем на типовой шаблон договора (contract_services /
    contract_goods_single / по contract_form) и ТЗ для договора
    (tech_spec_contract)."""
    if doc_type == "contract" and p is not None:
        cf = getattr(p, "contract_form", None)
        if cf and cf in _CONTRACT_FORM_TO_DOC_TYPE:
            return _CONTRACT_FORM_TO_DOC_TYPE[cf]
        raw_items = [
            it for it in (getattr(p, "contract_items", None) or getattr(p, "items", None) or [])
            if (getattr(it, "item_name", None) or "").strip()
        ]
        if raw_items:
            all_services = all((getattr(it, "item_type", None) or "товар") == "услуга" for it in raw_items)
        else:
            all_services = getattr(p, "item_type", None) == "услуга"
        return "contract_services" if all_services else "contract_goods_single"
    if doc_type == "contract_tz" and p is not None:
        return "tech_spec_contract"
    return doc_type


def resolve_final_template(doc_type: str, subsidy_id, p=None):
    """Re-resolve template path now that subsidy_id is known (subsidy override)."""
    effective_doc_type = resolve_effective_contract_doc_type(doc_type, p)
    return _resolve_doc_template_path(effective_doc_type, subsidy_id)
