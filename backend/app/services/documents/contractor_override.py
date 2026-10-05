"""Правка реквизитов исполнителя на уровне субсидии (SubsidyContractorOverride,
см. app/models/subsidy_contractor_override.py и
routers/subsidies.py::get_contractor_override/upsert_contractor_override).

Владелец (05.10.2026, план «Шаблоны договоров», п.5): правка, сделанная в
карточке субсидии, в договор не попадала — генератор документа брал сырой
Contractor (generate.py: `c = p.contractor`). ПРАВИЛО №6 — один источник
применения override: эта функция, вызывается из generate.py перед сборкой
контекста; никто другой override для документа не читает и не копирует.

ORM-объект Contractor НЕ мутируется (иначе изменения могли случайно уйти в
БД при следующем commit сессии) — merge_contractor_override возвращает
read-only обёртку, которая отдаёт непустое поле override, а остальное —
как есть у contractor.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_contractor_override import SubsidyContractorOverride

# Поля override — имена совпадают с атрибутами Contractor (см. оба models/*.py).
_OVERRIDE_FIELDS = (
    "org_type", "inn", "kpp", "ogrn",
    "signatory", "signatory_position", "signatory_basis",
    "signatory_last_name", "signatory_first_name", "signatory_middle_name",
    "address", "postal_address", "bank_details",
    "settlement_account", "bank_name", "bik", "correspondent_account",
    "contact_person", "phone", "email",
)


async def load_contractor_override(db: AsyncSession, subsidy_id, contractor_id):
    """SubsidyContractorOverride для (subsidy_id, contractor_id) либо None."""
    if not subsidy_id or not contractor_id:
        return None
    return (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == contractor_id,
        )
    )).scalar_one_or_none()


class _OverriddenContractor:
    """Read-only вид на Contractor: непустые поля override перекрывают
    поля контрагента, остальные атрибуты читаются из contractor напрямую."""

    __slots__ = ("_contractor", "_override")

    def __init__(self, contractor, override):
        self._contractor = contractor
        self._override = override

    def __getattr__(self, name):
        if name in _OVERRIDE_FIELDS:
            value = getattr(self._override, name, None)
            if value not in (None, ""):
                return value
        return getattr(self._contractor, name, None)

    def __bool__(self):
        return bool(self._contractor)


def merge_contractor_override(contractor, override):
    """Контрагент для контекста документа: contractor с полями override
    поверх (если override задан и поле в нём непустое).

    contractor=None → None (закупка без контрагента — override неприменим).
    override=None   → contractor без изменений (ничего не оборачиваем).
    """
    if contractor is None or override is None:
        return contractor
    return _OverriddenContractor(contractor, override)
