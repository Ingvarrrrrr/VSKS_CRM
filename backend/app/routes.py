"""Регистрация всех APIRouter'ов на приложении, в фиксированном порядке.

Перенесено из app/__init__.py при разрезании монолитного файла на модули
(Правило №5). Порядок app.include_router(...) сохранён БАЙТ-В-БАЙТ —
многие специфичные суб-роутеры обязаны регистрироваться ДО роутеров с
catch-all путями (`/{id}`), иначе FastAPI отдаёт специфичный путь
catch-all'у. Комментарии про это сохранены на своих местах.
"""
from fastapi import FastAPI

from app.routers import (
    auth, users, contractors, contracts, purchases, payments,
    feo_categories, dashboard, subsidies, products, purchase_files,
    documents, publications, subsidy_approvers, responsible_persons,
    commercial_requests, suppliers, purchase_events, user_hierarchy,
    system_incidents, organizations, reports, events, purchase_approvals,
    tasks, departments, delivery_addresses, hierarchy, billing,
    wishes, purchase_export, purchase_items_import, purchase_members,
    permissions as permissions_router,
    staff_directory,
)
# Разрезание purchase_items_import.py (Правило №5, сессия 2026-09-08): mapped-,
# smart- и FEO-import вынесены в соседние роутеры на том же префиксе
# /api/purchases. Все пути литеральные или минимум на 2 сегмента длиннее
# catch-all "/{pid}" purchases.router — порядок регистрации относительно него
# и друг друга не важен, регистрируются рядом с purchase_items_import.router.
from app.routers import purchase_items_import_mapped
from app.routers import purchase_items_import_smart
from app.routers import purchase_items_import_feo
# Разрезание subsidies.py (Правило №5, сессия 2026-09-07): subsidy_templates,
# subsidy_plan_graph_compare, subsidy_plan_graph_versions, subsidy_plan_graph_export,
# subsidy_finance содержат ТОЛЬКО статические/специфичные литеральные пути на
# префиксе /api/subsidies ("/global-templates/{doc_type}", "/templates/normalize-all",
# ".../versions/compare", ".../versions/export-multi.xlsx", ".../plan-graph/export",
# "/payment-summary", "/financial-plan" и т.д.) — регистрируются РЯДОМ с
# subsidies.router и ДО него (как purchase_* перед purchases.router ниже).
# subsidy_plan_graph_compare — ДО subsidy_plan_graph_versions: ".../versions/compare"
# и ".../versions/export-multi.xlsx" не должны перехватываться int-конвертером
# ".../versions/{version_id:int}" из versions-роутера.
from app.routers import subsidy_templates
from app.routers import subsidy_plan_graph_compare
from app.routers import subsidy_plan_graph_versions
from app.routers import subsidy_plan_graph_export
from app.routers import subsidy_finance
# Разрезание products.py (Правило №5, сессия 2026-09-08): products_summary
# несёт GET "/summary" — ОДИН литеральный сегмент, ОБЯЗАН регистрироваться
# ДО products.router (несёт GET "/{product_id}" без явного int-конвертера в
# строке пути — совпадает по форме с любым односегментным литералом, иначе
# Starlette матчит "/summary" на catch-all первым и FastAPI падает 422).
# products_match (POST /match, /deduplicate), products_photos (фото),
# products_import (шаблон/импорт/bulk-from-purchase-items), products_price
# (share-price/price-actualization/price-history/verify-tz) конфликтов по
# форме не несут (POST/DELETE-литералы или минимум на сегмент длиннее
# catch-all) — регистрируются рядом для единообразия со всеми products_*
# соседями.
from app.routers import products_summary
from app.routers import products_match
from app.routers import products_photos
from app.routers import products_import
from app.routers import products_price
# Разрезание feo_categories.py (Правило №5, сессия 2026-09-07): feo_plan_reads,
# feo_import, feo_tree_ops содержат ТОЛЬКО статические/литеральные пути на
# префиксе /api/feo-categories (feo_plan_reads/feo_import — без {cat_id} вовсе;
# feo_tree_ops — "/{cat_id}/<literal>", минимум на сегмент длиннее catch-all) —
# регистрируются рядом с feo_categories.router и ДО него (как subsidy_* выше).
from app.routers import feo_plan_reads
from app.routers import feo_import
from app.routers import feo_tree_ops
# Разрезание purchases.py (Правило №5, сессия 2026-09-06): purchase_duplicates,
# purchase_lists, purchase_payment_matching, purchase_ops содержат статические
# литеральные пути ("/duplicate-check", "/my-tasks", "/payment-groups",
# "/bulk" и т.д.) на префиксе /api/purchases — ОБЯЗАНЫ регистрироваться ДО
# purchases.router (несёт catch-all "/{pid}" без явного int-конвертера в
# строке пути; Starlette матчит первый подходящий по форме путь, а не по
# типу параметра) — иначе тот перехватывает эти литералы и падает 422.
# purchase_items_edit и purchase_comments путей вида "/{pid}" НЕ имеют
# (минимум 2 сегмента сверх pid) — порядок относительно purchases.router
# для них не важен.
from app.routers import purchase_duplicates
from app.routers import purchase_lists
from app.routers import purchase_payment_matching
from app.routers import purchase_ops
from app.routers import purchase_items_edit
from app.routers import purchase_comments
# purchase_import_template / purchase_import: разрезаны из purchase_export.py
# (Правило №5, рефакторинг 2026-09) — только статические пути /import*, не
# несут catch-all, порядок относительно purchases.router не важен; включены
# рядом с purchase_export.router ниже, там же, где раньше жил весь модуль.
from app.routers import purchase_import_template
from app.routers import purchase_import
from app.routers import wish_documents
from app.routers import wish_members as wish_members_router
from app.routers import subsidy_members as subsidy_members_router
from app.routers import wish_approvals as wish_approvals_router
# Разрезание wishes.py (Правило №5, сессия 2026-09-06, по образцу purchases.py →
# purchase_ops.py/purchase_*.py): wish_transitions/wish_convert/wish_export несут
# ТОЛЬКО пути "/{wish_id}/<literal segment>" (submit/approve/reject/status/stop/
# execution/convert/convert-to-advance-report/approve-distribution/export.xlsx) —
# минимум 2 сегмента сверх wish_id, поэтому не конфликтуют с catch-all "/{wish_id}"
# в wishes.router (GET/PUT/DELETE) независимо от порядка регистрации; включены
# рядом с wishes.router ниже для читаемости.
from app.routers import wish_transitions as wish_transitions_router
from app.routers import wish_convert as wish_convert_router
from app.routers import wish_export as wish_export_router
from app.routers import user_addresses as user_addresses_router
from app.routers import org_config
from app.routers import purchase_transitions
# Разрезание feo_planned_items.py (Правило №5, сессия 2026-09-08): matching несёт
# статические пути (product-hint/map/match/confirm-wish-plan-match), reports —
# статические + "/{item_id}/consumers" (на сегмент длиннее catch-all ядра) на
# префиксе /api/feo-planned-items — оба регистрируются рядом с
# feo_planned_items.router и ДО него (catch-all "/{item_id}" — PUT/DELETE),
# как feo_plan_reads/feo_import/feo_tree_ops выше.
from app.routers import feo_planned_items_matching
from app.routers import feo_planned_items_reports
from app.routers import feo_planned_items
from app.routers import plan_excess as plan_excess_router
from app.routers import telegram_webhook
# Отслеживание местоположения сотрудников (владелец, 2026-09): смены/точки +
# разовый запрос местоположения через мессенджер. Второй роутер тоже висит на
# префиксе /api/staff-location (см. staff_location_requests.py) — это отдельный
# APIRouter в отдельном файле (Правило модульности), не расширение первого.
from app.routers import staff_location as staff_location_router
from app.routers import staff_location_requests as staff_location_requests_router
from app.routers import settings as settings_router
from app.routers import chat as chat_router
from app.routers import push as push_router
from app.routers import purchase_receipts
# Разрезание purchase_receipts.py (Правило №5, сессия 2026-09-08): recompute/dedup,
# import (JSON/QR/QR-fetch) и PDF/PNG-экспорт вынесены в соседние роутеры на том же
# префиксе /api/purchases. Все пути минимум на 2 сегмента длиннее catch-all "/{pid}"
# purchases.router (например "/{pid}/receipts/import-json") — порядок регистрации
# относительно purchases.router и друг друга не важен, но регистрируются рядом с
# purchase_receipts.router (как purchase_* выше) для читаемости.
from app.routers import purchase_receipts_recompute
from app.routers import purchase_receipts_import
from app.routers import purchase_receipts_export
from app.routers import install as install_router
from app.routers import analytics as analytics_router
from app.routers import report_configs as report_configs_router
from app.routers import vehicles_dashboard, vehicles, vehicle_attachments, repair_attachments
from app.routers import vehicles_dashboard_drill, vehicles_dashboard_summary, vehicles_dashboard_fines
# Соседи dashboard.router после резки монолита 1641→core (Правило №5, 2026-09-08).
from app.routers import dashboard_charts, dashboard_analytics, dashboard_financial_plan, dashboard_financial_plan_export
from app.routers import vehicle_repairs, vehicle_odometer, fuel_logs, trips
from app.routers import external_drivers
from app.routers import vehicles_import as vehicles_import_router
from app.routers import vehicle_fields as vehicle_fields_router
from app.routers import body_type_icons as body_type_icons_router
from app.routers import vehicle_fines
from app.routers import fleet_documents as fleet_documents_router
from app.routers import checklists as checklists_router
from app.routers import incidents as incidents_router
from app.routers import vehicle_passes as vehicle_passes_router
from app.routers.documents import guide_router as documents_guide_router
# Phase 27.1: contract_items MUST be registered BEFORE purchases.router
# because purchases has catch-all /{purchase_id} that would intercept /contract-items
from app.routers import contract_items as contract_items_router
# bank_statements MUST be registered BEFORE payments.router:
# /imports and /registry/{id}/... must resolve before payments' catch-all /{pid}
from app.routers import bank_statements
from app.routers import price_freshness as price_freshness_router
# Специфичные суб-роутеры /api/tasks/* регистрируются ДО tasks.router,
# иначе catch-all `/{task_id}` ловит `/badges`, `/pending-consent`, `/report/*`
from app.routers import entity_changes as entity_changes_router
from app.routers import task_badges, task_delegation, task_reports, task_comments
from app.routers import exports as exports_router
from app.routers import okpd2 as okpd2_router
from app.routers import expense_codes as expense_codes_router
from app.routers import diag as diag_router
from app.routers import dictionaries as dictionaries_router
# Разрезание contractors.py (Правило №5, сессия 2026-09-08): contractors_directory,
# contractors_lookup, contractors_enrich, contractors_import несут доп. эндпоинты
# на префиксе /api/contractors. contractors_directory ОБЯЗАН регистрироваться ДО
# contractors.router — его GET /product-categories, /with-stats, /duplicates-by-inn
# односегментные и совпадают по форме с GET /{cid} core-роутера (int-конвертация
# {cid} происходит уже ПОСЛЕ того, как Starlette матчит маршрут по форме пути, а не
# по типу параметра — регистрация раньше literal-путей обязательна, иначе 422).
# contractors_lookup/contractors_enrich/contractors_import конфликтов по форме не
# несут (минимум 2 сегмента либо другой метод), регистрируются рядом для единообразия.
from app.routers import contractors_directory
from app.routers import contractors_lookup
from app.routers import contractors_enrich
from app.routers import contractors_import
# Разрезание users.py (Правило №5, сессия 2026-09-08): users_access, users_me
# несут статические литеральные пути на префиксе /api/users (/assignable-ids,
# /in-my-orgs, /i-can-act-for, /me...) — ОБЯЗАНЫ регистрироваться ДО
# users.router, иначе Starlette матчит их на catch-all GET /{user_id} (int)
# раньше и FastAPI падает 422. users_docs, users_platform_credentials,
# users_dictionaries, users_import конфликтов по форме не несут (минимум на
# сегмент длиннее /{user_id} или другой метод), регистрируются рядом для
# единообразия со всеми users_* siblings.
from app.routers import users_access
from app.routers import users_me
from app.routers import users_docs
from app.routers import users_platform_credentials
from app.routers import users_dictionaries
from app.routers import users_import


def register_routes(app: FastAPI) -> None:
    app.include_router(auth.router)
    # Статические/специфичные пути /api/users/* — ДО users.router (см.
    # комментарий у импортов выше); users_access/users_me обязательны здесь,
    # остальные — для единообразия со всеми users_* siblings.
    app.include_router(users_access.router)
    app.include_router(users_me.router)
    app.include_router(users.router)
    app.include_router(users_docs.router)
    app.include_router(users_platform_credentials.router)
    app.include_router(users_dictionaries.router)
    app.include_router(users_import.router)
    app.include_router(staff_directory.router)
    # Статические/специфичные пути /api/contractors/* — ДО contractors.router
    # (см. комментарий у импортов выше); contractors_directory обязателен здесь,
    # остальные — для единообразия со всеми contractors_* siblings.
    app.include_router(contractors_directory.router)
    app.include_router(contractors_lookup.router)
    app.include_router(contractors_enrich.router)
    app.include_router(contractors_import.router)
    app.include_router(contractors.router)
    app.include_router(contracts.router)
    # Phase 27.1: contract_items MUST be registered BEFORE purchases.router
    # because purchases has catch-all /{purchase_id} that would intercept /contract-items
    app.include_router(contract_items_router.router)
    # Статические литеральные пути /api/purchases/* — ДО purchases.router
    # (catch-all "/{pid}"), см. комментарий у импортов выше.
    app.include_router(purchase_duplicates.router)
    app.include_router(purchase_lists.router)
    app.include_router(purchase_payment_matching.router)
    app.include_router(purchase_ops.router)
    app.include_router(purchases.router)
    app.include_router(purchase_items_edit.router)
    app.include_router(purchase_comments.router)
    app.include_router(purchase_receipts_recompute.router)
    app.include_router(purchase_receipts.router)
    app.include_router(purchase_receipts_import.router)
    app.include_router(purchase_receipts_export.router)
    app.include_router(install_router.router, prefix="/api")
    # bank_statements MUST be registered BEFORE payments.router:
    # /imports and /registry/{id}/... must resolve before payments' catch-all /{pid}
    app.include_router(bank_statements.router)
    app.include_router(payments.router)
    # Разрезание feo_categories.py (Правило №5, 2026-09-07) — см. комментарий у
    # импортов выше про порядок: статичные ДО feo_categories.router (catch-all
    # GET/PUT/DELETE "/{cat_id}").
    app.include_router(feo_plan_reads.router)
    app.include_router(feo_import.router)
    app.include_router(feo_tree_ops.router)
    app.include_router(feo_categories.router)
    app.include_router(feo_planned_items_matching.router)
    app.include_router(feo_planned_items_reports.router)
    app.include_router(feo_planned_items.router)
    app.include_router(plan_excess_router.router)
    app.include_router(settings_router.router)
    app.include_router(dashboard.router)
    # Соседи dashboard.router после резки монолита 1641→core (Правило №5, 2026-09-08):
    # тот же префикс /api/dashboard, все пути статические (нет /{id}) — порядок не критичен.
    app.include_router(dashboard_charts.router)             # /api/dashboard (charts)
    app.include_router(dashboard_analytics.router)           # /api/dashboard (analytics)
    app.include_router(dashboard_financial_plan.router)       # /api/dashboard (financial-plan, financial-plan/details)
    app.include_router(dashboard_financial_plan_export.router)  # /api/dashboard (financial-plan/export.xlsx, .../details/export.xlsx)
    # Разрезание subsidies.py (Правило №5, 2026-09-07) — см. комментарий у импортов
    # выше про порядок: statics/compare ДО subsidies.router (catch-all "/{subsidy_id}").
    app.include_router(subsidy_templates.router)
    app.include_router(subsidy_plan_graph_compare.router)
    app.include_router(subsidy_plan_graph_versions.router)
    app.include_router(subsidy_plan_graph_export.router)
    app.include_router(subsidy_finance.router)
    app.include_router(subsidies.router)
    app.include_router(subsidy_members_router.router)
    # Разрезание products.py (Правило №5, 2026-09-08) — см. комментарий у
    # импортов выше про порядок: products_summary ДО products.router (catch-all
    # "/{product_id}"); products_match/products_photos/products_import/
    # products_price — рядом, конфликтов по форме нет.
    app.include_router(products_summary.router)
    app.include_router(products_match.router)
    app.include_router(products_photos.router)
    app.include_router(products_import.router)
    app.include_router(products_price.router)
    app.include_router(products.router)
    app.include_router(price_freshness_router.router)
    app.include_router(purchase_files.router)
    app.include_router(documents.router)
    app.include_router(documents_guide_router)
    app.include_router(publications.router)
    app.include_router(subsidy_approvers.router)
    app.include_router(responsible_persons.router)
    app.include_router(commercial_requests.router)
    app.include_router(suppliers.router)
    # purchase_members.router несёт GET/POST /{pid}/members + DELETE
    # /{pid}/members/{user_id} (перенесены из purchases.py, сессия 2026-09-06).
    # purchase_events.router НИЖЕ определяет ТЕ ЖЕ ТРИ пути (пред-существующий
    # дубль, list_members/add_member/remove_member) — раньше выигрывали
    # purchases.py-версии, т.к. purchases.router стоял РАНЬШЕ purchase_events.router
    # в этом файле; сохраняем то же старшинство явным порядком здесь, иначе после
    # переноса в отдельный файл purchase_events.router оказался бы первым и начал
    # реально отвечать на эти пути вместо purchases.py-версии (поведенческий
    # регресс, найден при сверке OpenAPI-снапшота до/после разрезания).
    app.include_router(purchase_members.router)
    app.include_router(purchase_events.router)
    app.include_router(user_hierarchy.router)
    app.include_router(system_incidents.router)
    app.include_router(organizations.router)
    app.include_router(reports.router)
    app.include_router(events.router)
    app.include_router(purchase_approvals.router)
    app.include_router(purchase_export.router)
    app.include_router(purchase_import_template.router)
    app.include_router(purchase_import.router)
    app.include_router(purchase_items_import.router)
    app.include_router(purchase_items_import_mapped.router)
    app.include_router(purchase_items_import_smart.router)
    app.include_router(purchase_items_import_feo.router)
    app.include_router(purchase_transitions.router)
    # Специфичные суб-роутеры /api/tasks/* регистрируются ДО tasks.router,
    # иначе catch-all `/{task_id}` ловит `/badges`, `/pending-consent`, `/report/*`
    app.include_router(entity_changes_router.router)  # /api/entity-changes (Phase 31 diff-tracking)
    app.include_router(task_badges.router)
    app.include_router(task_delegation.router)
    app.include_router(task_reports.router)
    app.include_router(task_comments.router)
    app.include_router(tasks.router)
    app.include_router(departments.router)
    app.include_router(delivery_addresses.router)
    app.include_router(org_config.router)
    app.include_router(hierarchy.router)
    app.include_router(billing.router)
    app.include_router(telegram_webhook.router)
    app.include_router(staff_location_router.router)           # /api/staff-location (смены, точки, трек)
    app.include_router(staff_location_requests_router.router)  # /api/staff-location/requests, /roster
    app.include_router(chat_router.router)    # REST: /api/chat/...
    app.include_router(chat_router.ws_router)  # WS: /api/ws/chat
    # Specific sub-router /api/wishes/*/documents/* registered BEFORE wishes.router
    # so the specific path resolves before the catch-all /{wish_id} in wishes.router
    # (same ordering principle as task_badges/task_delegation before tasks.router, commit 3d37cf9)
    app.include_router(wish_documents.router)
    # wish_members.pending_router (/api/wishes/members/pending-consent) MUST be before wishes.router
    # to avoid /{wish_id:int} swallowing the static "members" segment.
    app.include_router(wish_members_router.pending_router)
    app.include_router(wish_members_router.router)
    # wish_approvals (/api/wishes/{wid}/approvers/*) MUST be before wishes.router
    # so static "approvers" segment resolves before the catch-all /{wish_id:int}.
    app.include_router(wish_approvals_router.router)
    # wish_transitions/wish_convert/wish_export — разрезаны из wishes.py, см.
    # комментарий у импортов выше; порядок относительно wishes.router не важен
    # (их пути минимум на 1 сегмент длиннее catch-all "/{wish_id}"), регистрируем
    # рядом для читаемости.
    app.include_router(wish_transitions_router.router)
    app.include_router(wish_convert_router.router)
    app.include_router(wish_export_router.router)
    app.include_router(wishes.router)
    app.include_router(push_router.router)
    app.include_router(permissions_router.router)
    app.include_router(user_addresses_router.router)
    app.include_router(analytics_router.router)
    app.include_router(report_configs_router.router)

    # Phase 29: vehicle fleet routers
    # vehicles_dashboard (/api/vehicles-dashboard) и external_drivers.drivers_router (/api/drivers)
    # регистрируются ПЕРЕД vehicles.router (/api/vehicles/{vehicle_id:int}) — Gotcha 2026-04-20 FastAPI routing
    app.include_router(vehicles_dashboard.router)          # /api/vehicles-dashboard
    # Соседи vehicles_dashboard.router после резки монолита (Правило №5, 2026-09-08):
    # тот же префикс /api/vehicles-dashboard, все пути статические (нет /{id}) —
    # порядок регистрации друг относительно друга не важен для роутинга.
    app.include_router(vehicles_dashboard_drill.router)     # /api/vehicles-dashboard (drill, expiring-docs-drill)
    app.include_router(vehicles_dashboard_summary.router)   # /api/vehicles-dashboard (all-vehicles-summary, by-region, driver-reports, filter-counts)
    app.include_router(vehicles_dashboard_fines.router)     # /api/vehicles-dashboard (fine-leaders, fines-summary, fines-by-filial)
    app.include_router(external_drivers.drivers_router)    # /api/drivers/available
    app.include_router(external_drivers.router)            # /api/external-drivers
    app.include_router(vehicles_import_router.router)      # /api/vehicles-import (BEFORE vehicles catch-all)
    app.include_router(vehicles_import_router.vehicles_template_router)  # /api/vehicles/import-template (BEFORE vehicles catch-all)
    app.include_router(vehicle_fields_router.router)       # /api/vehicle-fields (Автоблок §4)
    app.include_router(body_type_icons_router.router)      # /api/body-type-icons (редактор значков кузова, 2026-09)
    app.include_router(vehicles.router)                    # /api/vehicles (catch-all /{vehicle_id:int})
    app.include_router(vehicle_attachments.router)         # /api/vehicle-attachments
    app.include_router(repair_attachments.router)          # /api/repair-attachments
    app.include_router(vehicle_repairs.router)             # /api/vehicle-repairs
    app.include_router(vehicle_odometer.router)            # /api/vehicle-odometer
    app.include_router(fuel_logs.router)                   # /api/fuel-logs
    app.include_router(trips.router)                       # /api/trips
    app.include_router(vehicle_fines.router)               # /api/vehicle-fines
    app.include_router(vehicle_passes_router.router)       # /api/vehicle-passes (2026-09)
    app.include_router(fleet_documents_router.router)      # /api/fleet-documents
    app.include_router(checklists_router.router)           # /api/checklists
    app.include_router(incidents_router.router)            # /api/incidents
    app.include_router(exports_router.router)              # /api/exports
    app.include_router(okpd2_router.router)                # /api/okpd2
    app.include_router(expense_codes_router.router)         # /api/expense-codes

    app.include_router(diag_router.router)                 # /api/diag/*
    app.include_router(dictionaries_router.router)         # /api/dictionaries/purchase (Правило №6)
