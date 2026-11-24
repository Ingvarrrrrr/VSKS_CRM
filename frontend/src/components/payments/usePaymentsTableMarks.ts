import { computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCellMarks, type CellTarget } from '@/composables/useCellMarks'
import { useGalaContextMenu } from '@/composables/useGalaContextMenu'

export const headerMenuColumns = [
  { key: 'payment_number', type: 'enum' },
  { key: 'payer_name', type: 'enum' },
  { key: 'payee_name', type: 'enum' },
  { key: 'payer_inn', type: 'enum' },
  { key: 'payee_inn', type: 'enum' },
  { key: 'purpose_text', type: 'enum' },
  { key: 'basis_doc_text', type: 'enum' },
  { key: 'basis_doc_number', type: 'enum' },
  { key: 'basis_doc_date', type: 'date' },
  { key: 'parsed_contract_number', type: 'enum' },
  { key: 'parsed_kbk', type: 'enum' },
  { key: 'expense_code_short', type: 'enum' },
  { key: 'expense_code', type: 'enum' },
  { key: 'status', type: 'enum' },
  { key: 'matched', type: 'boolean' },
  { key: 'matched_confirmed', type: 'boolean' },
  { key: 'amount', type: 'number', align: 'end' as const },
  { key: 'payment_date', type: 'date' },
  { key: 'parsed_contract_date', type: 'date' },
]

export function resolveItemMatchedKind(item: any): 'goods' | 'services' | null {
  const isMatched = Boolean(
    item?.matched_contract_id ||
      item?.matched_purchase_id ||
      (item?.attached_purchases && item.attached_purchases.length > 0)
  )
  if (!isMatched) return null
  if (item.matched_kind === 'goods' || item.matched_kind === 'services') {
    return item.matched_kind
  }
  const ec = String(item.expense_code || item.expense_code_short || '').trim()
  if (ec.startsWith('03') || ec.startsWith('300')) return 'goods'
  return 'services'
}

export function usePaymentsTableMarks(
  props: {
    items: any[]
    setFilter?: (k: string, v: any) => void
  }
) {
  const cellMarks = useCellMarks()
  const { openCellContextMenu } = useGalaContextMenu()

  watch(
    () => props.items,
    (items) => {
      if (items && items.length > 0) {
        const ids = items.map((p: any) => p.id).filter(Boolean)
        if (ids.length > 0) {
          void cellMarks.loadMarks('payment', ids)
        }
      }
    },
    { immediate: true }
  )

  const displayItems = computed(() => {
    const filterColor = cellMarks.activeColorFilter.value?.payment
    if (filterColor) {
      return props.items.filter((p: any) => cellMarks.matchesColorFilter('payment', p.id))
    }
    return props.items
  })

  function onCellClick(event: MouseEvent, target: CellTarget) {
    if (cellMarks.handleCellSelectClick(event, target)) {
      event.stopPropagation()
      return
    }
    const el = event.currentTarget as HTMLElement | null
    if (el) {
      const rect = el.getBoundingClientRect()
      const isTopRight = event.clientX >= rect.right - 18 && event.clientY <= rect.top + 18
      const mark = cellMarks.getMark(target.entityType, Number(target.entityId), target.fieldName)
      if (isTopRight && mark?.comment) {
        event.stopPropagation()
        cellMarks.openCommentAt(event, target)
      }
    }
  }

  function openPaymentCellMenu(
    event: MouseEvent,
    item: any,
    fieldName: string,
    fieldLabel: string,
    cellValue: any,
    rawNumber?: number | string | null
  ) {
    const purchaseId = item.matched_purchase_id || item.matched_contract_id
    openCellContextMenu(event, {
      entityType: 'payment',
      entityId: item.id,
      fieldName,
      fieldLabel,
      cellValue,
      rawNumber:
        rawNumber !== undefined ? rawNumber : typeof cellValue === 'number' ? cellValue : undefined,
      openUrl: purchaseId ? `/orders/${purchaseId}/edit` : undefined,
      onFilterValue: (val: any) => {
        if (props.setFilter && fieldName) {
          props.setFilter(fieldName, val)
        }
      },
      extraItems: purchaseId
        ? [
            {
              key: 'open_purchase',
              label: 'Перейти к закупке',
              icon: 'mdi-open-in-new',
              onClick: () => {
                window.open(`/orders/${purchaseId}/edit`, '_blank')
              },
            },
          ]
        : undefined,
    } as any)
  }

  function onEntityRestored(e: Event) {
    const customEv = e as CustomEvent<{ entityType: string; entityId: number | string }>
    if (customEv.detail?.entityType === 'payment') {
      if (props.items && props.items.length > 0) {
        void cellMarks.loadMarks('payment', props.items.map((p: any) => p.id).filter(Boolean))
      }
    }
  }

  onMounted(() => {
    window.addEventListener('gala:entity-restored', onEntityRestored)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('gala:entity-restored', onEntityRestored)
  })

  return {
    cellMarks,
    displayItems,
    onCellClick,
    openPaymentCellMenu,
  }
}
