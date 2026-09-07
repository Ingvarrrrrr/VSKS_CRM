import { describe, it, expect } from 'vitest'
import * as purchaseStatus from '../purchaseStatus'
import dictionaries from '@/data/dictionaries.json'

// Правило №6 (2026-09-07): purchaseStatus.ts стал ГЕНЕРИРУЕМЫМ файлом — значения
// (label) читаются из frontend/src/data/dictionaries.json, который скрипт
// backend/scripts/export_dictionaries.py собирает из бэкенда. Этот файл
// проверяет, что публичный API модуля (имена экспортов, набор ключей статусов)
// НЕ поменялся при рефакторинге — потребители (OrdersView.vue, PlanView.vue,
// DashboardView.vue и т.д.) продолжают импортировать те же имена.

describe('purchaseStatus.ts — снимок публичного API (не менять при рефакторинге)', () => {
  it('экспортирует ровно тот же набор имён, что и до генерации из JSON', () => {
    expect(Object.keys(purchaseStatus).sort()).toEqual([
      'PURCHASE_STATUS_META',
      'PURCHASE_STATUS_ORDER',
      'contractTypeLabel',
      'purchaseBasisLabel',
      'purchaseMethodLabel',
      'purchaseStatusColor',
      'purchaseStatusIcon',
      'purchaseStatusLabel',
      'purchaseStatusOrder',
      'purchaseSubstatusLabel',
    ])
  })

  it('PURCHASE_STATUS_ORDER — ровно 7 статусов жизненного цикла закупки, в порядке из backend/app/routers/purchases.py::STATUS_ORDER', () => {
    expect(purchaseStatus.PURCHASE_STATUS_ORDER).toEqual([
      'wishes', 'plan_schedule', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid',
    ])
  })

  it('каждый статус из PURCHASE_STATUS_META имеет непустые label/color/icon и числовой order', () => {
    for (const key of purchaseStatus.PURCHASE_STATUS_ORDER) {
      const meta = purchaseStatus.PURCHASE_STATUS_META[key]
      expect(meta, `нет meta для статуса "${key}"`).toBeDefined()
      if (!meta) continue
      expect(meta.label).toBeTruthy()
      expect(meta.color).toMatch(/^#[0-9A-Fa-f]{6}$/)
      expect(meta.icon).toMatch(/^mdi-/)
      expect(typeof meta.order).toBe('number')
    }
  })

  it('label статусов — байт-в-байт из dictionaries.json (единый источник, бэкенд)', () => {
    for (const s of dictionaries.statuses) {
      expect(purchaseStatus.purchaseStatusLabel(s.key)).toBe(s.label)
    }
  })

  it('покрывает все подстатусы/способы закупки/основания/типы договора из JSON без "сырых" ключей', () => {
    for (const s of dictionaries.substatuses) expect(purchaseStatus.purchaseSubstatusLabel(s.key)).toBe(s.label)
    for (const m of dictionaries.purchase_methods) expect(purchaseStatus.purchaseMethodLabel(m.key)).toBe(m.label)
    for (const b of dictionaries.purchase_bases) expect(purchaseStatus.purchaseBasisLabel(b.key)).toBe(b.label)
    for (const t of dictionaries.contract_types) expect(purchaseStatus.contractTypeLabel(t.key)).toBe(t.label)
  })

  it('неизвестный ключ возвращается как есть (фолбэк), а не падает', () => {
    expect(purchaseStatus.purchaseStatusLabel('__unknown__')).toBe('__unknown__')
    expect(purchaseStatus.purchaseSubstatusLabel('__unknown__')).toBe('__unknown__')
    expect(purchaseStatus.purchaseMethodLabel('__unknown__')).toBe('__unknown__')
  })
})
