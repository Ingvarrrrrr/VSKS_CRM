"""generate_document: items list / subject_kind detection.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
from app.models.purchase import Purchase
from app.services.documents.doc_types import CONTRACT_FAMILY_DOC_TYPES
from app.services.documents.contexts import (
    _build_items_list_from_contract_items,
    _build_items_list_from_purchase_items,
)


def build_items_and_subject_kind(p: Purchase, doc_type: str, tz_override_mode, resolve_photo):
    # Build template context
    # «Плановые не равно Договор»: для CONTRACT_FAMILY_DOC_TYPES позиции
    # берутся ТОЛЬКО из ContractItem (гейт _require_contract_items_for_doc
    # выше уже гарантировал, что contract_items не пуст). Для остальных —
    # старое поведение (purchase_items).
    if doc_type in CONTRACT_FAMILY_DOC_TYPES:
        items_list = _build_items_list_from_contract_items(p, resolve_photo=resolve_photo)
    else:
        items_list = _build_items_list_from_purchase_items(
            p, tz_override_mode=tz_override_mode, resolve_photo=resolve_photo,
        )

    # Phase 23.1: auto-detect subject_kind for universal contract.docx
    # 'services' if ALL items have item_kind='услуга', otherwise 'goods' (default)
    subject_kind = "goods"
    if items_list:
        kinds = {it.get("item_kind", "товар").lower() for it in items_list}
        if kinds == {"услуга"}:
            subject_kind = "services"

    return items_list, subject_kind
