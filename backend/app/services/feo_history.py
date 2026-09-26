"""Журнал изменений ФЭО — ЕДИНСТВЕННАЯ точка записи истории для
feo_categories/feo_planned_items (волна 1 из 3, владелец 22.09).

«Импорт ФЭО не оставляет записи, кто загрузил файл и что он перезаписал.
А также если кто-то менял плановые позиции в ФЭО или вносил новые,
независимо от способа внесения. Если плановая появилась из заявки, то
пишется, на основании какой заявки — и там уже понятно, кто вносил.»

Хранилище — существующий entity_changes (app/models/entity_change.py), не
заводим вторую таблицу истории (Правило №6: у показателя «история изменений
сущности» уже есть один источник истины — entity_changes/record_entity_changes,
app/routers/entity_changes.py). Здесь — только тонкая обвязка над
record_entity_changes с фиксированными entity_type/source вместо того, чтобы
каждый вызывающий код (импорт, роутеры категорий/позиций, автопривязка,
схлопывание дублей) собирал вызов сам и на свой лад придумывал источник.

⚠️ Волна 1 — только этот модуль и его функции. Расстановка вызовов по точкам
изменения (feo_categories.py, feo_planned_items.py, feo_import_engine.py,
plan_autoassign.py, схлопывание дублей) — волна 2. UI ленты истории — волна 3.

Публичный API:
    ENTITY_FEO_ITEM, ENTITY_FEO_CATEGORY  — константы entity_type.
    SOURCES                                — ЕДИНСТВЕННЫЙ список допустимых
                                              значений source (сверяй с
                                              комментарием у колонки source в
                                              app/models/entity_change.py —
                                              комментарий там повторяет этот
                                              список для читаемости прямо у
                                              колонки, но нормативен именно
                                              этот кортеж).
    record_created(db, entity_type, entity_id, user, old_row=None, *,
                    source, source_ref=None, commit=True)
        Факт создания сущности — ОДНА запись EntityChange с
        field_name=FIELD_CREATED_MARKER ('__created__'), old_value=None,
        new_value=str(entity_id) (маркер значения не несёт смысла сам по
        себе — важен факт наличия строки с этим field_name; выдача GET
        /api/entity-changes/{type}/{id} отличает «создание» от «правки поля»
        по field_name == FIELD_CREATED_MARKER, а не по old_value is None,
        т.к. old_value=None легитимен и для обычной правки поля, у которого
        раньше не было значения).
    record_updated(db, entity_type, entity_id, user, old_values, new_values,
                    *, source, source_ref=None, commit=True)
        Построчный дифф полей — СТРОГО через record_entity_changes
        (app/routers/entity_changes.py), второй раз сравнение old/new не
        пишем (Правило №6).
    record_deleted(db, entity_type, entity_id, user, old_row=None, *,
                    source, source_ref=None, commit=True)
        Факт удаления — ОДНА запись с field_name=FIELD_DELETED_MARKER
        ('__deleted__'), тем же приёмом, что и record_created.

Все три принимают `user` — объект с .id/.full_name (обычно current_user) ИЛИ None
для системных вызовов без живого пользователя (тогда changed_by_id/name оба
NULL — например будущий cron схлопывания дублей без инициатора-человека).
`commit` пробрасывается в record_entity_changes как есть — импорт ФЭО
(волна 2) обязан звать все три с commit=False внутри своей транзакции
dry_run, и коммитить/откатывать снаружи одним махом.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.entity_changes import record_entity_changes

# ── Entity types (Правило №6 — эти же строки идут в entity_changes.py::_VALID_ENTITY_TYPES) ──
ENTITY_FEO_ITEM = "feo_item"
ENTITY_FEO_CATEGORY = "feo_category"

# ── Единственный список допустимых source (см. комментарий у колонки source
# в app/models/entity_change.py — дублирует эти же значения текстом рядом с
# колонкой для читаемости миграции/модели, но НОРМАТИВЕН именно этот кортеж) ──
SOURCE_MANUAL = "manual"
SOURCE_IMPORT = "import"
SOURCE_WISH = "wish"
SOURCE_PURCHASE = "purchase"
SOURCE_AUTOASSIGN = "autoassign"
SOURCE_COLLAPSE = "collapse"
SOURCES = (
    SOURCE_MANUAL,
    SOURCE_IMPORT,
    SOURCE_WISH,
    SOURCE_PURCHASE,
    SOURCE_AUTOASSIGN,
    SOURCE_COLLAPSE,
)

FIELD_CREATED_MARKER = "__created__"
FIELD_DELETED_MARKER = "__deleted__"


def _user_id_name(user) -> tuple[Optional[int], Optional[str]]:
    """User.full_name (не .name — см. app/models/user.py, поле производное
    через compose_fio) — тот же атрибут, что и остальной проект читает для
    changed_by_name."""
    if user is None:
        return None, None
    return getattr(user, "id", None), getattr(user, "full_name", None)


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"Invalid source: {source!r}. Must be one of {SOURCES}")


async def record_created(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user,
    *,
    source: str,
    source_ref: Optional[int] = None,
    commit: bool = True,
) -> None:
    """Факт создания сущности — см. докстринг модуля про FIELD_CREATED_MARKER."""
    _check_source(source)
    changed_by_id, changed_by_name = _user_id_name(user)
    await record_entity_changes(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        changed_by_id=changed_by_id,
        changed_by_name=changed_by_name,
        old_values={FIELD_CREATED_MARKER: None},
        new_values={FIELD_CREATED_MARKER: str(entity_id)},
        source=source,
        source_ref=source_ref,
        commit=commit,
    )


async def record_updated(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user,
    old_values: dict,
    new_values: dict,
    *,
    source: str,
    source_ref: Optional[int] = None,
    commit: bool = True,
) -> None:
    """Построчный дифф полей — тонкая обёртка над record_entity_changes.

    old_values/new_values — {field_name: value}, ровно как ожидает
    record_entity_changes (сравнение str(old) vs str(new) там же, второй раз
    не переопределяем).
    """
    _check_source(source)
    changed_by_id, changed_by_name = _user_id_name(user)
    await record_entity_changes(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        changed_by_id=changed_by_id,
        changed_by_name=changed_by_name,
        old_values=old_values,
        new_values=new_values,
        source=source,
        source_ref=source_ref,
        commit=commit,
    )


async def record_deleted(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    user,
    *,
    source: str,
    source_ref: Optional[int] = None,
    commit: bool = True,
) -> None:
    """Факт удаления сущности — см. докстринг модуля про FIELD_DELETED_MARKER."""
    _check_source(source)
    changed_by_id, changed_by_name = _user_id_name(user)
    await record_entity_changes(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        changed_by_id=changed_by_id,
        changed_by_name=changed_by_name,
        old_values={FIELD_DELETED_MARKER: str(entity_id)},
        new_values={FIELD_DELETED_MARKER: None},
        source=source,
        source_ref=source_ref,
        commit=commit,
    )
