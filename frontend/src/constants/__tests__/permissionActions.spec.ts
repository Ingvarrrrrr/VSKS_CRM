import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { ACTIONS } from '../permissionActions'
import dictionaries from '@/data/dictionaries.json'

// Правило №6 (2026-09-07): каждый литерал 'x.y', переданный в hasAction()/can(),
// обязан существовать как ключ действия на бэкенде (permission_actions в
// dictionaries.json ← backend/app/startup/permission_seeds.py). Если тест упал
// на НОВОМ литерале — либо это опечатка, либо сначала нужно завести сид в
// permission_seeds.py и перегенерировать JSON, а не выдумывать ключ на фронте.
//
// KNOWN_GAPS — задокументированное исключение (см. отчёт агента K3, сессия
// 2026-09-07): эти action_key реально существуют и гейтят бэкенд, но заведены
// НЕ через permission_seeds.py (значит, export_dictionaries.py их не видит):
//   - 'publication.create', 'purchase_files.upload' — через alembic-миграции
//     (baseline / perm_seed_hotfix.sql), которые не переразбираются задним числом.
//   - 'subsidy.edit' — заведён через исходную alembic-миграцию системы прав
//     (q4r5s6t7u8v9_add_permission_system.py / perm_seed_hotfix.sql), не через
//     permission_seeds.py; используется в SubsidiesView.vue (запрещённый для
//     правки файл этой сессии) и SubsidyMembersDialog.vue.
// 'staff.location.view' исключён из этого списка 2026-09-07: заведён сидом
// _staff_location_view_action() в permission_seeds.py (дефект D3 починен),
// теперь присутствует в dictionaries.json как обычный сидированный ключ.
// Если один из оставшихся ключей появится в permission_actions после
// сидирования — уберите его из KNOWN_GAPS, иначе тест перестанет ловить
// реальные дефекты.
const KNOWN_GAPS = new Set(['publication.create', 'purchase_files.upload', 'subsidy.edit'])

const repoRoot = path.resolve(fileURLToPath(import.meta.url), '../../../../../')
const srcDir = path.join(repoRoot, 'frontend', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (entry === 'node_modules' || entry === '__tests__') continue
      walk(full, out)
    } else if (/\.(vue|ts)$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

// hasAction('x.y') / can('x.y') / hasAction("x.y") — только буквальные строки,
// не переменные (authStore.hasAction(someVar) не ловим — это не наш случай).
const CALL_RE = /\b(?:hasAction|can)\(\s*['"]([a-z][a-z0-9_.]*\.[a-z0-9_.]+)['"]/g

function findLiteralActionKeys(): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const file of walk(srcDir)) {
    const rel = path.relative(repoRoot, file).replace(/\\/g, '/')
    const content = readFileSync(file, 'utf-8')
    for (const match of content.matchAll(CALL_RE)) {
      const key = match[1]!
      if (!found.has(key)) found.set(key, [])
      found.get(key)!.push(rel)
    }
  }
  return found
}

describe('permission action-литералы во frontend/src — все присутствуют в dictionaries.json (Правило №6)', () => {
  const seededKeys = new Set((dictionaries.permission_actions as { key: string }[]).map(a => a.key))
  const literalKeys = findLiteralActionKeys()

  it('dictionaries.json содержит хотя бы один action (сиды не пустые)', () => {
    expect(seededKeys.size).toBeGreaterThan(0)
  })

  it('каждый литерал hasAction(...)/can(...) по всему frontend/src либо сидирован, либо в KNOWN_GAPS', () => {
    const unexplained: string[] = []
    for (const [key, files] of literalKeys) {
      if (seededKeys.has(key) || KNOWN_GAPS.has(key)) continue
      unexplained.push(`'${key}' (${files.join(', ')})`)
    }
    expect(
      unexplained,
      `Найдены action-литералы без сида в permission_seeds.py и без записи в KNOWN_GAPS: ${unexplained.join('; ')}`
    ).toEqual([])
  })

  it('KNOWN_GAPS не устарел — ни один из них уже не сидирован (иначе уберите его из списка)', () => {
    const stale = [...KNOWN_GAPS].filter(k => seededKeys.has(k))
    expect(stale, `Эти ключи уже сидированы — уберите из KNOWN_GAPS и замените литерал на ACTIONS.xxx: ${stale.join(', ')}`).toEqual([])
  })

  it('ACTIONS.xxx резолвится ровно в тот же ключ (по всем сидированным actions)', () => {
    for (const a of dictionaries.permission_actions as { key: string }[]) {
      const constName = a.key.toUpperCase().replace(/[.\-]/g, '_')
      expect(ACTIONS[constName], `ACTIONS.${constName} не найден для action_key '${a.key}'`).toBe(a.key)
    }
  })
})
