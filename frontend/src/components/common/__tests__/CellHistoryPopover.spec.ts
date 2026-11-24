// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  avatarColor,
  avatarLetter,
  formatRussianDate,
  formatCellValue,
  fetchCellHistory,
} from '@/composables/useCellHistory'
import { useGalaContextMenu, extractNumericValue } from '@/composables/useGalaContextMenu'
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
    it('formats valid date string', () => {
      const res = formatRussianDate('2026-10-23T15:11:00Z')
      expect(res).toBeTruthy()
      expect(res).toContain('11')
    })

    it('handles empty input gracefully', () => {
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

    it('formats FEO money fields into currency format', () => {
      const opts = {
        entityType: 'feo_item',
        entityId: 1,
        fieldName: 'amount',
        fieldLabel: 'Сумма',
      }
      const res = formatCellValue('1500', opts)
      expect(res).toContain('1')
      expect(res).toContain('500')
      expect(res).toContain('₽')
    })

    it('formats FEO quantity fields without trailing zeros', () => {
      const opts = {
        entityType: 'feo_item',
        entityId: 1,
        fieldName: 'quantity',
        fieldLabel: 'Количество',
      }
      expect(formatCellValue('2.000', opts)).toBe('2')
      expect(formatCellValue('0.500', opts)).toBe('0.5')
    })

    it('formats standard numbers with locale formatting', () => {
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

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining('/vehicles/1/field-history?field_key=mileage')
      )
      expect(events).toHaveLength(1)
      expect(events[0].changedByName).toBe('Игорь Цыганов')
      expect(events[0].oldValue).toBe('1000')
      expect(events[0].newValue).toBe('2000')
      expect(events[0].comment).toBe('ТО-1')
    })

    it('fetches entity changes and filters by field_name', async () => {
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
          id: 11,
          entity_type: 'purchase',
          entity_id: 100,
          field_name: 'other_field',
          old_value: '1',
          new_value: '2',
        },
      ])

      const events = await fetchCellHistory({
        entityType: 'purchase',
        entityId: 100,
        fieldName: 'subject',
        fieldLabel: 'Предмет',
      })

      expect(mockApiFetch).toHaveBeenCalledWith('/entity-changes/purchase/100')
      expect(events).toHaveLength(1)
      expect(events[0].oldValue).toBe('Старый договор')
      expect(events[0].newValue).toBe('Новый договор')
    })

    it('synthesizes created event when no direct field changes exist but __created__ exists', async () => {
      const mockApiFetch = vi.mocked(apiFetch)
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 1,
          entity_type: 'feo_item',
          entity_id: 5,
          field_name: '__created__',
          changed_by_name: 'Игорь Цыганов',
          changed_at: '2026-10-20T10:00:00Z',
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
      expect(events[0].isCreated).toBe(true)
      expect(events[0].newValue).toBe('Молоток слесарный')
      expect(events[0].changedByName).toBe('Игорь Цыганов')
    })
  })

  describe('useGalaContextMenu', () => {
    it('manages context menu and history popover open/close state', () => {
      const {
        isMenuOpen,
        menuPosition,
        activeCellOptions,
        openCellContextMenu,
        closeContextMenu,
        isHistoryOpen,
        openCellHistory,
        closeCellHistory,
      } = useGalaContextMenu()

      const fakeEvent = {
        clientX: 150,
        clientY: 250,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      } as unknown as MouseEvent

      const options = {
        entityType: 'task',
        entityId: 77,
        fieldName: 'title',
        fieldLabel: 'Название',
        cellValue: 'Подготовить отчёт',
      }

      openCellContextMenu(fakeEvent, options)
      expect(isMenuOpen.value).toBe(true)
      expect(menuPosition.value).toEqual({ x: 150, y: 250 })
      expect(activeCellOptions.value?.entityId).toBe(77)

      // Open history from context menu
      openCellHistory()
      expect(isMenuOpen.value).toBe(false)
      expect(isHistoryOpen.value).toBe(true)

      closeCellHistory()
      expect(isHistoryOpen.value).toBe(false)
    })
  })

  describe('useCellMarks', () => {
    it('exports 6 palette colors', () => {
      expect(MARK_COLOR_PALETTE).toHaveLength(6)
      const keys = MARK_COLOR_PALETTE.map(p => p.key)
      expect(keys).toEqual(['yellow', 'red', 'green', 'blue', 'purple', 'orange'])
    })

    it('handles selection and keyboard navigation', () => {
      const marks = useCellMarks()
      marks.clearSelection()

      const target: CellTarget = {
        entityType: 'order',
        entityId: 10,
        fieldName: 'amount',
      }

      const fakeEventNoModifier = {
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      } as unknown as MouseEvent

      expect(marks.handleCellSelectClick(fakeEventNoModifier, target)).toBe(false)
      expect(marks.isCellSelected('order', 10, 'amount')).toBe(false)

      const fakeEventWithCtrl = {
        ctrlKey: true,
        metaKey: false,
        shiftKey: false,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      } as unknown as MouseEvent

      expect(marks.handleCellSelectClick(fakeEventWithCtrl, target)).toBe(true)
      expect(marks.isCellSelected('order', 10, 'amount')).toBe(true)

      // Toggle off
      expect(marks.handleCellSelectClick(fakeEventWithCtrl, target)).toBe(true)
      expect(marks.isCellSelected('order', 10, 'amount')).toBe(false)

      marks.setBatchSelection([target])
      expect(marks.selectedTargets.value).toHaveLength(1)
      marks.clearSelection()
      expect(marks.selectedTargets.value).toHaveLength(0)
    })

    it('loads marks, provides classes, styles, and color filters', async () => {
      const marks = useCellMarks()
      const mockApiFetch = vi.mocked(apiFetch)

      const mockData: CellMarkRecord[] = [
        {
          id: 1,
          group_id: 'grp_1',
          entity_type: 'order',
          entity_id: 99,
          field_name: 'price',
          color: 'red',
          comment: 'Проверить цену',
          visibility: 'shared',
          is_resolved: false,
          created_at: '2026-10-23T10:00:00Z',
        },
        {
          id: 2,
          group_id: 'grp_2',
          entity_type: 'order',
          entity_id: 99,
          field_name: '*',
          color: 'yellow',
          comment: null,
          visibility: 'shared',
          is_resolved: false,
          created_at: '2026-10-23T10:00:00Z',
        },
      ]

      mockApiFetch.mockResolvedValueOnce(mockData)

      await marks.loadMarks('order', [99])

      expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining('/cell-marks?entity_type=order&entity_ids=99'))

      const exact = marks.getExactMark('order', 99, 'price')
      expect(exact?.color).toBe('red')
      expect(exact?.comment).toBe('Проверить цену')

      const rowMark = marks.getRowMark('order', 99)
      expect(rowMark?.color).toBe('yellow')

      const classes = marks.getCellMarkClasses('order', 99, 'price')
      expect(classes['gala-cell-marked']).toBe(true)
      expect(classes['gala-cell-has-comment']).toBe(true)

      const styles = marks.getCellMarkStyle('order', 99, 'price')
      expect(styles['--gala-mark-light']).toBeTruthy()
      expect(styles['--gala-mark-dark']).toBeTruthy()

      // Color filter testing
      expect(marks.matchesColorFilter('order', 99)).toBe(true)
      marks.setColorFilter('order', 'red')
      expect(marks.matchesColorFilter('order', 99)).toBe(true)
      marks.setColorFilter('order', 'purple')
      expect(marks.matchesColorFilter('order', 99)).toBe(false)
      marks.setColorFilter('order', null)
      expect(marks.matchesColorFilter('order', 99)).toBe(true)
    })

    it('applies batch marks, clears color, and resolves groups', async () => {
      const marks = useCellMarks()
      const mockApiFetch = vi.mocked(apiFetch)

      const target: CellTarget = {
        entityType: 'task',
        entityId: 55,
        fieldName: 'status',
      }

      mockApiFetch.mockResolvedValueOnce([])
      await marks.applyMarkBatch({
        targets: [target],
        color: 'green',
        comment: 'Готово',
      })

      expect(mockApiFetch).toHaveBeenCalledWith(
        '/cell-marks/batch',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            targets: [
              expect.objectContaining({
                entity_type: 'task',
                entity_id: 55,
                field_name: 'status',
              }),
            ],
            color: 'green',
            comment: 'Готово',
          }),
        })
      )
      const m = marks.getMark('task', 55, 'status')
      expect(m?.color).toBe('green')
      expect(m?.comment).toBe('Готово')

      // Clear color
      mockApiFetch.mockResolvedValueOnce({})
      await marks.clearMarksColor([target])
      expect(mockApiFetch).toHaveBeenCalledWith('/cell-marks/clear-color', {
        method: 'POST',
        body: {
          targets: [
            {
              entity_type: 'task',
              entity_id: 55,
              field_name: 'status',
            },
          ],
        },
      })
      const cleared = marks.getExactMark('task', 55, 'status')
      expect(cleared?.color).toBeNull()
      expect(cleared?.comment).toBe('Готово')

      // Do not send request when entityId is 0 or negative or entityType is table_row
      mockApiFetch.mockClear()
      await marks.applyMarkBatch({
        targets: [{ entityType: 'table_row', entityId: 0, fieldName: '*' }],
        color: 'red',
      })
      expect(mockApiFetch).not.toHaveBeenCalled()

      await marks.clearMarksColor([{ entityType: 'summary', entityId: 0, fieldName: 'total' }])
      expect(mockApiFetch).not.toHaveBeenCalled()

      // Resolve mark group
      if (cleared?.group_id) {
        mockApiFetch.mockResolvedValueOnce({})
        await marks.resolveMarkGroup(cleared.group_id)
        expect(mockApiFetch).toHaveBeenCalledWith(`/cell-marks/${cleared.group_id}/resolve`, expect.anything())
        expect(marks.getExactMark('task', 55, 'status')).toBeNull()
      }
    })
  })

  describe('useUniversalTableContext', () => {
    it('ignores input, textarea, contenteditable, and popovers', () => {
      const { isInputOrExcluded } = useUniversalTableContext()
      const inp = document.createElement('input')
      const txt = document.createElement('textarea')
      const ed = document.createElement('div')
      ed.setAttribute('contenteditable', 'true')
      const pop = document.createElement('div')
      pop.className = 'gala-context-menu'
      const norm = document.createElement('td')

      expect(isInputOrExcluded(inp)).toBe(true)
      expect(isInputOrExcluded(txt)).toBe(true)
      expect(isInputOrExcluded(ed)).toBe(true)
      expect(isInputOrExcluded(pop)).toBe(true)
      expect(isInputOrExcluded(norm)).toBe(false)
    })

    it('extracts numeric value from currency text formatted like 48 939,62 ₽', () => {
      expect(extractNumericValue('48 939,62 ₽')).toBe('48939.62')
      expect(extractNumericValue('1 250,50')).toBe('1250.5')
      expect(extractNumericValue('без суммы')).toBeNull()
    })

    it('handles contextmenu event on td and opens context menu with entity context', () => {
      const { handleContextMenu } = useUniversalTableContext()
      const menu = useGalaContextMenu()

      const table = document.createElement('table')
      table.innerHTML = `
        <thead><tr><th>Код</th><th>Сумма</th></tr></thead>
        <tbody>
          <tr data-entity-type="contract" data-entity-id="42">
            <td>CTR-01</td>
            <td>48 939,62 ₽</td>
          </tr>
        </tbody>
      `
      document.body.appendChild(table)
      const targetTd = table.querySelectorAll('td')[1]

      const evt = new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        clientX: 100,
        clientY: 200,
      })
      Object.defineProperty(evt, 'target', { value: targetTd })

      handleContextMenu(evt)

      expect(evt.defaultPrevented).toBe(true)
      expect(menu.isMenuOpen.value).toBe(true)
      expect(menu.activeCellOptions.value?.entityType).toBe('contract')
      expect(menu.activeCellOptions.value?.entityId).toBe(42)
      expect(menu.activeCellOptions.value?.fieldLabel).toBe('Сумма')
      expect(menu.activeCellOptions.value?.rawNumber).toBe('48939.62')

      menu.closeContextMenu()
      document.body.removeChild(table)
    })
  })
})
