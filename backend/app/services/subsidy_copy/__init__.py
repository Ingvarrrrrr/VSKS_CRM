"""«Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б).

create_sandbox_copy — единственная точка входа для POST /api/subsidies/{id}/copy
(ПРАВИЛО №5 — остальная логика разрезана по соседним файлам этого пакета).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy

from .copy_tree import copy_feo_tree, copy_access_and_approvers, copy_templates
from .copy_purchases import copy_purchases
from .delete_copy import delete_sandbox_copy, dry_run_delete

__all__ = [
    "create_sandbox_copy",
    "delete_sandbox_copy",
    "dry_run_delete",
    "promote_sandbox_copy",
]


async def _unique_copy_name(db: AsyncSession, base_name: str) -> str:
    candidate = f"{base_name} (копия)"
    n = 1
    while True:
        exists = (await db.execute(
            select(Subsidy.id).where(Subsidy.name == candidate).limit(1)
        )).scalar_one_or_none()
        if not exists:
            return candidate
        n += 1
        candidate = f"{base_name} (копия {n})"


async def create_sandbox_copy(db: AsyncSession, source: Subsidy) -> Subsidy:
    """Копия субсидии целиком: дерево ФЭО + план, доступы/согласующие,
    docx-шаблоны, закупки с договорами/позициями/чеками/платежами/файлами.
    НЕ копируются заявки и история согласований (решение владельца).

    Одна транзакция, без уведомлений — caller (router) делает commit."""
    name = await _unique_copy_name(db, source.name)
    new_subsidy = Subsidy(
        name=name,
        year=source.year,
        budget=source.budget,
        description=source.description,
        agreement_text=source.agreement_text,
        grantor_name=source.grantor_name,
        ministry_name=source.ministry_name,
        extra_contract_clause_1=source.extra_contract_clause_1,
        extra_contract_clause_2=source.extra_contract_clause_2,
        require_planned_dates=source.require_planned_dates,
        ceiling_warn_percent=source.ceiling_warn_percent,
        org_id=source.org_id,
        contractor_id=source.contractor_id,
        status=source.status,
        is_sandbox=True,
        copied_from_id=source.id,
        # basis_doc_number/basis_doc_date/agreement_number сознательно НЕ
        # копируются — это реквизиты РЕАЛЬНОГО документа-основания/соглашения,
        # у копии-песочницы его нет (иначе банковский матчинг и ensure_contract_
        # linked рисковали бы спутать копию с оригиналом, см. payment_matcher.py).
    )
    db.add(new_subsidy)
    await db.flush()

    tree = await copy_feo_tree(db, source.id, new_subsidy.id)
    await copy_access_and_approvers(db, source.id, new_subsidy.id)
    await copy_purchases(db, source.id, new_subsidy.id, tree.category_id_map, tree.planned_item_id_map)
    await db.flush()
    copy_templates(source.id, new_subsidy.id)  # файловая операция, не часть транзакции БД

    return new_subsidy


async def promote_sandbox_copy(subsidy: Subsidy) -> None:
    """«Сделать настоящей» — снимает флаг песочницы. Числа копии начинают
    учитываться в итогах дашборда/аккаунта как у любой обычной субсидии
    (оригинал и копия с этого момента считаются ДВАЖДЫ — предупреждение
    владельцу показывает фронт перед вызовом)."""
    subsidy.is_sandbox = False
