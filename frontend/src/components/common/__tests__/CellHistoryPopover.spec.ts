// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createApp, nextTick, defineComponent, computed, ref, watch } from 'vue'
import fs from 'node:fs'
import path from 'node:path'
import {
  avatarColor,
  avatarLetter,
  formatRussianDate,
  formatCellValue,
  fetchCellHistory,
} from '@/composables/useCellHistory'
import {
  useGalaContextMenu,
  extractNumericValue,
  type CellHistoryEvent,
} from '@/composables/useGalaContextMenu'
import {
  useCellMarks,
  MARK_COLOR_PALETTE,
  type CellTarget,
  type CellMarkRecord,
} from '@/composables/useCellMarks'
import { useUniversalTableContext } from '@/composables/useUniversalTableContext'

// Mock apiFetch
vi.mock('@/api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '@/api'

describe('CellHistoryPopover helpers and composables', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('avatarLetter and avatarColor', () => {
    it('returns uppercase initial of author name', () => {
      expect(avatarLetter('Игорь Цыганов')).toBe('И')
      expect(avatarLetter('  alex  ')).toBe('A')
      expect(avatarLetter('')).toBe('С')
    })

    it('returns a valid color from palette deterministically', () => {
      const c1 = avatarColor('Игорь Цыганов')
      const c2 = avatarColor('Игорь Цыганов')
      expect(c1).toBe(c2)
      expect(c1).toMatch(/^#[0-9A-Fa-f]{6}$/)
    })
  })

  describe('formatRussianDate', () => {
    it('formats valid date string and handles empty', () => {
      const res = formatRussianDate('2026-10-23T15:11:00Z')
      expect(res).toBeTruthy()
      expect(res).toContain('11')
      expect(formatRussianDate('')).toBe('')
      expect(formatRussianDate(undefined)).toBe('')
    })
  })

  describe('formatCellValue', () => {
    it('formats null / undefined / empty as em-dash', () => {
      expect(formatCellValue(null)).toBe('—')
      expect(formatCellValue('')).toBe('—')
      expect(formatCellValue('None')).toBe('—')
    })

    it('formats booleans to Да / Нет', () => {
      expect(formatCellValue(true)).toBe('Да')
      expect(formatCellValue('true')).toBe('Да')
      expect(formatCellValue(false)).toBe('Нет')
      expect(formatCellValue('false')).toBe('Нет')
    })

    it('formats FEO fields and numbers correctly', () => {
      const optsMoney = { entityType: 'feo_item', entityId: 1, fieldName: 'amount', fieldLabel: 'Сумма' }
      const res = formatCellValue('1500', optsMoney)
      expect(res).toContain('1')
      expect(res).toContain('500')
      expect(res).toContain('₽')
      const optsQty = { entityType: 'feo_item', entityId: 1, fieldName: 'quantity', fieldLabel: 'Количество' }
      expect(formatCellValue('2.000', optsQty)).toBe('2')
      expect(formatCellValue(10000)).toMatch(/10[\s\u00A0]000/)
    })
  })

  describe('extractNumericValue', () => {
    it('extracts number from formatted strings and currency', () => {
      expect(extractNumericValue('1 250 400.50 ₽')).toBe('1250400.5')
      expect(extractNumericValue('500,25')).toBe('500.25')
      expect(extractNumericValue(42)).toBe('42')
      expect(extractNumericValue('   100 % ')).toBe('100')
      expect(extractNumericValue('не число')).toBeNull()
      expect(extractNumericValue(null)).toBeNull()
    })
  })

  describe('fetchCellHistory', () => {
    it('returns calculated event for table_row, empty or 0 entityId', async () => {
      const res = await fetchCellHistory({
        entityType: 'table_row',
        entityId: 0,
        fieldName: 'total',
        fieldLabel: 'Итого',
        cellValue: '100 000 ₽',
      })
      expect(res).toHaveLength(1)
      expect(res[0]!.isCalculatedOrEmpty).toBe(true)
      expect(res[0]!.originLabel).toContain('Расчётная')
    })

    it('fetches vehicle field history and maps changed_by_name', async () => {
      const mockApiFetch = vi.mocked(apiFetch)
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 42,
          vehicle_id: 1,
          field_key: 'mileage',
          old_value: '1000',
          new_value: '2000',
          changed_at: '2026-10-23T12:00:00Z',
          changed_by_name: 'Игорь Цыганов',
          comment: 'ТО-1',
        },
      ])

      const events = await fetchCellHistory({
        entityType: 'vehicle',
        entityId: 1,
        fieldName: 'mileage',
        fieldLabel: 'Пробег',
      })

      expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining('/vehicles/1/field-history?field_key=mileage'))
      expect(events).toHaveLength(1)
      expect(events[0]!.changedByName).toBe('Игорь Цыганов')
      expect(events[0]!.newValue).toBe('2000')
    })

    it('fetches entity changes and appends created as oldest event', async () => {
      const mockApiFetch = vi.mocked(apiFetch)
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 10,
          entity_type: 'purchase',
          entity_id: 100,
          field_name: 'subject',
          old_value: 'Старый договор',
          new_value: 'Новый договор',
          changed_by_name: 'Игорь Цыганов',
          changed_at: '2026-10-23T14:00:00Z',
        },
        {
          id: 1,
          entity_type: 'purchase',
          entity_id: 100,
          field_name: '__created__',
          changed_by_name: 'Импорт',
          changed_at: '2026-10-20T10:00:00Z',
          origin_label: 'Загружено из файла',
        },
      ])

      const events = await fetchCellHistory({
        entityType: 'purchase',
        entityId: 100,
        fieldName: 'subject',
        fieldLabel: 'Предмет',
      })

      expect(events).toHaveLength(2)
      expect(events[0]!.newValue).toBe('Новый договор')
      expect(events[1]!.isCreated).toBe(true)
      expect(events[1]!.newValue).toBe('Старый договор')
      expect(events[1]!.originLabel).toBe('Загружено из файла')
    })

    it('returns single created event with comment when no field changes exist', async () => {
      const mockApiFetch = vi.mocked(apiFetch)
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 1,
          entity_type: 'feo_item',
          entity_id: 5,
          field_name: '__created__',
          changed_by_name: 'Игорь Цыганов',
          changed_at: '2026-10-20T10:00:00Z',
          origin_label: 'Создано из заявки №275',
        },
      ])

      const events = await fetchCellHistory({
        entityType: 'feo_item',
        entityId: 5,
        fieldName: 'name',
        fieldLabel: 'Наименование',
        cellValue: 'Молоток слесарный',
      })

      expect(events).toHaveLength(1)
      expect(events[0]!.isCreated).toBe(true)
      expect(events[0]!.newValue).toBe('Молоток слесарный')
      expect(events[0]!.originLabel).toBe('Создано из заявки №275')
      expect(events[0]!.comment).toContain('не изменялась')
    })
  })

  describe('useGalaContextMenu', () => {
    it('manages context menu and history popover open/close state', () => {
      const menu = useGalaContextMenu()
      const fakeEvent = { clientX: 150, clientY: 250, preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as MouseEvent
      const options = { entityType: 'task', entityId: 77, fieldName: 'title', fieldLabel: 'Название', cellValue: 'Отчёт' }

      menu.openCellContextMenu(fakeEvent, options)
      expect(menu.isMenuOpen.value).toBe(true)
      expect(menu.menuPosition.value).toEqual({ x: 150, y: 250 })

      menu.openCellHistory()
      expect(menu.isMenuOpen.value).toBe(false)
      expect(menu.isHistoryOpen.value).toBe(true)

      menu.closeCellHistory()
      expect(menu.isHistoryOpen.value).toBe(false)
    })
  })

  describe('useCellMarks', () => {
    it('exports 6 palette colors and handles selection', () => {
      expect(MARK_COLOR_PALETTE).toHaveLength(6)
      const marks = useCellMarks()
      marks.clearSelection()
      const target: CellTarget = { entityType: 'order', entityId: 10, fieldName: 'amount' }
      const fakeEvent = { ctrlKey: true, metaKey: false, shiftKey: false, preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as MouseEvent

      expect(marks.handleCellSelectClick(fakeEvent, target)).toBe(true)
      expect(marks.isCellSelected('order', 10, 'amount')).toBe(true)
      marks.clearSelection()
      expect(marks.selectedTargets.value).toHaveLength(0)
    })

    it('loads marks and handles color filtering', async () => {
      const marks = useCellMarks()
      const mockApiFetch = vi.mocked(apiFetch)
      const mockData: CellMarkRecord[] = [{
        id: 1, group_id: 'grp_1', entity_type: 'order', entity_id: 99,
        field_name: 'price', color: 'red', comment: 'Проверить цену',
        visibility: 'shared', is_resolved: false, created_at: '2026-10-23T10:00:00Z',
      }]
      mockApiFetch.mockResolvedValueOnce(mockData)
      await marks.loadMarks('order', [99])

      expect(marks.getExactMark('order', 99, 'price')?.color).toBe('red')
      marks.setColorFilter('order', 'red')
      expect(marks.matchesColorFilter('order', 99)).toBe(true)
      marks.setColorFilter('order', 'purple')
      expect(marks.matchesColorFilter('order', 99)).toBe(false)
      marks.setColorFilter('order', null)
    })

    it('applies batch marks and clears color', async () => {
      const marks = useCellMarks()
      const mockApiFetch = vi.mocked(apiFetch)
      const target: CellTarget = { entityType: 'task', entityId: 55, fieldName: 'status' }

      mockApiFetch.mockResolvedValueOnce([])
      await marks.applyMarkBatch({ targets: [target], color: 'green', comment: 'Готово' })
      expect(marks.getMark('task', 55, 'status')?.color).toBe('green')

      mockApiFetch.mockResolvedValueOnce({})
      await marks.clearMarksColor([target])
      expect(marks.getExactMark('task', 55, 'status')?.color).toBeNull()
    })
  })

  describe('useUniversalTableContext', () => {
    it('ignores input elements and extracts formatted numeric values', () => {
      const { isInputOrExcluded } = useUniversalTableContext()
      const inp = document.createElement('input')
      const td = document.createElement('td')
      expect(isInputOrExcluded(inp)).toBe(true)
      expect(isInputOrExcluded(td)).toBe(false)
      expect(extractNumericValue('48 939,62 ₽')).toBe('48939.62')
      expect(extractNumericValue('без суммы')).toBeNull()
    })

    it('handles contextmenu event on td and opens context menu', () => {
      const { handleContextMenu } = useUniversalTableContext()
      const menu = useGalaContextMenu()
      const table = document.createElement('table')
      table.innerHTML = `<tbody><tr data-entity-type="contract" data-entity-id="42"><td>CTR-01</td><td>48 939,62 ₽</td></tr></tbody>`
      document.body.appendChild(table)
      const targetTd = table.querySelectorAll('td')[1]

      const evt = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 100, clientY: 200 })
      Object.defineProperty(evt, 'target', { value: targetTd })
      handleContextMenu(evt)

      expect(evt.defaultPrevented).toBe(true)
      expect(menu.isMenuOpen.value).toBe(true)
      expect(menu.activeCellOptions.value?.entityType).toBe('contract')
      expect(menu.activeCellOptions.value?.rawNumber).toBe('48939.62')

      menu.closeContextMenu()
      document.body.removeChild(table)
    })
  })

  describe('CellHistoryPopover component verification & rendering', () => {
    it('verifies CellHistoryPopover.vue source has withDefaults and modelValue: null fix', () => {
      const vueFilePath = path.resolve(__dirname, '../CellHistoryPopover.vue')
      const source = fs.readFileSync(vueFilePath, 'utf-8')
      expect(source).toContain('modelValue: null')
      expect(source).toContain('props.modelValue !== null && props.modelValue !== undefined')
      expect(source).toContain('z-index: 200001')
      expect(source).toContain('currentEvent.originLabel')
      expect(source).toContain('Изменений после внесения не было')
    })

    it('mounts without modelValue prop and opens popover via useGalaContextMenu', async () => {
      const { openCellHistory, closeCellHistory, isHistoryOpen, historyCellOptions } = useGalaContextMenu()
      const mockApiFetch = vi.mocked(apiFetch)

      mockApiFetch.mockResolvedValueOnce([
        {
          id: 101,
          entity_type: 'purchase',
          entity_id: 100,
          field_name: '__created__',
          changed_by_name: 'Игорь Цыганов',
          changed_at: '2026-10-20T10:00:00Z',
          source: 'import',
          origin_label: 'Загружено из файла «ФЭО_2026.xlsx» (строка 14)',
        },
      ])

      // Test component recreating CellHistoryPopover props contract and rendering
      const PopoverTestComponent = defineComponent({
        name: 'CellHistoryPopoverTest',
        props: {
          modelValue: { type: [Boolean, Object] as any, default: null },
          options: { type: Object as any, default: undefined },
          position: { type: Object as any, default: undefined },
        },
        setup(props) {
          const effectiveVisible = computed(() =>
            props.modelValue !== null && props.modelValue !== undefined ? props.modelValue : isHistoryOpen.value
          )
          const events = ref<CellHistoryEvent[]>([])
          const currentEvent = computed(() => events.value[0] || null)

          watch(
            () => effectiveVisible.value,
            async (vis) => {
              if (vis && historyCellOptions.value) {
                events.value = await fetchCellHistory(historyCellOptions.value as any)
              } else {
                events.value = []
              }
            },
            { immediate: true }
          )

          return { effectiveVisible, events, currentEvent }
        },
        template: `
          <div v-if="effectiveVisible" class="gala-history-popover-backdrop">
            <div class="gala-history-popover">
              <div v-if="currentEvent" class="gala-history-content">
                <div v-if="currentEvent.originLabel" class="origin-label">
                  {{ currentEvent.originLabel }}
                </div>
                <div v-if="events.length === 1 && !currentEvent.isCalculatedOrEmpty" class="gala-history-single-notice">
                  Изменений после внесения не было
                </div>
              </div>
            </div>
          </div>
        `,
      })

      const container = document.createElement('div')
      document.body.appendChild(container)

      // Mount WITHOUT passing modelValue, matching <cell-history-popover /> in App.vue!
      const app = createApp(PopoverTestComponent)
      app.mount(container)

      // Initially closed
      expect(container.querySelector('.gala-history-popover')).toBeNull()

      openCellHistory({
        entityType: 'purchase',
        entityId: 100,
        fieldName: 'subject',
        fieldLabel: 'Предмет закупки',
        cellValue: '90 585,00 ₽',
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 50))
      await nextTick()

      const popover = container.querySelector('.gala-history-popover')
      expect(popover).not.toBeNull()
      expect(container.textContent).toContain('Загружено из файла «ФЭО_2026.xlsx» (строка 14)')
      expect(container.textContent).toContain('Изменений после внесения не было')

      closeCellHistory()
      await nextTick()
      app.unmount()
      document.body.removeChild(container)
    })
  })
})
