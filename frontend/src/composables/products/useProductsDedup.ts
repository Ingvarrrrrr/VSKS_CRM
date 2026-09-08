// useProductsDedup.ts — поиск и удаление дубликатов товаров (dry-run превью +
// подтверждение). Дословный перенос из ProductsView.vue.
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { DupGroup } from './productsTypes'

export function useProductsDedup(options: {
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { load, showSnack } = options

  const deduplicating = ref(false)
  const dupDialog = reactive({
    show: false,
    groups: [] as DupGroup[],
    skipIds: new Set<number>(),
  })

  async function deduplicateProducts() {
    deduplicating.value = true
    try {
      const result = await apiFetch<{ groups: DupGroup[]; total_groups: number; total_to_delete: number }>(
        '/products/deduplicate?dry_run=true', { method: 'POST' },
      )
      if (!result.total_groups) {
        showSnack('Дубликатов не найдено')
        return
      }
      dupDialog.groups = result.groups
      dupDialog.skipIds = new Set()
      for (const g of result.groups) for (const d of g.duplicates) if (d.match === 'fuzzy') dupDialog.skipIds.add(d.id)
      dupDialog.show = true
    } catch (e: any) {
      showSnack(e.message || 'Ошибка поиска дубликатов', 'error')
    } finally {
      deduplicating.value = false
    }
  }

  const totalDupsToDelete = computed(() =>
    dupDialog.groups.reduce(
      (sum, g) => sum + g.duplicates.filter(d => !dupDialog.skipIds.has(d.id)).length,
      0,
    ),
  )

  async function confirmDeduplicate() {
    deduplicating.value = true
    try {
      const skipCsv = Array.from(dupDialog.skipIds).join(',')
      const url = `/products/deduplicate${skipCsv ? `?skip_ids=${skipCsv}` : ''}`
      const result = await apiFetch<{ deleted: number; kept: number }>(url, { method: 'POST' })
      showSnack(`Удалено дублей: ${result.deleted}, оставлено: ${result.kept}`)
      dupDialog.show = false
      if (result.deleted > 0) await load()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка дедупликации', 'error')
    } finally {
      deduplicating.value = false
    }
  }

  function toggleSkip(id: number) {
    if (dupDialog.skipIds.has(id)) dupDialog.skipIds.delete(id)
    else dupDialog.skipIds.add(id)
  }

  return { deduplicating, dupDialog, deduplicateProducts, totalDupsToDelete, confirmDeduplicate, toggleSkip }
}
