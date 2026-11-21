"""Обогащение контекста документов родительным падежом подписантов и авто-номером приказа.

Правило №6 (Единый источник истины) и Правило №5 (< 500 строк).
Обеспечивает:
1. Родительный падеж подписантов и ответственных:
   - customer_signatory_genitive (должность + ФИО в род. падеже Заказчика)
   - contractor_signatory_genitive (должность + ФИО в род. падеже Подрядчика)
   - initiator_fio_genitive (ФИО инициатора в род. падеже)
   - responsible_person_genitive (ФИО ответственного в род. падеже)
   - авто-нормализацию для конструкций «в лице ...»
2. Детерминированный номер приказа на закупку (если не задан вручную):
   - procurement_order_number и order_number
"""
from __future__ import annotations

from typing import Any, Optional
from app.services.fio_inflect import inflect_fio, inflect_position, inflect_signatory_full


def enrich_document_signatories_and_orders(context: dict[str, Any], purchase: Optional[Any] = None, subsidy: Optional[Any] = None) -> None:
    """Единая точка обогащения контекста падежами подписантов и номером приказа."""

    # ── 1. Заказчик (Customer) ───────────────────────────────────────────────
    cust_full = context.get("customer_signatory", "") or ""
    cust_name = context.get("customer_signatory_name", "") or ""
    cust_pos = context.get("customer_signatory_position", "") or ""

    if not context.get("customer_signatory_genitive"):
        if cust_full:
            context["customer_signatory_genitive"] = inflect_signatory_full(cust_full, "gent")
        elif cust_name or cust_pos:
            pos_gen = inflect_position(cust_pos, "gent") if cust_pos else ""
            name_gen = inflect_fio(cust_name, "gent") if cust_name else ""
            context["customer_signatory_genitive"] = f"{pos_gen} {name_gen}".strip()
        else:
            context["customer_signatory_genitive"] = ""

    if not context.get("customer_signatory_name_genitive") and cust_name:
        context["customer_signatory_name_genitive"] = inflect_fio(cust_name, "gent")

    # ── 2. Подрядчик / Исполнитель (Contractor) ──────────────────────────────
    ctr_full = context.get("contractor_signatory", "") or ""
    ctr_name = context.get("contractor_signatory_name", "") or ""
    ctr_pos = context.get("contractor_signatory_position", "") or ""

    if not context.get("contractor_signatory_genitive"):
        if ctr_full:
            context["contractor_signatory_genitive"] = inflect_signatory_full(ctr_full, "gent")
        elif ctr_name or ctr_pos:
            pos_gen = inflect_position(ctr_pos, "gent") if ctr_pos else ""
            name_gen = inflect_fio(ctr_name, "gent") if ctr_name else ""
            context["contractor_signatory_genitive"] = f"{pos_gen} {name_gen}".strip()
        else:
            context["contractor_signatory_genitive"] = ""

    if not context.get("contractor_signatory_name_genitive") and ctr_name:
        context["contractor_signatory_name_genitive"] = inflect_fio(ctr_name, "gent")

    # ── 3. Инициатор служебной записки (Initiator) ───────────────────────────
    init_name = context.get("initiator_name", "") or ""
    if not context.get("initiator_fio_genitive"):
        context["initiator_fio_genitive"] = inflect_fio(init_name, "gent") if init_name else ""
    if not context.get("initiator_name_genitive"):
        context["initiator_name_genitive"] = context["initiator_fio_genitive"]

    # ── 4. Ответственный исполнитель (Responsible person) ────────────────────
    resp_full = context.get("responsible_person_full", "") or context.get("responsible_person", "") or ""
    if not context.get("responsible_person_genitive"):
        context["responsible_person_genitive"] = inflect_fio(resp_full, "gent") if resp_full else ""
    if not context.get("responsible_person_full_genitive"):
        context["responsible_person_full_genitive"] = context["responsible_person_genitive"]

    # ── 5. Авто-номер приказа о закупке (procurement_order_number / order_number)
    order_num = (context.get("procurement_order_number") or context.get("order_number") or "").strip()
    if not order_num:
        # Пытаемся взять из объекта purchase / subsidy
        if purchase:
            order_num = (
                getattr(purchase, "procurement_order_number", None)
                or getattr(purchase, "order_number", None)
                or ""
            ).strip()
            if not order_num:
                # Детерминированный fallback по ТЗ:
                # на основе префикса/года и registry_number / purchase_number / commission_order_number
                comm_num = getattr(purchase, "commission_order_number", None)
                if not comm_num and subsidy:
                    comm_num = getattr(subsidy, "commission_order_number", None)
                if comm_num:
                    order_num = str(comm_num).strip()
                elif getattr(purchase, "registry_number", None):
                    order_num = f"ПР-{purchase.registry_number}".strip()
                elif getattr(purchase, "purchase_number", None):
                    order_num = f"ПР-{purchase.purchase_number}".strip()
                elif getattr(purchase, "id", None):
                    order_num = f"ПР-{purchase.id}".strip()

        if not order_num and subsidy:
            comm_num = getattr(subsidy, "commission_order_number", None)
            if comm_num:
                order_num = str(comm_num).strip()

        if not order_num:
            # Fallback по контексту (registry_number или purchase_number в словаре)
            reg = str(context.get("registry_number") or "").strip()
            pnum = str(context.get("purchase_number") or "").strip()
            if reg:
                order_num = f"ПР-{reg}" if not reg.startswith("ПР-") else reg
            elif pnum:
                order_num = f"ПР-{pnum}" if not pnum.startswith("ПР-") else pnum
            else:
                order_num = "1"

    context["procurement_order_number"] = order_num
    context["order_number"] = order_num
