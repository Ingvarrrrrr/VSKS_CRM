// contractsLabels.ts — справочники типов/способов/статусов договора и мелкие
// форматтеры. Дословный перенос из ContractsView.vue (ПРАВИЛО №6: свои
// списки типов/способов договора — отдельное решение владельца, не трогать).
import { toAmount } from '@/types/purchaseAmounts'
import type { Purchase } from './contractsTypes'

export const contractTypeItems = [
  { value: 'single',                label: 'Разовая поставка' },
  { value: 'framework_cumulative',  label: 'Рамочный (нарастающий итог)' },
  { value: 'framework_with_amount', label: 'Рамочный (с суммой)' },
  { value: 'invoice',               label: 'Счёт' },
  { value: 'invoice_contract',      label: 'Счёт-договор' },
  { value: 'advance_report',        label: 'Авансовый платёж' },
]
export const purchaseMethodItems = [
  { value: 'single',      label: 'Единственный поставщик' },
  { value: 'competitive', label: 'Конкурсная процедура' },
  { value: 'advance',     label: 'Авансовый платёж' },
]
export const statusItems = [
  { value: 'active', label: 'Активен' },
  { value: 'closed', label: 'Закрыт' },
]

export const contractTypeLabel = (t?: string) => contractTypeItems.find(i => i.value === t)?.label || t || '—'
export const purchaseMethodLabel = (m?: string) => purchaseMethodItems.find(i => i.value === m)?.label || m || '—'
export const statusLabel = (s?: string) => statusItems.find(i => i.value === s)?.label || s || '—'

export const contractTypeLabels = Object.fromEntries(contractTypeItems.map(i => [i.value, i.label]))
export const purchaseMethodLabels = Object.fromEntries(purchaseMethodItems.map(i => [i.value, i.label]))
export const statusLabels = Object.fromEntries(statusItems.map(i => [i.value, i.label]))

export const contractTypeColor = (t?: string) => {
  if (t === 'single') return 'blue'
  if (t?.startsWith('framework')) return 'orange'
  if (t === 'invoice' || t === 'invoice_contract') return 'teal'
  if (t === 'advance_report') return 'purple'
  return 'grey'
}

export const isExpired = (d: string) => new Date(d) < new Date()
export const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('ru-RU') : '—'
export const formatMoney = (v: number | string) =>
  Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ₽'
// ПРАВИЛО №6 (2026-09-05/06): amounts.effective приходит с бэкенда JSON-строкой
// (Decimal) — toAmount() в одном месте вместо повторного parseFloat в шаблоне.
export const purchaseEffectiveAmount = (p: Purchase): number | null => toAmount(p.amounts?.effective)
export const isFrameworkContract = (c: any): boolean =>
  c?.contract_type === 'framework_cumulative' || c?.contract_type === 'framework_non_cumulative'
