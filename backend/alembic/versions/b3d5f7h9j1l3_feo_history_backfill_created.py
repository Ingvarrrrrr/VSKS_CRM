"""Бэкфилл журнала ФЭО (волна 3, 26.09): «создание» для позиций из ДО журнала

Владелец: «нужно знать ... кто менял плановые позиции ... или вносил новые
любым способом; если позиция появилась из заявки — на основании какой».
До миграции t6v8x1z3b5d7 (волна 1) журнал не существовал вовсе — все
FeoPlannedItem, заведённые раньше, не имеют записи __created__. Эта миграция
восстанавливает происхождение по остаточным следам, ОДНА запись на позицию:

  - есть строка заявки, ссылающаяся на неё (wish_items.feo_planned_item_id)
    → source='wish',       source_ref=id заявки (wish_items.wish_id);
  - иначе есть строка закупки (purchase_items.feo_planned_item_id)
    → source='purchase',   source_ref=id закупки (purchase_items.purchase_id);
  - иначе auto_created=true ИЛИ notes начинается с 'Создано '
    (см. app/services/plan_autoassign.py::note) → source='autoassign',
    source_ref=NULL (у автозаведения без заявки/закупки в journal нет второй
    сущности-источника, см. её же ветку в plan_autoassign.py);
  - иначе → source=NULL (позиция без восстановимого происхождения — обычная
    ручная запись до журнала, честно НЕ выдаём за 'manual', т.к. в отличие от
    'wish'/'purchase' здесь нет улики, кто именно её создал; UI (волна 3)
    подписывает такую запись как «до появления журнала, автор неизвестен»).

changed_by_id/changed_by_name — ВСЕГДА NULL: кто завёл позицию до журнала, мы
не знаем и не выдумываем (задание волны 3, дословно). changed_at — created_at
самой позиции (COALESCE на now() для НЕ NULL колонки entity_changes.changed_at,
у FeoPlannedItem.created_at её server_default — func.now(), NULL практически
не встречается, кроме совсем древних строк без default на момент вставки).

Идемпотентно БЕЗ доп. guard'а: WHERE NOT EXISTS (...) сам по себе делает
повторный прогон no-op — при первом запуске создаёт ровно недостающие строки,
при повторном не находит ни одной позиции без __created__ (кроме тех, что
появились ПОСЛЕ волны 1 — а те уже пишут __created__ на своём собственном
пути создания, см. волну 2).

Revision ID: b3d5f7h9j1l3
Revises: t6v8x1z3b5d7
Create Date: 2026-09-26 00:00:00.000000
"""
from alembic import op

revision = 'b3d5f7h9j1l3'
down_revision = 't6v8x1z3b5d7'
branch_labels = None
depends_on = None


_BACKFILL_SQL = """
INSERT INTO entity_changes (
    entity_type, entity_id, field_name, old_value, new_value,
    changed_by_id, changed_by_name, changed_at, source, source_ref
)
SELECT
    'feo_item',
    fpi.id,
    '__created__',
    NULL,
    fpi.id::text,
    NULL,
    NULL,
    COALESCE(fpi.created_at, now()),
    CASE
        WHEN wi.wish_id IS NOT NULL THEN 'wish'
        WHEN pi.purchase_id IS NOT NULL THEN 'purchase'
        WHEN fpi.auto_created = TRUE OR fpi.notes LIKE 'Создано %' THEN 'autoassign'
        ELSE NULL
    END,
    CASE
        WHEN wi.wish_id IS NOT NULL THEN wi.wish_id
        WHEN pi.purchase_id IS NOT NULL THEN pi.purchase_id
        ELSE NULL
    END
FROM feo_planned_items fpi
LEFT JOIN LATERAL (
    SELECT wish_id FROM wish_items
    WHERE feo_planned_item_id = fpi.id
    ORDER BY id LIMIT 1
) wi ON true
LEFT JOIN LATERAL (
    SELECT purchase_id FROM purchase_items
    WHERE feo_planned_item_id = fpi.id
    ORDER BY id LIMIT 1
) pi ON true
WHERE NOT EXISTS (
    SELECT 1 FROM entity_changes ec
    WHERE ec.entity_type = 'feo_item'
      AND ec.entity_id = fpi.id
      AND ec.field_name = '__created__'
);
"""


def upgrade() -> None:
    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    # Намеренно no-op (тот же приём, что и в других backfill-миграциях проекта,
    # например y1z2a3b4c5d6/w6y8a0c2e4g6): вставленные строки НЕЛЬЗЯ надёжно
    # отличить от совершенно легитимных строк волны 2 с тем же обликом —
    # record_created(..., user=None, source='wish'/'purchase'/'autoassign')
    # в plan_autoassign.py ТОЖЕ всегда пишет changed_by_id=changed_by_name=NULL
    # (см. app/services/feo_history.py::_user_id_name), поэтому фильтр
    # "changed_by_id IS NULL" удалил бы вперемешку и настоящую историю,
    # написанную уже ПОСЛЕ волны 1. Откатывать эту миграцию — вручную и
    # осознанно, не автоматикой downgrade.
    pass
