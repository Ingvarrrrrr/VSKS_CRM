"""Идемпотентные DDL-миграции, выполняемые при каждом старте приложения
(ALTER TABLE ... IF NOT EXISTS, CREATE TABLE IF NOT EXISTS, вызовы
check_schema._ensure_*). Это НЕ замена Alembic — Alembic функционален с
2026-06-02 (см. project_alembic_functional в Obsidian), новый DDL должен
идти миграцией; этот модуль — унаследованные non-fatal подстраховки,
перенесённые 1:1 из app/__init__.py.lifespan при разрезании файла на модули
(Правило №5). Каждый блок — отдельная функция с исходным
комментарием-заголовком; run() вызывает их в исходном порядке.
"""
import logging

from app.database import engine


async def _phase22_bank_payments_hash_migration():
    # Phase 22: idempotent ALTER для bank_payments — заменить старый UniqueConstraint на source_row_hash
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            # Дропаем старый natural-key UniqueConstraint (если есть на проде из старых ревертов)
            await conn.execute(text("ALTER TABLE bank_payments DROP CONSTRAINT IF EXISTS uq_bank_payment_natural"))
            # Добавляем колонку source_row_hash если не существует
            await conn.execute(text("ALTER TABLE bank_payments ADD COLUMN IF NOT EXISTS source_row_hash VARCHAR(64)"))
            # Создаём partial unique index (WHERE IS NOT NULL — legacy NULL записи не дедуплицируются)
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_bank_payment_source_row_hash "
                "ON bank_payments (source_row_hash) WHERE source_row_hash IS NOT NULL"
            ))
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 22 hash migration skipped (non-fatal): {e}")


async def _phase26_dd_contract_items_fk():
    # Phase 26-DD: FK contract_items.source_item_id → SET NULL ON DELETE.
    # Раньше RESTRICT — update_purchase delete-then-insert ломал FK от contract_items,
    # которые ссылались на старые purchase_items.
    try:
        from sqlalchemy import text as _text
        async with engine.begin() as conn:
            await conn.execute(_text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.referential_constraints
                        WHERE constraint_name = 'contract_items_source_item_id_fkey'
                          AND delete_rule != 'SET NULL'
                    ) THEN
                        ALTER TABLE contract_items
                            DROP CONSTRAINT contract_items_source_item_id_fkey;
                        ALTER TABLE contract_items
                            ADD CONSTRAINT contract_items_source_item_id_fkey
                            FOREIGN KEY (source_item_id) REFERENCES purchase_items(id)
                            ON DELETE SET NULL;
                    END IF;
                END $$;
            """))
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-DD FK ALTER skipped (non-fatal): {e}")


async def _phase27_1_contract_items_table():
    # Phase 27.1: contract_items table + idempotent backfill (non-fatal pattern из Phase 22)
    try:
        from check_schema import _ensure_contract_items_table, _backfill_contract_items_from_purchase_items
        async with engine.begin() as conn:
            await _ensure_contract_items_table(conn)
            backfilled = await _backfill_contract_items_from_purchase_items(conn)
            if backfilled:
                logging.getLogger(__name__).info(
                    f"Phase 27.1 backfill: {backfilled} contract_items inserted from legacy purchase_items"
                )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 27.1 contract_items setup skipped (non-fatal): {e}"
        )


async def _phase26_bb_purchase_items_receipt_id():
    # Phase 26-BB: purchase_items.receipt_id column + FK
    try:
        from check_schema import _ensure_purchase_items_receipt_id
        async with engine.begin() as conn:
            await _ensure_purchase_items_receipt_id(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-BB receipt_id column setup skipped (non-fatal): {e}")


async def _phase26_u3_vat_columns():
    # Phase 26-U-3: idempotent ALTER для purchase_items.vat_rate + purchases.vat_mode
    try:
        from sqlalchemy import text as _text2
        async with engine.begin() as conn:
            await conn.execute(_text2(
                "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS vat_rate VARCHAR(20)"
            ))
            await conn.execute(_text2(
                "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS vat_mode VARCHAR(20) DEFAULT 'uniform'"
            ))
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-U-3 vat columns skipped (non-fatal): {e}")


async def _phase26_yy_snapshot_hash_column():
    # Phase 26-YY: idempotent ALTER — purchases.recompute_snapshot_hash (SHA-1 гейт
    # auto-recompute из purchase_receipts._recompute_from_receipts_core).
    try:
        from sqlalchemy import text as _text3
        async with engine.begin() as conn:
            await conn.execute(_text3(
                "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS recompute_snapshot_hash VARCHAR(64)"
            ))
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-YY snapshot_hash column skipped (non-fatal): {e}")


async def _phase29_vehicles_fleet_schema():
    # Phase 29: vehicles fleet tables + ALTER purchases/users/tasks
    try:
        from check_schema import (
            _ensure_external_drivers_table, _ensure_vehicles_table,
            _ensure_vehicle_attachments_table, _ensure_vehicle_repairs_table,
            _ensure_repair_attachments_table, _ensure_vehicle_field_history_table,
            _ensure_vehicle_odometer_table, _ensure_fuel_logs_table,
            _ensure_trips_table, _ensure_purchases_vehicle_id,
            _ensure_users_driver_columns, _ensure_tasks_system_tag,
            _ensure_vehicles_new_columns,
            _ensure_vehicles_assignment_columns, _ensure_vehicle_transfer_history_table,
            _ensure_vehicle_fines_table,
            _ensure_organizations_color,
        )
        async with engine.begin() as conn:
            for fn in [
                _ensure_external_drivers_table, _ensure_vehicles_table,
                _ensure_vehicles_new_columns,
                _ensure_vehicle_attachments_table, _ensure_vehicle_repairs_table,
                _ensure_repair_attachments_table, _ensure_vehicle_field_history_table,
                _ensure_vehicle_odometer_table, _ensure_fuel_logs_table,
                _ensure_trips_table, _ensure_purchases_vehicle_id,
                _ensure_users_driver_columns, _ensure_tasks_system_tag,
                _ensure_vehicles_assignment_columns, _ensure_vehicle_transfer_history_table,
                _ensure_vehicle_fines_table,
                _ensure_organizations_color,
            ]:
                try:
                    await fn(conn)
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"Phase 29 schema {fn.__name__} skipped: {e}"
                    )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 29 schema bootstrap failed (non-fatal): {e}"
        )


async def _phase30_schema_bootstrap():
    # Phase 30: новые таблицы и колонки
    try:
        from check_schema import (
            _ensure_organizations_geo_fields,
            _ensure_users_driver_extended,
            _ensure_fleet_documents_table,
            _ensure_trips_waybill_columns,
            _ensure_waybill_children_tables,
            _ensure_checklists_tables,
            _ensure_incidents_table,
        )
        async with engine.begin() as conn:
            for fn in [
                _ensure_trips_waybill_columns,
                _ensure_waybill_children_tables,
                _ensure_checklists_tables,
                _ensure_incidents_table,
                _ensure_fleet_documents_table,
                _ensure_organizations_geo_fields,
                _ensure_users_driver_extended,
            ]:
                try:
                    await fn(conn)
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"Phase 30 schema {fn.__name__} skipped: {e}"
                    )
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 30 schema bootstrap failed (non-fatal): {e}"
        )


async def _phase12_05_effective_date_column():
    # Phase 12-05: plan_graph_versions.effective_date column
    try:
        from check_schema import _ensure_plan_graph_versions_effective_date_column
        async with engine.begin() as conn:
            await _ensure_plan_graph_versions_effective_date_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Phase 12-05 effective_date column setup skipped (non-fatal): {e}"
        )


async def _fcat_b1_feo_category_id_column():
    # FCAT-B1: purchase_items.feo_category_id column
    try:
        from check_schema import _ensure_purchase_items_feo_category_id_column
        async with engine.begin() as conn:
            await _ensure_purchase_items_feo_category_id_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"FCAT-B1 feo_category_id column setup skipped (non-fatal): {e}"
        )


async def _import_vat_cols_vat_amount_column():
    # import-vat-cols: purchase_items.vat_amount column
    try:
        from check_schema import _ensure_purchase_items_vat_amount_column
        async with engine.begin() as conn:
            await _ensure_purchase_items_vat_amount_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"import-vat-cols vat_amount column setup skipped (non-fatal): {e}"
        )


async def _import_vat_cols_total_with_vat_column():
    # import-vat-cols: purchase_items.total_with_vat column
    try:
        from check_schema import _ensure_purchase_items_total_with_vat_column
        async with engine.begin() as conn:
            await _ensure_purchase_items_total_with_vat_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"import-vat-cols total_with_vat column setup skipped (non-fatal): {e}"
        )


async def _sn_ux_service_note_to_user_id_column():
    # SN-UX: purchases.service_note_to_user_id column
    try:
        from check_schema import _ensure_purchases_service_note_to_user_id_column
        async with engine.begin() as conn:
            await _ensure_purchases_service_note_to_user_id_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"SN-UX service_note_to_user_id column setup skipped (non-fatal): {e}"
        )


async def _feo_reorder_sort_order_column():
    # FEO-reorder: feo_categories.sort_order column
    try:
        from check_schema import _ensure_feo_categories_sort_order_column
        async with engine.begin() as conn:
            await _ensure_feo_categories_sort_order_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"FEO-reorder sort_order column setup skipped (non-fatal): {e}"
        )


async def _b9_wish_items_feo_category_column():
    # B9: wish_items.feo_category_id column
    try:
        from check_schema import _ensure_wish_items_feo_category_column
        async with engine.begin() as conn:
            await _ensure_wish_items_feo_category_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"B9 wish_items.feo_category_id column setup skipped (non-fatal): {e}"
        )


async def _b_event_wishes_event_id_column():
    # B-event: wishes.event_id column
    try:
        from check_schema import _ensure_wishes_event_id_column
        async with engine.begin() as conn:
            await _ensure_wishes_event_id_column(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"B-event wishes.event_id column setup skipped (non-fatal): {e}"
        )


async def _b_exec_wishes_execution_columns():
    # B-exec: wishes.executor_id + execution_deadline columns
    try:
        from check_schema import _ensure_wishes_execution_columns
        async with engine.begin() as conn:
            await _ensure_wishes_execution_columns(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"B-exec wishes execution columns setup skipped (non-fatal): {e}"
        )


async def _contractor_card_columns():
    # contractor-card: contractors new card columns
    try:
        from check_schema import _ensure_contractors_card_columns
        async with engine.begin() as conn:
            await _ensure_contractors_card_columns(conn)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"contractor-card columns setup skipped (non-fatal): {e}"
        )


async def run():
    """Вызывает все idempotent DDL-блоки в исходном порядке (см. app/__init__.py.lifespan до разрезания)."""
    await _phase22_bank_payments_hash_migration()
    await _phase26_dd_contract_items_fk()
    await _phase27_1_contract_items_table()
    await _phase26_bb_purchase_items_receipt_id()
    await _phase26_u3_vat_columns()
    await _phase26_yy_snapshot_hash_column()
    await _phase29_vehicles_fleet_schema()
    await _phase30_schema_bootstrap()
    await _phase12_05_effective_date_column()
    await _fcat_b1_feo_category_id_column()
    await _import_vat_cols_vat_amount_column()
    await _import_vat_cols_total_with_vat_column()
    await _sn_ux_service_note_to_user_id_column()
    await _feo_reorder_sort_order_column()
    await _b9_wish_items_feo_category_column()
    await _b_event_wishes_event_id_column()
    await _b_exec_wishes_execution_columns()
    await _contractor_card_columns()
