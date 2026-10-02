"""Группы полей (field_group) и bundle_no корректировки утверждённой субсидии —
вынесено из subsidy_revision_ops.py (ПРАВИЛО №5, тот файл подходил к 500
строкам). Единственное место, где перечислены группы полей сущностей
(ПРАВИЛО №6) — читают и роутер (app.routers.subsidy_revisions), и
subsidy_revision_ops.add_op (реэкспортирует эти имена как свои атрибуты через
`from ... import *`-подобный набор ниже, см. докстринг там), и applier
(subsidy_revision_apply.py).

ПОЛЯ И ИХ ГРУППЫ — одна строка корректировки правит РОВНО одну группу полей
одной сущности; повторная правка той же сущности и группы сливается в уже
существующую строку (см. subsidy_revision_ops.add_op/merge_after_fields).
Качественно разные вещи (деньги по ФЭО / план / описание / положение в
дереве) не блокируют и не склеиваются друг с другом.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

ENTITY_SUBSIDY = "subsidy"
ENTITY_CATEGORY = "feo_category"
ENTITY_ITEM = "feo_item"
ENTITIES = (ENTITY_SUBSIDY, ENTITY_CATEGORY, ENTITY_ITEM)

FIELD_GROUPS: dict[str, dict[str, tuple]] = {
    ENTITY_SUBSIDY: {
        "budget": ("budget",),
        "meta": ("name", "description", "basis_doc_number", "basis_doc_date", "grantor_name"),
    },
    ENTITY_CATEGORY: {
        "funding": ("budget", "feo_quantity", "feo_unit", "feo_amount"),
        "plan": ("planned_quantity", "planned_amount", "plan_source", "manual_plan_amount"),
        "meta": ("name", "code", "appendix", "is_active", "description", "unit"),
        "structure": ("parent_id",),
    },
    ENTITY_ITEM: {
        "qty_price": (
            "quantity", "unit_price", "amount", "payment_mode", "planned_date",
            "monthly_start_date", "monthly_end_date", "monthly_amount", "months_count",
        ),
        "meta": (
            "name", "unit", "notes", "is_active", "sort_order", "item_type",
            "is_feo_breakdown", "is_internal_plan", "is_composite",
            "feo_quantity", "feo_unit_price", "feo_amount",
        ),
        "structure": ("feo_category_id",),
    },
}

ALL_FIELDS: dict[str, tuple] = {
    entity: tuple(f for group in groups.values() for f in group)
    for entity, groups in FIELD_GROUPS.items()
}

# Поля, которые реально шлёт фронт в after (см. feoWriteAdapter.ts/
# useFeoLevel5ItemType.ts/useFeoPlannedItemEditDialog.ts), но которые НЕ
# являются колонками сущности — флаги самого запроса. split_after_fields
# (ниже) отбрасывает их молча при автоматической раскладке по группам; любое
# ДРУГОЕ неопознанное поле — явная 422 со списком, а не потерянная правка и не
# 500.
SERVICE_FIELDS: dict[str, frozenset] = {
    ENTITY_ITEM: frozenset({"sync_product_kind", "product_id", "allow_duplicate_name"}),
    ENTITY_CATEGORY: frozenset(),
    ENTITY_SUBSIDY: frozenset(),
}


def _group_for_field(entity_type: str, field: str) -> Optional[str]:
    for group, fields in FIELD_GROUPS.get(entity_type, {}).items():
        if field in fields:
            return group
    return None


def field_group_for(entity_type: str, field: str) -> str:
    group = _group_for_field(entity_type, field)
    if group is None:
        raise HTTPException(
            422,
            detail={
                "code": "unknown_field",
                "message": f"Поле «{field}» не входит ни в одну группу правки «{entity_type}»",
            },
        )
    return group


def split_after_fields(entity_type: str, after: dict) -> tuple[dict[str, dict], list[str]]:
    """Раскладывает after по группам полей сущности — используется, когда
    клиент НЕ передал field_group (POST /ops шлёт только реально изменённые
    поля, см. докстринг feoWriteAdapter.ts, которые могут принадлежать сразу
    нескольким группам: amount+feo_amount -> 'qty_price'+'funding'). Известные
    служебные флаги запроса (SERVICE_FIELDS, не колонки сущности) молча
    отбрасываются и перечисляются вторым элементом возврата; любое ДРУГОЕ
    неопознанное поле — 422 со списком СРАЗУ всех таких полей (не падаем на
    первом же, чтобы фронт увидел всю картину за один запрос)."""
    groups: dict[str, dict] = {}
    dropped: list[str] = []
    unknown: list[str] = []
    service = SERVICE_FIELDS.get(entity_type, frozenset())
    for field, value in after.items():
        group = _group_for_field(entity_type, field)
        if group is not None:
            groups.setdefault(group, {})[field] = value
        elif field in service:
            dropped.append(field)
        else:
            unknown.append(field)
    if unknown:
        raise HTTPException(
            422,
            detail={
                "code": "unknown_field",
                "message": f"Поля {sorted(unknown)} не входят ни в одну группу правки «{entity_type}»",
            },
        )
    return groups, dropped


def parse_bundle_no(value) -> Optional[int]:
    """Связка (bundle_no) — колонка Integer («Связка 1, 2…»). Фронт может
    прислать её строкой ("1") — приводим к int; None/"" — отсутствие связки;
    нечисловое значение ("B1") — явная 422, не падение на INSERT/UPDATE."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise HTTPException(422, {"code": "bad_bundle_no", "message": "Связка (bundle_no) должна быть числом"})
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        if s.lstrip("-").isdigit():
            return int(s)
    raise HTTPException(
        422,
        {
            "code": "bad_bundle_no",
            "message": f"Связка «{value}» должна быть числом (например 1, 2…), не текстом",
        },
    )


_ENTITY_NOT_IN_SUBSIDY = HTTPException(
    404,
    detail={
        "code": "entity_not_in_subsidy",
        "message": "Строка корректировки ссылается на позицию/статью не из этой субсидии",
    },
)


def _not_in_subsidy() -> HTTPException:
    # Новый экземпляр на каждый вызов — FastAPI/Starlette мутирует объект
    # исключения (headers и т.п.), общий синглтон не переиспользуем.
    return HTTPException(404, detail=dict(_ENTITY_NOT_IN_SUBSIDY.detail))


async def assert_entity_in_subsidy(
    db: AsyncSession, subsidy_id: int, entity_type: str, target_id: Optional[int],
) -> None:
    """ЕДИНСТВЕННАЯ проверка (ПРАВИЛО №6), что сущность, на которую ссылается
    строка корректировки (target_id автора ИЛИ extra_ops проверяющего, родитель
    create/move), действительно принадлежит субсидии этой корректировки —
    IDOR-гейт против чужой FeoCategory/FeoPlannedItem/Subsidy, подставленной по
    id. target_id=None — не живая ссылка (например target_ref на строку этой же
    корректировки, или create без родителя) — пропускаем, проверять нечего.
    Вызывается и при сборе строки (add_op/_add_single_update_op), и повторно
    непосредственно перед записью (apply_ops) — сущность могли переместить в
    другую субсидию за время, пока корректировка ждала решения."""
    if target_id is None:
        return

    if entity_type == ENTITY_SUBSIDY:
        if target_id != subsidy_id:
            raise _not_in_subsidy()
        return

    if entity_type == ENTITY_CATEGORY:
        from app.models.feo_category import FeoCategory
        cat = await db.get(FeoCategory, target_id)
        if cat is None or cat.subsidy_id != subsidy_id:
            raise _not_in_subsidy()
        return

    if entity_type == ENTITY_ITEM:
        from app.models.feo_category import FeoCategory
        from app.models.feo_planned_item import FeoPlannedItem
        item = await db.get(FeoPlannedItem, target_id)
        if item is None:
            raise _not_in_subsidy()
        cat = await db.get(FeoCategory, item.feo_category_id)
        if cat is None or cat.subsidy_id != subsidy_id:
            raise _not_in_subsidy()
        return

    raise HTTPException(422, f"Неизвестный тип сущности: {entity_type}")
