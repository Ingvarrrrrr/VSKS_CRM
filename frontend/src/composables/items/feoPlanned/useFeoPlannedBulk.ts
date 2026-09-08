// useFeoPlannedBulk — диалог выбора СПОСОБА массового создания плановых позиций
// (владелец, сессия 2026-08-17): по позиции на каждый товар / одна общая / вручную,
// POST /feo-planned-items/bulk одной атомарной транзакцией. Вынесено дословно из
// FeoPlannedItemsSelect.vue (рефакторинг монолита, 2026-09-08).
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import type { ToastType } from '@/composables/useToast'

export interface BulkItem {
  idx: number
  name: string
  quantity: number | null
  unit: string | null
  amount: number | null
  linked: boolean
}

export interface BulkPreviewRow {
  idx: number | null
  name: string
  quantity: number | null
  unit: string | null
  amount: number | null
}

export interface UseFeoPlannedBulkDeps {
  props: {
    categoryId: number | null
    bulkItems?: BulkItem[]
    bulkTitle?: string | null
  }
  emit: {
    (event: 'update:modelValue', val: FeoPlanSelection | null): void
    (event: 'planned-item-created'): void
    (event: 'bulk-items-created', payload: { mode: 'per_item' | 'single' | 'manual'; results: { idx: number | null; id: number }[] }): void
  }
  showSnack: (text: string, color?: ToastType) => void
}

export function useFeoPlannedBulk(deps: UseFeoPlannedBulkDeps) {
  const { props, emit, showSnack } = deps

  const bulkChooserDialog = ref(false)
  const bulkMode = ref<'per_item' | 'single' | 'manual'>('per_item')
  const bulkSingleName = ref('')
  const manualChecked = ref<number[]>([])
  const bulkCreating = ref(false)

  function toggleManualChecked(idx: number, checked: boolean) {
    if (checked) {
      if (!manualChecked.value.includes(idx)) manualChecked.value = [...manualChecked.value, idx]
    } else {
      manualChecked.value = manualChecked.value.filter(i => i !== idx)
    }
  }

  function openBulkChooserDialog() {
    bulkMode.value = 'per_item'
    bulkSingleName.value = props.bulkTitle?.trim() || ''
    // По умолчанию отмечены позиции БЕЗ существующей привязки к плановой позиции —
    // владелец: «уже привязанные по умолчанию не отмечать и пояснить почему».
    manualChecked.value = (props.bulkItems || []).filter(r => !r.linked).map(r => r.idx)
    bulkChooserDialog.value = true
  }

  const bulkTotalAmount = computed((): number =>
    (props.bulkItems || []).reduce((s, r) => s + (Number(r.amount) || 0), 0)
  )

  // Вариант (а) «по позиции на каждый товар» — пропускает уже привязанные к плановой
  // позиции строки (иначе плодили бы вторую плановую позицию поверх уже существующей).
  const bulkPerItemCandidates = computed(() => (props.bulkItems || []).filter(r => !r.linked))
  const bulkSkippedLinkedCount = computed(() => (props.bulkItems || []).filter(r => r.linked).length)

  const bulkPreviewRows = computed((): BulkPreviewRow[] => {
    if (bulkMode.value === 'single') {
      const name = bulkSingleName.value.trim()
      if (!name) return []
      return [{ idx: null, name, quantity: null, unit: null, amount: bulkTotalAmount.value }]
    }
    if (bulkMode.value === 'manual') {
      return (props.bulkItems || [])
        .filter(r => manualChecked.value.includes(r.idx))
        .map(r => ({ idx: r.idx, name: r.name, quantity: r.quantity, unit: r.unit, amount: r.amount }))
    }
    // per_item
    return bulkPerItemCandidates.value.map(r => ({ idx: r.idx, name: r.name, quantity: r.quantity, unit: r.unit, amount: r.amount }))
  })

  const bulkPreviewTotal = computed((): number =>
    bulkPreviewRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0)
  )

  async function runBulkCreate() {
    if (props.categoryId == null) return
    const rows = bulkPreviewRows.value
    if (!rows.length) return
    bulkCreating.value = true
    try {
      const resp = await apiFetch<{ items: { id: number }[] }>('/feo-planned-items/bulk', {
        method: 'POST',
        body: JSON.stringify({
          items: rows.map(r => ({
            feo_category_id: props.categoryId,
            name: r.name,
            quantity: r.quantity,
            unit: r.unit || null,
            amount: r.amount,
          })),
        }),
      })
      const results = resp.items.map((it, i) => ({ idx: rows[i]?.idx ?? null, id: it.id }))
      bulkChooserDialog.value = false
      emit('planned-item-created')
      emit('bulk-items-created', { mode: bulkMode.value, results })
      if (bulkMode.value === 'single' && results[0]) {
        emit('update:modelValue', { kind: 'planned_item', id: results[0].id })
      }
      showSnack(`Плановых позиций создано/привязано: ${results.length}`)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось создать плановые позиции', 'error')
    } finally {
      bulkCreating.value = false
    }
  }

  return {
    bulkChooserDialog, bulkMode, bulkSingleName, manualChecked, bulkCreating,
    toggleManualChecked, openBulkChooserDialog, bulkTotalAmount, bulkPerItemCandidates,
    bulkSkippedLinkedCount, bulkPreviewRows, bulkPreviewTotal, runBulkCreate,
  }
}
