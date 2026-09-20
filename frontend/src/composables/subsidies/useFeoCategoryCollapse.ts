// «Свернуть категорию-дубль в плановую позицию» (владелец, задача 3) —
// категория без подкатегорий и ровно с одной плановой позицией часто дублирует
// её же имя ("Great Wall POER" как категория И как единственная позиция внутри)
// — лишний уровень вложенности, который путает дерево. Backend-контракт
// (параллельный исполнитель, тот же коммит-план): GET
// /feo-categories/collapse-candidates?subsidy_id=, POST
// /feo-categories/{id}/collapse-to-item, POST /feo-categories/collapse-bulk.
//
// Module-level singleton (тот же приём, что и useFeoLevel5Api/usePlanToRequest,
// Правило №6) — один список кандидатов на всю субсидию: FeoTreeToolbar.vue
// (счётчик кнопки + диалог предпросмотра FeoCollapseCandidatesDialog.vue) и
// FeoTreeRow.vue (кнопка у отдельной категории) читают ОДИН и тот же список,
// второй запрос/копию не заводят.
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface FeoCollapseCandidate {
  category_id: number
  name: string
  parent_id: number | null
  parent_name: string | null
  planned_item_id: number
  planned_item_name: string
  is_name_duplicate: boolean
  category_feo_amount: number | null
  item_amount: number | null
  blocked_reason: string | null
}

export interface FeoCollapseMovedRefs {
  purchases: number
  purchase_items: number
  products: number
  wishes: number
  wish_items: number
}

export interface FeoCollapseBulkResult {
  category_id: number
  ok: boolean
  error: string | null
  planned_item_id: number | null
}

const candidates = ref<FeoCollapseCandidate[]>([])
const candidatesLoadedForSubsidyId = ref<number | null>(null)
const candidatesLoading = ref(false)
const singleCollapsing = ref<number | null>(null)

// Диалог подтверждения одиночного сворачивания (FeoCollapseConfirmDialog.vue) —
// координатор (приёмка в браузере, 2026-09-20): window.confirm() заменён на
// v-dialog в стиле проекта, тот же паттерн, что и FeoCategoryDeleteDialog.vue
// (v-model + defineExpose не нужен — состояние здесь, в module-level singleton,
// как и остальное в этом файле, второй канал не заводим).
export interface FeoCollapseSingleTarget { categoryId: number; categoryName: string; plannedItemName: string }
const singleDialogOpen = ref(false)
const singleDialogTarget = ref<FeoCollapseSingleTarget | null>(null)

const bulkDialogOpen = ref(false)
const bulkSelectedIds = ref<Set<number>>(new Set())
const bulkSubmitting = ref(false)
const bulkResults = ref<FeoCollapseBulkResult[]>([])
// Прогресс пачечной отправки (QA-замечание, задача 3, 2026-09-20): у субсидии
// ЛНР 186 кандидатов — один запрос всеми id рискует таймаутом apiFetch (60с,
// api.ts) при последовательном пересчёте версии плана на бэке. Шлём пачками,
// прогресс — для v-progress-linear в FeoCollapseCandidatesDialog.vue.
const BULK_CHUNK_SIZE = 15
const bulkProgressDone = ref(0)
const bulkProgressTotal = ref(0)

export function useFeoCategoryCollapse() {
  const toast = useToast()
  function showSnack(text: string, color: 'success' | 'error' | 'info' | 'warning' = 'success') {
    toast.addToast(text, color)
  }

  // Считается лениво — при открытии субсидии (FeoTreeToolbar.vue вызывает при
  // монтировании/смене ctx.selectedId), не на каждый рендер строки дерева.
  async function ensureCandidates(subsidyId: number, force = false) {
    if (!force && candidatesLoadedForSubsidyId.value === subsidyId) return
    candidatesLoading.value = true
    try {
      const resp = await apiFetch<{ items: FeoCollapseCandidate[] }>(`/feo-categories/collapse-candidates?subsidy_id=${subsidyId}`)
      candidates.value = resp.items || []
      candidatesLoadedForSubsidyId.value = subsidyId
    } catch {
      // Тихий фолбэк: кнопка/счётчик просто не появляются (0 кандидатов) —
      // фича ожидает параллельно разрабатываемый бэкенд-эндпоинт, дерево ФЭО
      // не должно падать снэкбаром об ошибке из-за неё.
      candidates.value = []
      candidatesLoadedForSubsidyId.value = subsidyId
    } finally {
      candidatesLoading.value = false
    }
  }

  const candidatesCount = computed(() => candidates.value.length)
  function candidateFor(categoryId: number): FeoCollapseCandidate | undefined {
    return candidates.value.find(c => c.category_id === categoryId)
  }

  function movedRefsSummary(m: FeoCollapseMovedRefs | null | undefined): string {
    if (!m) return 'Категория свёрнута в плановую позицию'
    const parts: string[] = []
    if (m.purchases) parts.push(`закупок: ${m.purchases}`)
    if (m.purchase_items) parts.push(`позиций закупок: ${m.purchase_items}`)
    if (m.products) parts.push(`товаров: ${m.products}`)
    if (m.wishes) parts.push(`заявок: ${m.wishes}`)
    if (m.wish_items) parts.push(`позиций заявок: ${m.wish_items}`)
    return parts.length ? `Категория свёрнута в плановую позицию. Перенесено — ${parts.join(', ')}` : 'Категория свёрнута в плановую позицию'
  }

  // Открыть/закрыть диалог подтверждения (FeoTreeRow.vue::onCollapseToItem вызывает
  // openSingleCollapseDialog вместо прямого collapseCategoryToItem).
  function openSingleCollapseDialog(categoryId: number, categoryName: string, plannedItemName: string) {
    singleDialogTarget.value = { categoryId, categoryName, plannedItemName }
    singleDialogOpen.value = true
  }
  function closeSingleCollapseDialog() {
    singleDialogOpen.value = false
  }

  // Одиночное сворачивание — вызывается ТОЛЬКО кнопкой «Свернуть» в
  // FeoCollapseConfirmDialog.vue (подтверждение уже получено диалогом, второй
  // confirm() здесь не нужен — координатор заменил window.confirm на v-dialog).
  async function collapseCategoryToItem(categoryId: number, categoryName: string, plannedItemName: string): Promise<boolean> {
    singleCollapsing.value = categoryId
    try {
      const resp = await apiFetch<{ category_id: number; planned_item_id: number; parent_id: number | null; moved_refs: FeoCollapseMovedRefs }>(
        `/feo-categories/${categoryId}/collapse-to-item`, { method: 'POST' },
      )
      showSnack(movedRefsSummary(resp.moved_refs))
      candidates.value = candidates.value.filter(c => c.category_id !== categoryId)
      singleDialogOpen.value = false
      singleDialogTarget.value = null
      return true
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось свернуть категорию в плановую позицию', prefix: 'Ошибка' }), 'error')
      return false
    } finally {
      singleCollapsing.value = null
    }
  }

  // ── Диалог предпросмотра массового сворачивания (FeoCollapseCandidatesDialog.vue) ──
  function openBulkDialog(subsidyId: number) {
    bulkResults.value = []
    // По умолчанию отмечены is_name_duplicate без blocked_reason (задание).
    bulkSelectedIds.value = new Set(
      candidates.value.filter(c => c.is_name_duplicate && !c.blocked_reason).map(c => c.category_id),
    )
    bulkDialogOpen.value = true
    void ensureCandidates(subsidyId, true)
  }
  function closeBulkDialog() {
    bulkDialogOpen.value = false
  }
  function toggleBulkSelected(categoryId: number) {
    const s = new Set(bulkSelectedIds.value)
    if (s.has(categoryId)) s.delete(categoryId); else s.add(categoryId)
    bulkSelectedIds.value = s
  }

  // Пачками по BULK_CHUNK_SIZE, последовательно — каждая пачка коммитится на
  // бэке независимо, поэтому ошибка/таймаут одной пачки не теряет результат
  // уже свёрнутых категорий из предыдущих. bulkResults копится по ходу —
  // FeoCollapseCandidatesDialog.vue видит нарастающий список ошибок сразу.
  async function submitBulkCollapse(): Promise<boolean> {
    const ids = [...bulkSelectedIds.value]
    if (!ids.length) return false
    bulkSubmitting.value = true
    bulkResults.value = []
    bulkProgressDone.value = 0
    bulkProgressTotal.value = ids.length
    try {
      for (let i = 0; i < ids.length; i += BULK_CHUNK_SIZE) {
        const chunk = ids.slice(i, i + BULK_CHUNK_SIZE)
        try {
          const resp = await apiFetch<{ results: FeoCollapseBulkResult[] }>('/feo-categories/collapse-bulk', {
            method: 'POST',
            body: JSON.stringify({ category_ids: chunk }),
          })
          bulkResults.value = [...bulkResults.value, ...(resp.results || [])]
        } catch (e: any) {
          // Пачка целиком не доехала (таймаут/сеть) — бэк мог часть уже
          // закоммитить, но ответа мы не увидим; помечаем всю пачку ошибкой с
          // причиной, дерево ниже перезагрузится и покажет фактическое
          // состояние. Остальные пачки всё равно отправляем.
          const reason = describeApiError(e, { fallback: 'Не удалось выполнить массовое сворачивание категорий', prefix: 'Ошибка' })
          bulkResults.value = [
            ...bulkResults.value,
            ...chunk.map(category_id => ({ category_id, ok: false, error: reason, planned_item_id: null })),
          ]
        } finally {
          bulkProgressDone.value += chunk.length
        }
      }
      const okIds = new Set(bulkResults.value.filter(r => r.ok).map(r => r.category_id))
      candidates.value = candidates.value.filter(c => !okIds.has(c.category_id))
      bulkSelectedIds.value = new Set([...bulkSelectedIds.value].filter(id => !okIds.has(id)))
      const okCount = okIds.size
      const failCount = bulkResults.value.length - okCount
      if (failCount === 0) {
        showSnack(`Свёрнуто ${okCount} из ${ids.length}`)
        bulkDialogOpen.value = false
      } else {
        showSnack(`Свёрнуто ${okCount} из ${ids.length}. Не удалось: ${failCount} — см. список ошибок`, 'error')
      }
      return okCount > 0
    } finally {
      bulkSubmitting.value = false
    }
  }

  return {
    candidates, candidatesLoading, candidatesCount, candidateFor, ensureCandidates,
    singleCollapsing, collapseCategoryToItem,
    singleDialogOpen, singleDialogTarget, openSingleCollapseDialog, closeSingleCollapseDialog,
    bulkDialogOpen, bulkSelectedIds, bulkSubmitting, bulkResults,
    bulkProgressDone, bulkProgressTotal,
    openBulkDialog, closeBulkDialog, toggleBulkSelected, submitBulkCollapse,
  }
}
