import { computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useCellMarks, type CellTarget } from '@/composables/useCellMarks'
import { useGalaContextMenu } from '@/composables/useGalaContextMenu'
import type { Purchase } from '@/composables/orders/ordersTypes'

export function useOrdersTableMarks(
  props: {
    items: any[]
    selectedOrders: Purchase[]
    setFilter?: (k: string, v: any) => void
  }
) {
  const router = useRouter()
  const cellMarks = useCellMarks()
  const { openCellContextMenu } = useGalaContextMenu()

  // Load marks on items change
  watch(
    () => props.items,
    (items) => {
      if (items && items.length > 0) {
        const ids = items.map((i: any) => i.id).filter(Boolean)
        if (ids.length > 0) {
          void cellMarks.loadMarks('purchase', ids)
        }
      }
    },
    { immediate: true }
  )

  // Filter items by active color filter
  const displayItems = computed(() => {
    const filterColor = cellMarks.activeColorFilter.value?.purchase
    if (filterColor) {
      return props.items.filter((item: any) => cellMarks.matchesColorFilter('purchase', item.id))
    }
    return props.items
  })

  function getRowProps({ item }: { item: any }) {
    const markClasses = cellMarks.getRowMarkClasses('purchase', item.id)
    const markStyle = cellMarks.getRowMarkStyle('purchase', item.id)
    return {
      class: markClasses,
      style: markStyle,
      'data-gala-focus': `purchase:${item.id}`,
    }
  }

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

  function openOrderCellMenu(
    event: MouseEvent,
    item: Purchase,
    fieldName: string,
    fieldLabel: string,
    cellValue: any,
    rawNumber?: number | string | null
  ) {
    const isSelected = props.selectedOrders?.some((o) => o.id === item.id)
    const bulkTargets =
      isSelected && props.selectedOrders.length > 1
        ? props.selectedOrders.map((o) => ({
            entityType: 'purchase',
            entityId: o.id,
            fieldName: '*',
          }))
        : undefined

    openCellContextMenu(event, {
      entityType: 'purchase',
      entityId: item.id,
      fieldName,
      fieldLabel,
      cellValue,
      rawNumber:
        rawNumber !== undefined ? rawNumber : typeof cellValue === 'number' ? cellValue : undefined,
      openUrl: `/orders/${item.id}/edit`,
      subsidyId: item.subsidy_id ?? null,
      bulkTargets,
      onFilterValue: (val: any) => {
        if (props.setFilter && fieldName) {
          props.setFilter(fieldName, val)
        }
      },
      extraItems: [
        {
          key: 'open_order_card',
          label: 'Перейти к карточке закупки',
          icon: 'mdi-open-in-new',
          onClick: () => {
            router.push(`/orders/${item.id}/edit`)
          },
        },
      ],
    } as any)
  }

  function onEntityRestored(e: Event) {
    const customEv = e as CustomEvent<{ entityType: string; entityId: number | string }>
    if (customEv.detail?.entityType === 'purchase') {
      if (props.items && props.items.length > 0) {
        const ids = props.items.map((i: any) => i.id).filter(Boolean)
        if (ids.length > 0) {
          void cellMarks.loadMarks('purchase', ids)
        }
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
    getRowProps,
    onCellClick,
    openOrderCellMenu,
  }
}
