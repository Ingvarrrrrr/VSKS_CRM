// useWishItemsFeoAutosave.ts — ДЕФЕКТ 1 (владелец, 2026-08-20): автосохранение
// построчных ФЭО-правок (категория/плановая позиция), которые дочерние компоненты
// (FeoTreeSelect/FeoPlannedItemsSelect) пишут напрямую в wishForm.value.items,
// НЕЗАВИСИМО от readonly формы. Debounce 700мс → тихий PATCH /wishes/{id}/execution.
// Дословный перенос из WishesView.vue при разбиении файла — см. подробные
// комментарии по каждому решению в оригинале (git-история WishesView.vue).
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { WishesContext } from './useWishesContext'
import type { UseWishFormReturn } from './useWishForm'

export function useWishItemsFeoAutosave(deps: {
  ctx: WishesContext
  apiFetch: typeof import('@/api').apiFetch
  form: UseWishFormReturn
  reloadActiveTab: () => Promise<void>
}) {
  const { ctx, apiFetch, form, reloadActiveTab } = deps
  const { showSnack } = ctx
  const { wishForm, editingWishId, editingWish, wishFeoSelected, wishFormSavedSnapshot, wishPayloadSnapshotJson } = form

  const wishItemsFeoSnapshot = ref<Map<number, { feo_category_id: number | null; feo_planned_item_id: number | null }>>(new Map())

  function snapshotWishItemsFeo() {
    const m = new Map<number, { feo_category_id: number | null; feo_planned_item_id: number | null }>()
    for (const it of wishForm.value.items as any[]) {
      if (it.id != null) {
        m.set(it.id, {
          feo_category_id: it.feo_category_id ?? null,
          feo_planned_item_id: it.feo_planned_item_id ?? null,
        })
      }
    }
    wishItemsFeoSnapshot.value = m
  }

  const wishItemsFeoDirtyList = computed(() => {
    const out: { id: number; feo_category_id: number | null; feo_planned_item_id: number | null }[] = []
    for (const it of wishForm.value.items as any[]) {
      if (it.id == null) continue
      const before = wishItemsFeoSnapshot.value.get(it.id)
      if (!before) continue
      const catId = it.feo_category_id ?? null
      const planId = it.feo_planned_item_id ?? null
      if (before.feo_category_id !== catId || before.feo_planned_item_id !== planId) {
        out.push({ id: it.id, feo_category_id: catId, feo_planned_item_id: planId })
      }
    }
    return out
  })
  const wishItemsFeoDirty = computed(() => wishItemsFeoDirtyList.value.length > 0)

  let feoAutosaveTimer: ReturnType<typeof setTimeout> | null = null
  const feoAutosavePending = ref(false)
  const feoAutosaveSaving = ref(false)
  let feoAutosaveInFlight: Promise<boolean> | null = null

  const feoAutosaveApplicable = computed(() =>
    !!editingWishId.value && ['submitted', 'approved'].includes((wishForm.value as any).status)
  )

  const wishFeoHeaderDirty = computed(() =>
    !!editingWishId.value &&
    !wishForm.value.feo_per_item &&
    (wishFeoSelected.value ?? null) !== (wishForm.value.feo_category_id ?? null)
  )

  function feoExecutionItemsPayload(): { id: number; feo_category_id: number | null; feo_planned_item_id: number | null }[] {
    return wishItemsFeoDirtyList.value.map(it => ({
      id: it.id,
      feo_category_id: wishForm.value.feo_per_item ? it.feo_category_id : (wishFeoSelected.value ?? null),
      feo_planned_item_id: it.feo_planned_item_id,
    }))
  }

  function applyFeoExecutionSuccess(sentFeoCategoryId: number | null | undefined) {
    if (sentFeoCategoryId != null) wishForm.value.feo_category_id = sentFeoCategoryId
    snapshotWishItemsFeo()
    wishFormSavedSnapshot.value = wishPayloadSnapshotJson()
  }

  function describeFeoExecutionError(e: any, headerWasDirty: boolean): string {
    const msg = e?.payload?.message ?? e?.detail ?? e?.message ?? 'не удалось сохранить'
    const status = e?.status != null ? ` (HTTP ${e.status})` : ''
    const hint = headerWasDirty
      ? ' Смена категории ФЭО заявки НЕ сохранена — категория позиции и выбранная категория заявки разошлись. Проверьте категорию/плановую позицию у товара и нажмите «Сохранить ФЭО» ещё раз.'
      : ''
    return `${msg}${status}.${hint}`
  }

  function scheduleFeoAutosave() {
    feoAutosavePending.value = true
    if (feoAutosaveTimer) clearTimeout(feoAutosaveTimer)
    feoAutosaveTimer = setTimeout(() => {
      feoAutosaveTimer = null
      void runFeoAutosave()
    }, 700)
  }

  // Правки построчного ФЭО пишутся напрямую в объекты wishForm.value.items дочерними
  // компонентами — wishItemsFeoDirtyList уже computed поверх этого, пересчитывается на
  // каждое изменение. Не планируем автосейв вовсе, если статус не submitted/approved.
  watch(() => wishItemsFeoDirtyList.value, (list) => {
    if (list.length > 0 && feoAutosaveApplicable.value) scheduleFeoAutosave()
  })
  // Если пока тикал debounce статус заявки перестал быть submitted/approved — гасим
  // таймер без отправки: сработавший PATCH всё равно был бы отклонён backend'ом 400-й.
  watch(feoAutosaveApplicable, (applicable) => {
    if (!applicable && feoAutosaveTimer) {
      clearTimeout(feoAutosaveTimer)
      feoAutosaveTimer = null
      feoAutosavePending.value = false
    }
  })

  async function runFeoAutosave(): Promise<boolean> {
    feoAutosavePending.value = false
    if (feoAutosaveInFlight) {
      const prevOk = await feoAutosaveInFlight
      if (!prevOk) return false
    }
    if (!feoAutosaveApplicable.value) return true
    if (!editingWishId.value) return true
    const headerDirty = wishFeoHeaderDirty.value
    if (wishItemsFeoDirtyList.value.length === 0 && !headerDirty) return true
    const items = feoExecutionItemsPayload()
    const body: any = { items }
    if (headerDirty) body.feo_category_id = wishFeoSelected.value
    feoAutosaveSaving.value = true
    const p = (async (): Promise<boolean> => {
      try {
        await apiFetch(`/wishes/${editingWishId.value}/execution`, {
          method: 'PATCH',
          body: JSON.stringify(body),
          suppressErrorDialog: true,
        })
        applyFeoExecutionSuccess(headerDirty ? body.feo_category_id : undefined)
        showSnack(headerDirty ? 'ФЭО заявки и позиций сохранено' : 'ФЭО сохранено', 'success', { duration: 2000 })
        return true
      } catch (e: any) {
        showSnack(`Автосохранение ФЭО не удалось: ${describeFeoExecutionError(e, headerDirty)}`, 'error')
        return false
      } finally {
        feoAutosaveSaving.value = false
        feoAutosaveInFlight = null
      }
    })()
    feoAutosaveInFlight = p
    return p
  }

  async function flushFeoAutosave(): Promise<boolean> {
    if (feoAutosaveTimer) {
      clearTimeout(feoAutosaveTimer)
      feoAutosaveTimer = null
      feoAutosavePending.value = false
    }
    if (feoAutosaveInFlight) {
      const ok = await feoAutosaveInFlight
      if (!ok) return false
    }
    if (wishItemsFeoDirtyList.value.length === 0 && !wishFeoHeaderDirty.value) return true
    return runFeoAutosave()
  }

  onBeforeUnmount(() => {
    if (feoAutosaveTimer) clearTimeout(feoAutosaveTimer)
  })

  const savingExecution = ref(false)
  async function saveExecution() {
    if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'warning'); return }
    if (feoAutosaveTimer) { clearTimeout(feoAutosaveTimer); feoAutosaveTimer = null; feoAutosavePending.value = false }
    if (feoAutosaveInFlight) await feoAutosaveInFlight
    savingExecution.value = true
    try {
      const body: any = {
        executor_id: wishForm.value.executor_id,
        execution_deadline: wishForm.value.execution_deadline || null,
        event_id: wishForm.value.event_id,
        feo_category_id: wishFeoSelected.value || wishForm.value.feo_category_id,
        assigned_to: wishForm.value.assigned_to,
      }
      if (wishItemsFeoDirtyList.value.length > 0) {
        body.items = feoExecutionItemsPayload()
      }
      await apiFetch(`/wishes/${editingWishId.value}/execution`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
      showSnack('Сохранено: исполнитель / срок / мероприятие / ФЭО / получатель')
      applyFeoExecutionSuccess(body.feo_category_id)
      await reloadActiveTab()
    } catch (e: any) {
      showSnack(`Ошибка: ${describeFeoExecutionError(e, wishFeoHeaderDirty.value)}`, 'error')
    } finally {
      savingExecution.value = false
    }
  }

  // Быстрое сохранение поля «На чьё имя будет заявка» без полного saveExecution
  async function saveAssignedTo(val: number | null) {
    if (!editingWishId.value) return
    try {
      await apiFetch(`/wishes/${editingWishId.value}/execution`, {
        method: 'PATCH',
        body: JSON.stringify({ assigned_to: val }),
      })
      if (editingWish.value) editingWish.value.assigned_to = val as number
      showSnack('Исполнитель обновлён')
      await reloadActiveTab()
    } catch (e: any) {
      showSnack(`Ошибка: ${e?.payload?.message || e?.message || 'не удалось сохранить'}`, 'error')
    }
  }

  return {
    wishItemsFeoSnapshot, snapshotWishItemsFeo, wishItemsFeoDirtyList, wishItemsFeoDirty,
    feoAutosavePending, feoAutosaveSaving, feoAutosaveApplicable, wishFeoHeaderDirty,
    scheduleFeoAutosave, runFeoAutosave, flushFeoAutosave,
    savingExecution, saveExecution, saveAssignedTo,
  }
}

export type UseWishItemsFeoAutosaveReturn = ReturnType<typeof useWishItemsFeoAutosave>
