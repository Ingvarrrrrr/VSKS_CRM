// useWishForm.ts — состояние и сохранение карточки заявки (create/edit), вынесено
// из WishesView.vue при разбиении на WishFormDialog.vue. Дословный перенос логики:
// wishForm, FEO-каскад заголовка, гейты редактируемости, buildWishPayload/saveWish,
// открытие create/edit диалога, T3-подсказки недостающих дат/категории, undo/redo.
//
// Часть кросс-композабловых вызовов (loadWishMembers/loadWishApprovers/ensureApprovers
// из useWishApprovers.ts, snapshotWishItemsFeo из useWishItemsFeoAutosave.ts) передаётся
// сюда через параметр hooks у openEditDialog/saveWish — это сохраняет ТОЧНО ту же
// последовательность вызовов внутри одного try/finally, что была в исходном файле
// (см. комментарии внутри), вместо циклической зависимости композаблов друг на друга.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useUndoRedo } from '@/composables/useUndoRedo'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoTreeNodes } from '@/composables/useFeoTreeNodes'
import { useFeoNodeAmounts } from '@/composables/useFeoNodeAmounts'
import { ACTIONS } from '@/constants/permissionActions'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import { numOrNull } from '@/utils/numberFormat'
import type { WishesContext } from './useWishesContext'
import type { Wish } from './wishTypes'

export interface OpenEditHooks {
  // Вызывается ПОСЛЕ заполнения формы/позиций, но ДО завершения try/finally
  // (wishDialogLoading всё ещё true) — ровно там же, где исходный openEditDialog
  // звал loadWishMembers/loadWishApprovers/снимки ФЭО.
  afterItemsFilled?: () => Promise<void> | void
}

export function useWishForm(deps: {
  ctx: WishesContext
  apiFetch: typeof import('@/api').apiFetch
  reloadActiveTab: () => Promise<void>
  ensureApprovers: (wishId: number) => Promise<boolean>
  // Участники, добавленные ДО первого сохранения новой заявки («совместное
  // создание») — живут в useWishApprovers.ts (wishMembers), но должны быть
  // прикреплены к заявке сразу после её создания здесь же, в saveWish (см.
  // оригинальный WishesView.vue::saveWish). getStagedMemberUserIds читает их
  // текущий список, reloadStagedMembers перезагружает его с сервера после
  // прикрепления (тот же loadWishMembers из useWishApprovers.ts).
  getStagedMemberUserIds: () => number[]
  reloadStagedMembers: () => Promise<void>
  // QA-фикс: оригинал (WishesView.vue::saveWish, ветка «черновик создан, но
  // ensureApprovers не нашёл согласующего») звал loadWishMembers()/loadWishApprovers()
  // ПЕРЕД reloadActiveTab() — обе живут в useWishApprovers.ts.
  reloadApprovers: () => Promise<void>
}) {
  const { ctx, apiFetch, reloadActiveTab, ensureApprovers, getStagedMemberUserIds, reloadStagedMembers, reloadApprovers } = deps
  const { showSnack, currentUserId, isAdmin, can } = ctx

  // Create/edit dialog
  const wishDialog = ref(false)
  const wishDialogLoading = ref(false)
  const editingWishId = ref<number | null>(null)
  const editingWish = ref<Wish | null>(null)
  const wishDateMode = ref<'common' | 'per_item'>('common')

  // T3: error state for «missing needed dates» when converting/approving
  const wishConvertError = ref<{ message: string; missingItemIds: number[]; missingItemNames: string[] } | null>(null)

  watch(wishDialog, (v) => { if (!v) { dismissValidationArrows(); wishConvertError.value = null } })

  watch(wishDateMode, (mode, prev) => {
    if (mode === 'per_item' && prev === 'common') {
      const d = wishForm.value.desired_date
      if (!d) return
      for (const it of wishForm.value.items as any[]) {
        if (!it.needed_date) it.needed_date = d
      }
    }
  })

  // Владелец (сессия 2026-08-19): «Должна быть возможность задать дату поставки всем
  // позициям заявки одновременно».
  function applyCommonDateToAllItems() {
    const d = wishForm.value.desired_date
    if (!d) return
    const items = (wishForm.value.items as any[]).filter(
      (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
    )
    if (!items.length) return
    const hasDifferent = items.some((it) => it.needed_date && it.needed_date !== d)
    if (hasDifferent) {
      if (!confirm('У части позиций уже указана другая дата поставки. Заменить её выбранной датой у ВСЕХ позиций?')) return
    }
    for (const it of items) it.needed_date = d
    showSnack('Дата поставки проставлена всем позициям')
  }

  const wishFormRef = ref<any>(null)
  const wishSubmitBtnRef = ref<any>(null)

  // Стрелочки к незаполненным полям (паттерн из CreateOrderView)
  const validationArrowsActive = ref(false)
  const validationArrowFrom = ref<HTMLElement | null>(null)
  const validationArrowTargets = ref<HTMLElement[]>([])
  let validationArrowsTimer: number | null = null
  function dismissValidationArrows() {
    validationArrowsActive.value = false
    validationArrowFrom.value = null
    validationArrowTargets.value = []
    if (validationArrowsTimer) { window.clearTimeout(validationArrowsTimer); validationArrowsTimer = null }
  }
  // Общий хелпер: рисует стрелки от кнопки «Отправить/Сохранить» к переданным целям.
  function pointArrowsTo(targets: HTMLElement[]) {
    if (!targets.length) return
    const btn = (wishSubmitBtnRef.value?.$el ?? wishSubmitBtnRef.value) as HTMLElement | null
    if (!btn) return
    validationArrowFrom.value = btn
    validationArrowTargets.value = targets.slice(0, 8)
    validationArrowsActive.value = true
    if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
    validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
  }
  function showValidationArrows() {
    const formEl = wishFormRef.value?.$el as HTMLElement | undefined
    if (!formEl) return
    const allErrors = Array.from(formEl.querySelectorAll('.v-input.v-input--error')) as HTMLElement[]
    if (!allErrors.length) return
    const headerErrors = allErrors.filter(el => el.closest('[data-field]'))
    const restErrors = allErrors.filter(el => !el.closest('[data-field]'))
    const errors = [...headerErrors, ...restErrors].slice(0, 8)
    const btn = (wishSubmitBtnRef.value?.$el ?? wishSubmitBtnRef.value) as HTMLElement | null
    if (!btn) return
    errors[0]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    validationArrowFrom.value = btn
    validationArrowTargets.value = errors.slice(0, 8)
    validationArrowsActive.value = true
    if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
    validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
  }
  const saving = ref(false)
  // Серверные ошибки валидации по полям: {desired_date: 'неверный формат даты'}.
  const serverFieldErrors = ref<Record<string, string>>({})

  const wishForm = ref({
    title: '' as string,
    subsidy_id: null as number | null,
    feo_category_id: null as number | null,
    assigned_to: null as number | null,
    event_id: null as number | null,
    justification: '',
    priority: 'medium' as string,
    desired_date: '',
    items: [] as any[],
    status: 'draft' as string,
    executor_id: null as number | null,
    execution_deadline: '' as string,
    vat_mode: 'uniform' as string,
    contractor_id: null as number | null,
    contractor_name: '' as string,
    feo_per_item: false as boolean,
  })

  // Название субсидии для «ствола» дерева ФЭО (FeoTreeSelect rootLabel).
  const selectedSubsidyName = computed((): string | null =>
    ctx.subsidies.value.find(s => s.id === wishForm.value.subsidy_id)?.name ?? null
  )

  const eventsForSubsidy = computed(() => {
    const filtered = wishForm.value.subsidy_id
      ? ctx.events.value.filter(e => e.subsidy_id === wishForm.value.subsidy_id && (e.is_active !== false))
      : []
    const selId = wishForm.value.event_id
    if (selId && !filtered.find(e => e.id === selId)) {
      const fromAll = ctx.events.value.find(e => e.id === selId)
      if (fromAll) {
        filtered.unshift(fromAll)
      } else if ((editingWish.value as any)?.event_name) {
        filtered.unshift({
          id: selId,
          name: (editingWish.value as any).event_name,
          subsidy_id: wishForm.value.subsidy_id || 0,
          is_active: true,
        })
      }
    }
    return filtered
  })

  // FEO: динамический каскад (глубина = реальная глубина дерева, не 3 захардкоженных уровня).
  const wishFeoSelected = ref<number | null>(null)

  const wishFeoPerItemDisableDialog = ref(false)
  const wishFeoPerItemDisableCount = ref(0)
  function onWishFeoPerItemChange(val: boolean | null) {
    if (val) return // включение — безопасно, ничего подтверждать не нужно
    const relevantItems = (wishForm.value.items as any[])
      .filter((it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
    const distinctCats = new Set(
      relevantItems.map((it) => it.feo_category_id).filter((id) => id != null)
    )
    if (distinctCats.size > 1) {
      wishFeoPerItemDisableCount.value = distinctCats.size
      wishFeoPerItemDisableDialog.value = true
      wishForm.value.feo_per_item = true // держим тумблер включённым, пока владелец не подтвердит
      return
    }
    if (distinctCats.size === 1) {
      const onlyCatId = distinctCats.values().next().value as number
      wishFeoSelected.value = onlyCatId
      for (const it of wishForm.value.items as any[]) {
        it.feo_category_id = null
      }
    }
  }
  function cancelWishFeoPerItemDisable() {
    wishForm.value.feo_per_item = true
    wishFeoPerItemDisableDialog.value = false
  }
  function confirmWishFeoPerItemDisable() {
    for (const it of wishForm.value.items as any[]) {
      it.feo_category_id = null
      it.feo_planned_item_id = null
    }
    wishForm.value.feo_per_item = false
    wishFeoPerItemDisableDialog.value = false
  }

  const orgMembers = ref<import('./wishTypes').User[]>([])
  async function loadOrgMembers(sid: number | null) {
    orgMembers.value = []
    if (!sid) return
    try {
      orgMembers.value = await apiFetch<import('./wishTypes').User[]>(`/users/?subsidy_id=${sid}`)
    } catch { orgMembers.value = [] }
  }
  const orgUsers = computed(() => {
    if (!wishForm.value.subsidy_id) return ctx.users.value
    if (orgMembers.value.length) return orgMembers.value
    return ctx.users.value
  })

  // Должность сотрудника: per-org → fallback на legacy User.position/department
  function resolveUserPosition(u: any): string {
    if (!u) return ''
    const targetOrgId = ctx.subsidies.value.find(s => s.id === wishForm.value.subsidy_id)?.org_id
    if (targetOrgId && Array.isArray(u.organizations)) {
      const match = u.organizations.find((o: any) => o.org_id === targetOrgId || o.id === targetOrgId)
      if (match?.position) return match.position
    }
    return u.position || u.department || ''
  }

  // Task 2 (сессия 2026-08-17): предзаполнение ContractorPicker при открытии карточки.
  const wishContractorInitial = computed(() => {
    const id = wishForm.value.contractor_id
    if (!id) return null
    const name = editingWish.value?.contractor_display_name || `Контрагент #${id}`
    return { id, name }
  })
  function onWishContractorSelect(c: { id: number; name: string } | null) {
    if (c) wishForm.value.contractor_name = ''
  }

  // ФЭО-дерево субсидии (узлы + листья с бюджетами) — объявлено ПОСЛЕ wishForm (TDZ)
  const { feoLeaves: wishFeoLeaves, feoNodes: wishFeoNodes } = useFeoLeaves({
    subsidyId: computed(() => wishForm.value.subsidy_id),
  })
  const { feoTreeNodes: wishFeoTreeNodes, rawNodes: wishFeoTreeRawNodes } = useFeoTreeNodes(
    computed(() => wishForm.value.subsidy_id),
    computed(() => wishFeoSelected.value),
  )
  const { nodeAmounts: wishNodeAmounts } = useFeoNodeAmounts({
    subsidyId: computed(() => wishForm.value.subsidy_id),
  })

  function collectFeoDescendantIds(rootId: number): Set<number> {
    const childrenByParent = new Map<number, number[]>()
    for (const n of wishFeoNodes.value) {
      if (n.parent_id != null) {
        const arr = childrenByParent.get(n.parent_id) || []
        arr.push(n.id)
        childrenByParent.set(n.parent_id, arr)
      }
    }
    const result = new Set<number>()
    const stack = [rootId]
    while (stack.length) {
      const id = stack.pop() as number
      for (const childId of childrenByParent.get(id) || []) {
        if (!result.has(childId)) {
          result.add(childId)
          stack.push(childId)
        }
      }
    }
    return result
  }
  const wishFeoBranchHasPlannedItems = computed((): boolean => {
    const items = (wishForm.value.items as any[]).filter(
      (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
    )
    const catIds = new Set<number>()
    for (const it of items) {
      const cid = it.feo_category_id ?? wishFeoSelected.value
      if (cid != null) catIds.add(cid)
    }
    for (const cid of catIds) {
      const ids = collectFeoDescendantIds(cid)
      ids.add(cid)
      if (wishPlannedResiduals.value.some(r => ids.has(r.category_id))) return true
    }
    return false
  })

  const {
    plannedResiduals: wishPlannedResiduals,
    plannedByCategory: wishPlannedByCategory,
    reloadPlanned: reloadWishPlanned,
  } = useFeoPlannedResiduals({
    subsidyId: computed(() => wishForm.value.subsidy_id),
    excludeWishId: computed(() => editingWishId.value),
  })

  async function onWishPlannedItemCreated() {
    await reloadWishPlanned()
  }

  const wishFeoStale = computed(() => {
    const id = wishFeoSelected.value
    return !!id && wishFeoNodes.value.length > 0 && !wishFeoNodes.value.some(n => n.id === id)
  })

  const wishItemsMissingFeoCategory = computed(() => {
    const items = (wishForm.value.items as any[]).filter(
      (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
    )
    if (!items.length) return [] as any[]
    if (!wishForm.value.feo_per_item) {
      const catId = wishFeoSelected.value
      if (catId == null) return items
      const node = wishFeoNodes.value.find(n => n.id === catId)
      return (node && !node.is_leaf) ? items : []
    }
    return items.filter((it) => {
      const catId = it.feo_category_id ?? wishFeoSelected.value
      if (catId == null) return true
      const node = wishFeoNodes.value.find(n => n.id === catId)
      return !!node && !node.is_leaf
    })
  })
  const wishFeoCategoryMissing = computed(() => wishItemsMissingFeoCategory.value.length > 0)
  const wishFeoCategoryMissingTooltip = computed(() =>
    wishForm.value.feo_per_item
      ? 'Не у всех позиций выбрана категория ФЭО — заполните её в таблице позиций выше, иначе заявку нельзя будет согласовать'
      : 'Категория ФЭО заявки не выбрана (или не до конечного уровня) — заполните её в блоке выше, иначе заявку нельзя будет согласовать'
  )
  const wishItemsWithStaleFeoCategory = computed(() => {
    if (!wishFeoNodes.value.length) return [] as any[]
    const items = (wishForm.value.items as any[]).filter(
      (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
    )
    return items.filter((it) => it.feo_category_id != null && !wishFeoNodes.value.some(n => n.id === it.feo_category_id))
  })

  // «Не определена» — парковка категории заявки (вызывается из @pick-unallocated каскада)
  async function pickWishUnallocated(parentId: number | null) {
    const sid = wishForm.value.subsidy_id
    if (!sid) return
    try {
      const body: Record<string, unknown> = { subsidy_id: sid }
      if (parentId != null) body.parent_id = parentId
      const cat = await apiFetch<{ id: number; name: string; parent_id?: number | null }>('/feo-categories/unallocated', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      // Добавить в wishFeoNodes если отсутствует, пометив родителя not-leaf
      if (!wishFeoNodes.value.find(n => n.id === cat.id)) {
        const parentNode = cat.parent_id != null ? wishFeoNodes.value.find(n => n.id === cat.parent_id) : null
        const newNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentNode ? parentNode.level + 1 : 1, is_leaf: true } as any
        const updated = [...wishFeoNodes.value, newNode]
        if (cat.parent_id != null) {
          const pi = updated.findIndex(n => n.id === cat.parent_id)
          if (pi !== -1) updated[pi] = { ...updated[pi], is_leaf: false }
        }
        wishFeoNodes.value = updated
      }
      // Тот же псевдо-узел — в rawNodes composable'а useFeoTreeNodes (источник шапочного
      // FeoTreeSelect, :nodes="wishFeoTreeNodes"): без этого дерево не знает о только что
      // созданной категории «Не определена» и не может отрисовать её как выбранную.
      if (!wishFeoTreeRawNodes.value.find(n => n.id === cat.id)) {
        const parentRawNode = cat.parent_id != null ? wishFeoTreeRawNodes.value.find(n => n.id === cat.parent_id) : null
        const newRawNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentRawNode ? parentRawNode.level + 1 : 1, is_leaf: true } as any
        const updatedRaw = [...wishFeoTreeRawNodes.value, newRawNode]
        if (cat.parent_id != null) {
          const pi = updatedRaw.findIndex(n => n.id === cat.parent_id)
          if (pi !== -1) updatedRaw[pi] = { ...updatedRaw[pi], is_leaf: false }
        }
        wishFeoTreeRawNodes.value = updatedRaw
      }
      wishFeoSelected.value = cat.id
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
    }
  }

  // Владелец, 2026-08-13: чип «в закупке иначе» — расхождение позиции заявки с
  // сопоставленной позицией закупки (категория ФЭО/кол-во/цена).
  function moneyRoundedEq(a: number | null | undefined, b: number | null | undefined): boolean {
    if (a == null || b == null) return true
    return Math.round(Number(a) * 100) === Math.round(Number(b) * 100)
  }
  function itemDiscrepancy(item: any): { lines: string[] } | null {
    const pm = item?.purchase_match
    if (!pm || pm.match_method === 'item_name_ambiguous') return null
    const lines: string[] = []
    const ownCategoryId = item.feo_category_id ?? wishFeoSelected.value
    if (pm.feo_category_id != null && ownCategoryId != null && pm.feo_category_id !== ownCategoryId) {
      const ownName = ctx.feoCategoryNameById(ownCategoryId) || '—'
      const purchName = pm.feo_category_name || ctx.feoCategoryNameById(pm.feo_category_id) || '—'
      lines.push(`категория: «${ownName}» → «${purchName}»`)
    }
    if (pm.quantity != null && item.quantity != null && !moneyRoundedEq(item.quantity, pm.quantity)) {
      lines.push(`количество: ${item.quantity} → ${pm.quantity}`)
    }
    if (pm.unit_price != null && item.unit_price != null && !moneyRoundedEq(item.unit_price, pm.unit_price)) {
      lines.push(`цена: ${ctx.formatMoney(item.unit_price)} → ${ctx.formatMoney(pm.unit_price)}`)
    }
    if (!lines.length) return null
    return { lines }
  }
  // Есть что показать построчно: остановлена / расхождение / неоднозначный двойник
  function wishItemStatus(item: any): boolean {
    const pm = item?.purchase_match
    if (!pm) return false
    if (pm.purchase_stopped_at) return true
    if (pm.match_method === 'item_name_ambiguous') return true
    return !!itemDiscrepancy(item)
  }

  function highlightMissingFeoCategory() {
    const formEl = wishFormRef.value?.$el as HTMLElement | undefined
    const target = formEl?.querySelector('[data-field="feo_category"]') as HTMLElement | null
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.classList.add('wish-date-missing-pulse')
    setTimeout(() => target.classList.remove('wish-date-missing-pulse'), 3000)
    pointArrowsTo([target])
  }
  function highlightMissingApprovers() {
    const formEl = wishFormRef.value?.$el as HTMLElement | undefined
    const target = formEl?.querySelector('[data-field="approvers"]') as HTMLElement | null
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.classList.add('wish-date-missing-pulse')
    setTimeout(() => target.classList.remove('wish-date-missing-pulse'), 3000)
    pointArrowsTo([target])
  }
  function focusApproversField() {
    const formEl = wishFormRef.value?.$el as HTMLElement | undefined
    const target = formEl?.querySelector('[data-field="approvers"]') as HTMLElement | null
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const input = target.querySelector('input') as HTMLInputElement | null
    input?.focus()
  }
  async function onAddApproversClick() {
    if (editingWishId.value) { focusApproversField(); return }
    const ok = await saveWish(false)
    if (!ok) return
    await nextTick()
    focusApproversField()
  }

  // Phase 31-07: Undo/Redo for wish edit form
  const undoRedoWish = useUndoRedo(wishForm as any)
  let _wishPendingBlur: { field: string; before: unknown } | null = null
  const _wishFocusinHandler = (e: FocusEvent) => {
    const t = e.target as HTMLElement | null
    if (!t) return
    const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
    if (!field) return
    _wishPendingBlur = { field, before: (wishForm.value as any)[field] }
  }
  const _wishFocusoutHandler = (e: FocusEvent) => {
    if (!_wishPendingBlur) return
    const t = e.target as HTMLElement | null
    if (!t) return
    const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
    if (field && field === _wishPendingBlur.field) {
      undoRedoWish.push(field, _wishPendingBlur.before, (wishForm.value as any)[field])
    }
    _wishPendingBlur = null
  }
  onMounted(() => {
    document.addEventListener('focusin', _wishFocusinHandler, true)
    document.addEventListener('focusout', _wishFocusoutHandler, true)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('focusin', _wishFocusinHandler, true)
    document.removeEventListener('focusout', _wishFocusoutHandler, true)
  })

  watch(() => wishForm.value.subsidy_id, (sid) => { loadOrgMembers(sid) }, { immediate: true })

  const totalNmck = computed(() =>
    wishForm.value.items.reduce((sum, i) => sum + (i.total_price || 0), 0)
  )

  function onSubsidyChange() {
    wishFeoSelected.value = null
    wishForm.value.assigned_to = null
    wishForm.value.event_id = null
  }

  const isWishEditable = computed(() => {
    if (!editingWishId.value) return true
    const status = (wishForm.value as any).status || 'draft'
    if (['draft', 'rejected'].includes(status)) return true
    if (['approved', 'converted'].includes(status)) return !editingWish.value?.contracted_locked
    return false
  })
  const isDialogAssignee = computed(() =>
    !!editingWish.value && editingWish.value.assigned_to === currentUserId
  )
  const isDialogCreator = computed(() =>
    !!editingWish.value && editingWish.value.created_by === currentUserId
  )
  const canAssigneeAct = computed(() =>
    !!editingWish.value
    && editingWish.value.status === 'submitted'
    && (isDialogAssignee.value || isAdmin.value)
  )
  // Согласующий из цепочки — заполняется извне (useWishApprovers), см. setIsChainApprover.
  const _isChainApproverRef = ref(false)
  const isChainApprover = computed(() => _isChainApproverRef.value)
  function setIsChainApprover(v: boolean) { _isChainApproverRef.value = v }

  const canEditWishFeo = computed(() =>
    can(ACTIONS.WISH_EDIT_FEO!)
    && (
      canAssigneeAct.value
      || (!!editingWish.value && editingWish.value.status === 'submitted' && isChainApprover.value)
    )
  )
  const canEditAssignee = computed(() =>
    !!editingWish.value
    && ['submitted', 'approved'].includes(editingWish.value.status)
    && (ctx.isManagerOrAdmin.value || isChainApprover.value || editingWish.value.assigned_to === currentUserId)
  )

  function resetForm() {
    serverFieldErrors.value = {}
    wishForm.value = {
      title: '',
      subsidy_id: null,
      feo_category_id: null,
      assigned_to: null,
      event_id: null,
      justification: '',
      priority: 'medium',
      desired_date: '',
      items: [],
      status: 'draft',
      executor_id: null,
      execution_deadline: '',
      vat_mode: 'uniform',
      contractor_id: null,
      contractor_name: '',
      feo_per_item: false,
    }
    wishFeoSelected.value = null
    wishDateMode.value = 'common'
  }

  function openCreateDialog() {
    ctx.clearStaleSuccessToasts()
    editingWishId.value = null
    editingWish.value = null
    resetForm()
    undoRedoWish.clear() // Phase 31-07: fresh stack per dialog open
    wishDialog.value = true
  }

  async function openEditDialog(wish: Wish, hooks?: OpenEditHooks) {
    ctx.clearStaleSuccessToasts()
    undoRedoWish.clear() // Phase 31-07: fresh stack per dialog open
    editingWishId.value = wish.id
    editingWish.value = wish
    resetForm()
    wishForm.value.title = wish.title || ''
    wishForm.value.subsidy_id = wish.subsidy_id ?? null
    loadOrgMembers(wishForm.value.subsidy_id)
    wishForm.value.feo_category_id = wish.feo_category_id ?? null
    wishForm.value.assigned_to = wish.assigned_to ?? null
    wishForm.value.event_id = (wish as any).event_id ?? null
    wishForm.value.executor_id = (wish as any).executor_id ?? null
    wishForm.value.execution_deadline = (wish as any).execution_deadline ? String((wish as any).execution_deadline).slice(0, 10) : ''
    wishForm.value.justification = wish.justification || ''
    wishForm.value.priority = wish.priority || 'medium'
    wishForm.value.desired_date = wish.desired_date || ''
    wishForm.value.status = wish.status || 'draft'
    wishForm.value.vat_mode = (wish as any).vat_mode || 'uniform'
    wishForm.value.contractor_id = (wish as any).contractor_id ?? null
    wishForm.value.contractor_name = (wish as any).contractor_name || ''
    wishForm.value.feo_per_item = (wish as any).feo_per_item ?? false

    wishFeoSelected.value = wish.feo_category_id ?? null

    // Открываем диалог СРАЗУ после синхронного заполнения формы — пользователь
    // видит окно мгновенно, а тяжёлая загрузка позиций идёт под спиннером.
    wishDialog.value = true
    wishDialogLoading.value = true

    try {
      let rawItems: any[] = []
      try {
        const fresh = await apiFetch<any>(`/wishes/${wish.id}`)
        if (Array.isArray(fresh?.items)) rawItems = fresh.items
        if (editingWish.value && editingWish.value.id === wish.id) {
          editingWish.value = {
            ...editingWish.value,
            contracted_locked: fresh?.contracted_locked,
            contracted_locked_reason: fresh?.contracted_locked_reason,
            source: fresh?.source,
          }
        }
      } catch {}
      if (!rawItems.length && Array.isArray((wish as any).items) && (wish as any).items.length > 0) {
        rawItems = (wish as any).items
      }

      const needsBackfill = rawItems.some((i: any) => !i.product_id && i.item_name)
      const hasProductIds = rawItems.some((i: any) => i.product_id != null)
      let byId = new Map<number, any>()
      if (needsBackfill || hasProductIds) {
        try {
          const products = await apiFetch<any[]>('/products/?limit=10000')
          const byName = new Map<string, any>(
            (products || []).map((p: any) => [(p.name || '').trim().toLowerCase(), p])
          )
          byId = new Map<number, any>((products || []).map((p: any) => [p.id, p]))
          for (const it of rawItems) {
            if (!it.product_id && it.item_name) {
              const hit = byName.get(it.item_name.trim().toLowerCase())
              if (hit) it.product_id = hit.id
            }
          }
        } catch {}
      }

      const photoOf = (p: any): string | undefined => {
        if (!p) return undefined
        if (p.has_photo) return `/api/products/${p.id}/photo`
        return p.photo_url || p.photo_link || undefined
      }

      wishForm.value.items = rawItems.map((i: any) => {
        const prod = i.product_id != null ? byId.get(i.product_id) : null
        return {
          id: i.id ?? null,
          product_id: i.product_id ?? null,
          item_name: i.item_name || '',
          item_type: i.item_type || 'товар',
          quantity: i.quantity != null ? Number(i.quantity) : null,
          unit: i.unit || 'шт.',
          unit_price: i.unit_price != null ? Number(i.unit_price) : null,
          total_price: i.total_price != null ? Number(i.total_price) : null,
          country_origin: i.country_origin || 'РФ',
          feo_category_id: i.feo_category_id ?? null,
          feo_planned_item_id: i.feo_planned_item_id ?? null,
          over_plan: i.over_plan ?? false,
          vat_rate: i.vat_rate ?? null,
          needed_date: i.needed_date ?? null,
          purchase_match: i.purchase_match ?? null,
          _photo_url: prod ? photoOf(prod) : undefined,
          _description: prod?.description || undefined,
          _price_meta: prod ? {
            price_updated_at: prod.price_updated_at ?? null,
            price_source: prod.price_source ?? null,
            price_source_ref: prod.price_source_ref ?? null,
            price_freshness: prod.price_freshness ?? null,
          } : null,
        }
      }) as any
      if (wishFeoSelected.value != null) {
        for (const it of wishForm.value.items as any[]) {
          if (it.feo_category_id == null) it.feo_category_id = wishFeoSelected.value
        }
      }

      wishDateMode.value = (wishForm.value.items as any[]).some(it => it.needed_date) ? 'per_item' : 'common'
      await hooks?.afterItemsFilled?.()
    } finally {
      wishDialogLoading.value = false
    }
  }

  const wishFormSavedSnapshot = ref<string>('')

  function buildWishPayload() {
    const feo = wishFeoSelected.value
    let title = (wishForm.value.title || '').trim().slice(0, 255)
    if (!title) {
      const names = wishForm.value.items.map(i => i.item_name).filter(Boolean)
      title = names.join(', ') || 'Новая заявка'
      if (title.length > 255) {
        title = names.length > 1
          ? `${names[0].slice(0, 120)} + ещё ${names.length - 1} поз.`
          : names[0].slice(0, 252) + '…'
      }
    }
    return {
      ...wishForm.value,
      feo_category_id: feo,
      feo_per_item: wishForm.value.feo_per_item,
      title,
      contractor_id: wishForm.value.contractor_id || null,
      contractor_name: (wishForm.value.contractor_name || '').toString().trim() || null,
      items: wishForm.value.items
        .filter((it: any) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
        .map(({ _selectedProduct, _photo_url, _description, _description_44fz, _price_meta, ...rest }) => ({
          ...rest,
          quantity: numOrNull((rest as any).quantity),
          unit_price: numOrNull((rest as any).unit_price),
          total_price: numOrNull((rest as any).total_price),
          feo_category_id: wishForm.value.feo_per_item
            ? ((rest as any).feo_category_id ?? feo ?? null)
            : (feo ?? null),
          feo_planned_item_id: (rest as any).feo_planned_item_id ?? null,
          over_plan: !!((rest as any).over_plan),
        })),
    }
  }
  function wishPayloadSnapshotJson(): string {
    try { return JSON.stringify(buildWishPayload()) } catch { return '' }
  }

  async function saveWish(andSubmit = false): Promise<boolean> {
    if (andSubmit) {
      const { valid } = await wishFormRef.value?.validate() ?? { valid: true }
      if (!valid) { await nextTick(); showValidationArrows(); return false }
      if (wishFeoCategoryMissing.value) {
        const message = wishForm.value.feo_per_item
          ? `Нельзя отправить на согласование: не выбрана конечная категория ФЭО у позиций (${wishItemsMissingFeoCategory.value.map((it: any) => it.item_name || 'без названия').join(', ')}). Выберите категорию в таблице позиций, углубившись до конечного уровня, либо «Не определена», если категория неизвестна.`
          : 'Нельзя отправить на согласование: не выбрана конечная категория ФЭО заявки. Выберите категорию в блоке выше, углубившись до конечного уровня, либо «Не определена», если категория неизвестна.'
        showSnack(message, 'error')
        await nextTick()
        highlightMissingFeoCategory()
        return false
      }
      if (wishFeoBranchHasPlannedItems.value) {
        const wishLabel = (editingWishId.value ? `Заявка №${editingWishId.value}` : 'Новая заявка')
          + (wishForm.value.title ? ` «${wishForm.value.title}»` : '')
        const unfilledItems = (wishForm.value.items as any[])
          .map((it: any, idx: number) => ({ it, idx }))
          .filter(({ it }) => (
            ((it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
            && it.feo_planned_item_id == null
          ))
        if (unfilledItems.length > 0) {
          const names = unfilledItems.slice(0, 5)
            .map(({ it, idx }) => `№${idx + 1} «${it.item_name || 'без названия'}»`)
            .join(', ')
          const more = unfilledItems.length > 5 ? `, …и ещё ${unfilledItems.length - 5}` : ''
          showSnack(`${wishLabel}: позиции без плановой позиции плана закупок — ${names}${more}. Выберите её или создайте новую кнопкой «Создать в плане закупок» — без выбора позиция увеличит плановую сумму категории.`, 'warning')
        }
      }
    }

    saving.value = true
    try {
      const payload = buildWishPayload()

      if (editingWishId.value) {
        const currentStatus = (wishForm.value as any).status || 'draft'
        const putResp = await apiFetch<any>(`/wishes/${editingWishId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
        const newStatus = putResp?.status || currentStatus
        wishFormSavedSnapshot.value = JSON.stringify(payload)
        if (andSubmit && ['draft', 'rejected'].includes(currentStatus)) {
          const hasApprovers = await ensureApprovers(editingWishId.value)
          if (!hasApprovers) {
            showSnack('Не выбраны согласующие. Выберите «Верхнего согласующего» в разделе «Согласующие» — цепочка построится автоматически.', 'error')
            await nextTick()
            highlightMissingApprovers()
            return false
          }
          await apiFetch(`/wishes/${editingWishId.value}/submit`, { method: 'POST' })
          showSnack('Заявка отправлена на согласование')
        } else if (['approved', 'converted'].includes(currentStatus) && newStatus === 'submitted') {
          showSnack('Заявка изменена по существу и ушла на повторное согласование', 'error')
        } else if (['approved', 'converted'].includes(currentStatus)) {
          showSnack('Заявка обновлена, согласование сохранено')
        } else {
          showSnack('Заявка обновлена')
        }
      } else {
        const created = await apiFetch<any>('/wishes/', { method: 'POST', body: JSON.stringify(payload) })
        wishFormSavedSnapshot.value = JSON.stringify(payload)
        if (andSubmit && created?.id) {
          editingWishId.value = created.id
          const hasApprovers = await ensureApprovers(created.id)
          if (!hasApprovers) {
            showSnack('Черновик сохранён. Не выбраны согласующие. Выберите «Верхнего согласующего» в разделе «Согласующие» — цепочка построится автоматически.', 'error')
            await reloadStagedMembers()
            await reloadApprovers()
            await reloadActiveTab()
            await nextTick()
            highlightMissingApprovers()
            return false
          }
          await apiFetch(`/wishes/${created.id}/submit`, { method: 'POST' })
          showSnack('Заявка отправлена на согласование')
        } else if (created?.id) {
          // Прикрепляем участников, выбранных до сохранения (совместное создание).
          const staged = getStagedMemberUserIds()
          for (const uid of staged) {
            try {
              await apiFetch(`/wishes/${created.id}/members`, {
                method: 'POST', body: JSON.stringify({ user_id: uid, role: 'participant' }),
              })
            } catch { /* дубликат/нет прав — пропускаем, не роняем сохранение */ }
          }
          // Черновик создан → переходим в режим редактирования, НЕ закрывая диалог,
          // чтобы блок «Участники заявки» остался виден и заявку можно было
          // дорасшарить нескольким людям.
          editingWishId.value = created.id
          showSnack(staged.length
            ? 'Черновик сохранён, участники добавлены'
            : 'Черновик сохранён — добавьте участников для совместной работы')
          await reloadStagedMembers()
          await reloadActiveTab()
          return true
        }
      }

      wishDialog.value = false
      await reloadActiveTab()
      return true
    } catch (e: any) {
      if (await handleMissingDatesError(e, editingWish.value)) {
        return false
      }
      const fields = e?.payload?.fields
      if (Array.isArray(fields) && fields.length) {
        serverFieldErrors.value = {}
        for (const f of fields) {
          serverFieldErrors.value[f.field] = e?.payload?.message?.includes('обязательно')
            ? 'Заполните это поле'
            : 'Проверьте значение'
        }
        await nextTick()
        showValidationArrows()
        document.querySelector('.v-overlay--active .v-input--error')
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
      const msg = e?.payload?.message || e?.message || 'неизвестная ошибка'
      showSnack(`Не удалось сохранить: ${msg}`, 'error')
      return false
    } finally {
      saving.value = false
    }
  }

  // T3: общий обработчик 409 missing_needed_dates — используется в approveWish/saveWish/submitWish.
  async function handleMissingDatesError(e: any, wish?: Wish | null) {
    const det = e?.payload?.details
    if (e?.status !== 409 || det?.error_code !== 'missing_needed_dates') return false
    const missingIds: number[] = det.missing_item_ids || []
    const missingNames: string[] = det.missing_item_names || []
    wishConvertError.value = {
      message: det.message || e.message,
      missingItemIds: missingIds,
      missingItemNames: missingNames,
    }
    if (!wishDialog.value && wish) {
      await openEditDialog(wish)
    }
    if (missingIds.length > 0) {
      if (wishDateMode.value !== 'per_item') wishDateMode.value = 'per_item'
      await nextTick()
      highlightMissingDateItems(missingIds, missingNames)
    } else {
      await nextTick()
      highlightCommonDateField()
    }
    return true
  }

  // Гейт ФЭО (владелец, 2026-08-11): общий обработчик 409 missing_feo_category.
  async function handleMissingFeoCategoryError(e: any, wish: Wish): Promise<boolean> {
    const det = e?.payload?.details
    if (e?.status !== 409 || det?.error_code !== 'missing_feo_category') return false
    showSnack(det.message || e.message || 'Не выбрана категория ФЭО', 'error')
    if (!wishDialog.value) {
      await openEditDialog(wish)
    }
    await nextTick()
    highlightMissingFeoCategory()
    return true
  }

  // ── T3: highlight items without needed_date ──────────────────────────────
  function highlightMissingDateItems(missingItemIds: number[], missingItemNames: string[] = []) {
    if (!missingItemIds.length) return
    const dialogEl = document.querySelector('.v-dialog--active .v-card, .v-overlay--active .v-card') as HTMLElement | null
    if (!dialogEl) return

    const items = (wishForm.value as any).items as any[]
    let missingIndexes = new Set(
      items.map((it: any, idx: number) => missingItemIds.includes(it.id) ? idx : -1).filter((i: number) => i !== -1)
    )
    if (!missingIndexes.size && missingItemNames.length) {
      const namesNorm = new Set(missingItemNames.map(n => String(n).trim().toLowerCase()).filter(Boolean))
      missingIndexes = new Set(
        items
          .map((it: any, idx: number) => namesNorm.has(String(it.item_name || '').trim().toLowerCase()) ? idx : -1)
          .filter((i: number) => i !== -1)
      )
    }
    if (!missingIndexes.size) {
      missingIndexes = new Set(
        items
          .map((it: any, idx: number) => {
            const nonEmpty = (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
            return (nonEmpty && !it.needed_date) ? idx : -1
          })
          .filter((i: number) => i !== -1)
      )
    }
    if (!missingIndexes.size) {
      highlightCommonDateField()
      return
    }

    const dateInputs = Array.from(dialogEl.querySelectorAll('td input[type="date"]')) as HTMLInputElement[]
    const highlighted: HTMLElement[] = []
    missingIndexes.forEach(idx => {
      const inp = dateInputs[idx]
      if (inp) highlighted.push(inp.closest('td') as HTMLElement || inp)
    })

    if (!highlighted.length) {
      highlightCommonDateField()
      return
    }

    highlighted[0]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlighted.forEach(el => {
      el.classList.add('wish-date-missing-pulse')
      setTimeout(() => el.classList.remove('wish-date-missing-pulse'), 3000)
    })
    pointArrowsTo(highlighted)
  }

  function highlightCommonDateField() {
    const dialogEl = document.querySelector('.v-dialog--active .v-card, .v-overlay--active .v-card') as HTMLElement | null
    if (!dialogEl) return
    const allDateInputs = Array.from(dialogEl.querySelectorAll('input[type="date"]')) as HTMLInputElement[]
    const commonInput = allDateInputs.find(inp => !inp.closest('td'))
    if (commonInput) {
      commonInput.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const wrap = commonInput.closest('.v-field') as HTMLElement | null
      if (wrap) {
        wrap.classList.add('wish-date-missing-pulse')
        setTimeout(() => wrap.classList.remove('wish-date-missing-pulse'), 3000)
        pointArrowsTo([wrap])
      }
    }
  }

  // Superadmin: force-смена статуса.
  const WISH_FORCE_STATUS_OPTIONS = [
    { value: 'draft', title: 'Черновик' },
    { value: 'submitted', title: 'Отправлена' },
    { value: 'approved', title: 'Одобрена' },
    { value: 'rejected', title: 'Отклонена' },
    { value: 'converted', title: 'Конвертирована' },
  ]
  const forceStatusValue = ref<string>('draft')
  const forcingStatus = ref(false)
  async function forceStatus(wishId?: number): Promise<boolean> {
    const targetId = wishId ?? editingWishId.value
    if (!targetId) { showSnack('Сначала откройте заявку', 'warning'); return false }
    const label = WISH_FORCE_STATUS_OPTIONS.find(o => o.value === forceStatusValue.value)?.title || forceStatusValue.value
    if (!confirm(`Принудительно установить статус «${label}»? Workflow-проверки будут пропущены.`)) return false
    forcingStatus.value = true
    try {
      await apiFetch(`/wishes/${targetId}/status`, {
        method: 'POST',
        body: JSON.stringify({ status: forceStatusValue.value }),
      })
      showSnack(`Статус принудительно изменён на «${label}»`)
      await reloadActiveTab()
      return true
    } catch (e: any) {
      showSnack(`Ошибка force-status: ${e?.detail || e?.payload?.message || e?.message || 'не удалось'}`, 'error')
      return false
    } finally {
      forcingStatus.value = false
    }
  }
  const rowForceStatusWish = ref<Wish | null>(null)
  function openRowForceStatus(wish: Wish) {
    forceStatusValue.value = wish.status || 'draft'
    rowForceStatusWish.value = wish
  }
  async function applyRowForceStatus() {
    if (!rowForceStatusWish.value) return
    if (await forceStatus(rowForceStatusWish.value.id)) rowForceStatusWish.value = null
  }

  return {
    // core state
    wishDialog, wishDialogLoading, editingWishId, editingWish, wishDateMode, wishConvertError,
    applyCommonDateToAllItems, wishFormRef, wishSubmitBtnRef,
    validationArrowsActive, validationArrowFrom, validationArrowTargets, dismissValidationArrows,
    pointArrowsTo, showValidationArrows,
    saving, serverFieldErrors, wishForm, selectedSubsidyName, eventsForSubsidy,
    wishFeoSelected, wishFeoPerItemDisableDialog, wishFeoPerItemDisableCount,
    onWishFeoPerItemChange, cancelWishFeoPerItemDisable, confirmWishFeoPerItemDisable,
    orgMembers, loadOrgMembers, orgUsers, resolveUserPosition,
    wishContractorInitial, onWishContractorSelect,
    wishFeoLeaves, wishFeoNodes, wishFeoTreeNodes, wishFeoTreeRawNodes, wishNodeAmounts,
    collectFeoDescendantIds, wishFeoBranchHasPlannedItems,
    wishPlannedResiduals, wishPlannedByCategory, reloadWishPlanned, onWishPlannedItemCreated,
    wishFeoStale, wishItemsMissingFeoCategory, wishFeoCategoryMissing, wishFeoCategoryMissingTooltip,
    wishItemsWithStaleFeoCategory, pickWishUnallocated, itemDiscrepancy, wishItemStatus,
    highlightMissingFeoCategory, highlightMissingApprovers, focusApproversField, onAddApproversClick,
    undoRedoWish, totalNmck, onSubsidyChange,
    isWishEditable, isDialogAssignee, isDialogCreator, canAssigneeAct, isChainApprover, setIsChainApprover,
    canEditWishFeo, canEditAssignee,
    resetForm, openCreateDialog, openEditDialog,
    wishFormSavedSnapshot, buildWishPayload, wishPayloadSnapshotJson, saveWish,
    handleMissingDatesError, handleMissingFeoCategoryError,
    highlightMissingDateItems, highlightCommonDateField,
    WISH_FORCE_STATUS_OPTIONS, forceStatusValue, forcingStatus, forceStatus,
    rowForceStatusWish, openRowForceStatus, applyRowForceStatus,
  }
}

export type UseWishFormReturn = ReturnType<typeof useWishForm>
