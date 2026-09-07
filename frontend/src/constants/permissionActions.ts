/**
 * Ключи permission-действий/вкладок (Правило №6). Источник —
 * backend/app/startup/permission_seeds.py, выгружен скриптом
 * backend/scripts/export_dictionaries.py в frontend/src/data/dictionaries.json
 * (permission_actions/permission_tabs). НЕ писать новый литерал 'x.y' в
 * hasAction()/can() — использовать ACTIONS.xxx отсюда; если ключа ещё нет —
 * сперва завести сид в permission_seeds.py, перегенерировать JSON, и только
 * потом добавить сюда/использовать.
 *
 * Известное ограничение (см. отчёт K3, сессия 2026-09-07): часть реально
 * существующих action_key заведена через alembic-миграции (baseline/
 * perm_seed_hotfix.sql), а не через permission_seeds.py, и здесь отсутствует —
 * 'publication.create', 'purchase_files.upload'. Использующий их код
 * (CreateOrderView.vue, usePurchaseMembers.ts) продолжает вызывать
 * hasAction('publication.create'|'purchase_files.upload') строкой — не
 * заменено на ACTIONS.xxx, т.к. константы здесь не существует (см. отчёт).
 */
import dictionaries from '@/data/dictionaries.json'

type ActionEntry = { key: string; description: string }
type TabEntry = { key: string; title: string }

function toConstKey(actionKey: string): string {
  return actionKey.toUpperCase().replace(/[.\-]/g, '_')
}

const actionEntries = dictionaries.permission_actions as ActionEntry[]
const tabEntries = dictionaries.permission_tabs as TabEntry[]

/** ACTIONS.VEHICLE_EDIT === 'vehicle.edit', и т.д. — по одному имени на каждый
 * сидированный action_key (см. permission_seeds.py). */
export const ACTIONS: Record<string, string> = Object.fromEntries(
  actionEntries.map(a => [toConstKey(a.key), a.key])
)

/** TABS.VEHICLES === 'vehicles', и т.д. — по одному имени на каждый сидированный tab_key. */
export const TABS: Record<string, string> = Object.fromEntries(
  tabEntries.map(t => [toConstKey(t.key), t.key])
)

export const ACTION_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  actionEntries.map(a => [a.key, a.description])
)

export const TAB_TITLES: Record<string, string> = Object.fromEntries(
  tabEntries.map(t => [t.key, t.title])
)
