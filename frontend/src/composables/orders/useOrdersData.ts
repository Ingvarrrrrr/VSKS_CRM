// useOrdersData.ts — загрузка списка закупок, пагинация карточек, итог по
// странице (filteredSum через toAmount/effectivePrice), выбор строк, массовые
// действия (bulk delete/статус), переходы статуса. Дословный перенос из
// OrdersView.vue, без изменения поведения.
import { computed, reactive, ref, watch } from 'vue'
import type { ToastType } from '@/composables/useToast'
import { apiFetch } from '@/api'
import type { OrdersFiltersState } from './useOrdersFilters'
import type { Purchase, Subsidy, Contractor } from './ordersTypes'
import { effectivePrice, getOrderTypeKey, isItemFramework, nextStatus, statusLabelFor, transitionRequired } from './ordersLabels'

export function useOrdersData(options: {
  filters: OrdersFiltersState
  matchesColumnFilters: (row: any) => boolean
  localSort: { value: { key: string; order: 'asc' | 'desc' } | null }
  getRowField: (row: any, key: string) => any
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { filters, matchesColumnFilters, localSort, getRowField, showSnack } = options

  const orders = ref<Purchase[]>([])
  // Возможные дубликаты в реестре: purchase_id -> группа {contractor_name, amount, items: [...]}.
  // Заполняется batch-эндпоинтом GET /purchases/duplicate-groups, без N+1 запросов по строкам.
  const duplicateGroupsMap = ref<Map<number, any>>(new Map())
  function dupGroupFor(item: any) { return duplicateGroupsMap.value.get(item.id) }
  const subsidies = ref<Subsidy[]>([])
  const contractors = ref<Contractor[]>([])
  const loading = ref(false)
  const transitioning = ref<number | null>(null)

  // Дедуп по имени контрагента — для авансовых contractor_id часто пуст.
  const contractorsForFilter = computed(() => {
    const byName = new Map<string, any>()
    for (const o of orders.value as any[]) {
      const name = o.contractor_name
      if (!name || byName.has(name)) continue
      const real = contractors.value.find(c =>
        (o.contractor_id && c.id === o.contractor_id) ||
        (o.contractor_inn && c.inn === o.contractor_inn) ||
        c.name === name
      )
      byName.set(name, real || { id: -byName.size - 1, name, inn: o.contractor_inn || '' })
    }
    return Array.from(byName.values())
  })

  const expanded = ref<string[]>([])
  const selectedOrders = ref<Purchase[]>([])

  const guardDialog = reactive({
    show: false, purchaseId: 0, targetStatus: '', missing: [] as string[], isFramework: false,
  })
  const deleteDialog = reactive({
    show: false, single: null as Purchase | null, bulk: false, deleting: false,
  })

  const filteredOrders = computed(() => {
    let r = orders.value
    if (filters.status) {
      const statuses = filters.status.split(',').map(s => s.trim()).filter(Boolean)
      r = r.filter(o => statuses.includes(o.status))
    }
    if (filters.subsidyId) r = r.filter(o => o.subsidy_id === filters.subsidyId)
    if (filters.wishId) r = r.filter(o => (o as any).wish_id === filters.wishId)
    if (filters.feoCategoryId) {
      // Владелец 2026-08-17: клик по сумме категории ФЭО (SubsidiesView) должен
      // находить закупку по КАЖДОЙ категории, к которой относится хоть одна её
      // позиция — тот же COALESCE(PurchaseItem.feo_category_id, Purchase.feo_category_id),
      // которым дерево ФЭО (backend/app/services/feo_plan.py, cat_col) считает деньги
      // категории. Раньше фильтр смотрел только на категорию самой закупки — закупка
      // с позициями в нескольких категориях (напр. #887: 3677/3691/3710 при шапке 3710)
      // не находилась по деньгам своих позиций.
      const target = filters.feoCategoryIds.size ? filters.feoCategoryIds : new Set([filters.feoCategoryId])
      r = r.filter(o => purchaseFeoCategoryIdsLocal(o).some(cid => target.has(cid)))
    }
    if (filters.method) r = r.filter(o => o.purchase_method === filters.method)
    if (filters.overdue) {
      const today = new Date().toISOString().slice(0, 10)
      r = r.filter(o => o.execution_term && o.execution_term < today && !['paid', 'delivered'].includes(o.status))
    }
    if (filters.dueSoon) {
      const today = new Date().toISOString().slice(0, 10)
      const in30  = new Date(Date.now() + 30 * 86400 * 1000).toISOString().slice(0, 10)
      r = r.filter(o => o.execution_term && o.execution_term >= today && o.execution_term <= in30 && !['paid', 'delivered'].includes(o.status))
    }
    if (filters.types.length > 0) {
      r = r.filter(o => filters.types.includes(getOrderTypeKey(o)))
    }
    if (filters.contractorIds.length > 0) {
      const allowedNames = new Set(
        contractorsForFilter.value
          .filter((c: any) => filters.contractorIds.includes(c.id))
          .map((c: any) => c.name)
      )
      r = r.filter(o => !!o.contractor_name && allowedNames.has(o.contractor_name))
    }
    // Поиск по товару (item_name позиций или subject закупки)
    if (filters.product && filters.product.trim()) {
      const q = filters.product.trim().toLowerCase()
      r = r.filter(o =>
        (o as any).items?.some((it: any) => it.item_name?.toLowerCase().includes(q)) ||
        o.subject?.toLowerCase().includes(q) ||
        o.item_name?.toLowerCase().includes(q)
      )
    }
    // Phase 31-06: filter to show only purchases with unseen foreign changes
    if (filters.onlyUnseen) r = r.filter(o => (o as any).unseen_changes_count > 0)
    // Phase 32: period filter — payment_doc_date if present, else contract_date
    if (filters.periodFrom || filters.periodTo) {
      r = r.filter(o => {
        const d = (o as any).payment_doc_date || o.contract_date
        if (!d) return false
        if (filters.periodFrom && d < filters.periodFrom) return false
        if (filters.periodTo && d > filters.periodTo) return false
        return true
      })
    }
    // Column-header filters (поверх panel-фильтров)
    r = r.filter(matchesColumnFilters)
    return r
  })

  const filteredOrdersWithRowNum = computed(() => {
    // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum.
    // Ключ Map — String(id) чтобы избежать number/string mismatch.
    const sorted = [...filteredOrders.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
    const map = new Map<string, number>()
    sorted.forEach((o, idx) => map.set(String(o.id), idx + 1))
    let result = filteredOrders.value.map(o => ({ ...o, _rownum: map.get(String(o.id)) ?? '' }))
    // Apply localSort from column-header menus
    if (localSort.value) {
      const { key, order } = localSort.value
      result = [...result].sort((a, b) => {
        const av = getRowField(a, key)
        const bv = getRowField(b, key)
        // Numeric-aware: если оба числа, сравниваем как числа
        const an = typeof av === 'number' ? av : parseFloat(av)
        const bn = typeof bv === 'number' ? bv : parseFloat(bv)
        let cmp: number
        if (!isNaN(an) && !isNaN(bn)) cmp = an - bn
        else cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'ru', { numeric: true })
        return order === 'asc' ? cmp : -cmp
      })
    }
    return result
  })

  // Cards pagination + selection (declared after filteredOrdersWithRowNum to avoid TDZ).
  // cardsSource also applies the free-text `search` (which the v-data-table handled
  // internally via :search — cards must replicate it to keep search interactive).
  const cardsPage = ref(1)
  const cardsPageSize = 24
  const cardsSource = computed(() => {
    const q = (filters.search || '').trim().toLowerCase()
    if (!q) return filteredOrdersWithRowNum.value
    return filteredOrdersWithRowNum.value.filter((o: any) =>
      [o.registry_number, o.subject, o.item_name, o.contractor_name, o.subsidy_name, o.contract_number, o.order_number, o.agreement_number]
        .some(v => String(v ?? '').toLowerCase().includes(q))
    )
  })
  const cardsTotalPages = computed(() => Math.max(1, Math.ceil(cardsSource.value.length / cardsPageSize)))
  const pagedCards = computed(() => { const s = (cardsPage.value - 1) * cardsPageSize; return cardsSource.value.slice(s, s + cardsPageSize) })
  watch(cardsTotalPages, t => { if (cardsPage.value > t) cardsPage.value = t })
  function isOrderSelected(item: any) { return selectedOrders.value.some((o: any) => o.id === item.id) }
  function toggleOrderSelected(item: any) { const i = selectedOrders.value.findIndex((o: any) => o.id === item.id); if (i >= 0) selectedOrders.value.splice(i, 1); else selectedOrders.value.push(item) }

  const filteredSum = computed(() =>
    filteredOrders.value.reduce((acc, o) => acc + (effectivePrice(o) ?? 0), 0)
  )

  // Все категории ФЭО, к которым относится закупка через свои позиции (см. ordersLabels.purchaseFeoCategoryIds).
  function purchaseFeoCategoryIdsLocal(o: Purchase): number[] {
    const ids = new Set<number>()
    if (o.items && o.items.length > 0) {
      for (const it of o.items) {
        const cid = it.feo_category_id ?? o.feo_category_id
        if (cid != null) ids.add(cid)
      }
    } else if (o.feo_category_id != null) {
      ids.add(o.feo_category_id)
    }
    return [...ids]
  }

  const loadOrders = async () => {
    loading.value = true
    try {
      // with_feo_excess=true — просим бэкенд досчитать feo_excess/feo_excess_hint
      // на элементах (задача владельца 2026-08-12, значок превышения ФЭО на
      // закупке). Если бэкенд ещё не знает этот параметр, лишний query-параметр
      // FastAPI молча игнорирует — список грузится как раньше, просто без чипа.
      orders.value = await apiFetch<Purchase[]>('/purchases/?scope=purchases&with_feo_excess=true')
    } catch {
      showSnack('Ошибка загрузки закупок', 'error')
    } finally {
      loading.value = false
    }
  }

  // Подсказка «возможный дубликат» в реестре — молча игнорируем ошибку загрузки,
  // это вспомогательная подсказка, а не критичные данные строки.
  const loadDuplicateGroups = async () => {
    try {
      const qs = filters.subsidyId ? `?subsidy_id=${filters.subsidyId}` : ''
      const groups = await apiFetch<any[]>(`/purchases/duplicate-groups${qs}`)
      const map = new Map<number, any>()
      for (const g of groups) {
        for (const pid of g.purchase_ids || []) map.set(pid, g)
      }
      duplicateGroupsMap.value = map
    } catch {
      // не блокируем реестр — просто не покажем подсказку
    }
  }

  const loadSubsidies = async (onSubsidyGone: () => void) => {
    try {
      subsidies.value = await apiFetch<Subsidy[]>('/subsidies/')
      // Если ранее выбранная субсидия больше недоступна (доступ отозван) —
      // сбросить выбор на «все доступные», иначе в селекторе залипал сырой id.
      if (filters.subsidyId && !subsidies.value.some(s => s.id === filters.subsidyId)) {
        filters.subsidyId = null
        onSubsidyGone()
      }
    } catch {}
  }

  watch(() => filters.subsidyId, () => { loadDuplicateGroups() })

  const doTransition = async (item: Purchase) => {
    const target = nextStatus(item.status)
    if (!target) return
    const required = transitionRequired(item)[target]
    if (required) {
      const missing = required.filter(r => !(item as any)[r.field]).map(r => r.label)
      if (missing.length) {
        guardDialog.purchaseId = item.id
        guardDialog.targetStatus = target
        guardDialog.missing = missing
        guardDialog.isFramework = isItemFramework(item)
        guardDialog.show = true
        return
      }
    }
    transitioning.value = item.id
    try {
      const res = await apiFetch<any>(`/purchases/${item.id}/transition?status=${target}`, { method: 'POST' })
      // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» — см.
      // app.services.feo_plan.assert_no_unapproved_excess. Форвард-переход больше не
      // блокируется превышением плана ОТДЕЛЬНОЙ категории ФЭО над её финансированием,
      // но факт перекоса обязан быть виден — excess_warnings в ответе.
      if (res?.excess_warnings?.length) {
        showSnack(`Статус изменён → ${statusLabelFor(item, target)}. ` + res.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
      } else {
        showSnack(`Статус изменён → ${statusLabelFor(item, target)}`)
      }
      await loadOrders()
    } catch (e: any) {
      showSnack(e?.detail || e?.message || 'Ошибка перехода', 'error')
    } finally {
      transitioning.value = null
    }
  }

  const doForceStatus = async (item: Purchase, status: string) => {
    if (item.status === status) return
    transitioning.value = item.id
    try {
      const res = await apiFetch<any>(`/purchases/${item.id}/transition?status=${status}`, { method: 'POST' })
      if (res?.excess_warnings?.length) {
        showSnack(`Статус изменён → ${statusLabelFor(item, status)}. ` + res.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
      } else {
        showSnack(`Статус изменён → ${statusLabelFor(item, status)}`)
      }
      await loadOrders()
    } catch (e: any) {
      showSnack(e?.detail || e?.message || 'Ошибка изменения статуса', 'error')
    } finally {
      transitioning.value = null
    }
  }

  const confirmDeleteOne = (item: Purchase) => {
    deleteDialog.single = item
    deleteDialog.bulk = false
    deleteDialog.show = true
  }

  const confirmBulkDelete = () => {
    deleteDialog.single = null
    deleteDialog.bulk = true
    deleteDialog.show = true
  }

  const bulkChangeStatus = async (status: string) => {
    const ids = selectedOrders.value.map(o => o.id)
    let ok = 0, fail = 0
    for (const id of ids) {
      try {
        await apiFetch<any>(`/purchases/${id}/transition?status=${status}`, { method: 'POST' })
        const idx = orders.value.findIndex(o => o.id === id)
        if (idx >= 0) orders.value[idx]!.status = status
        ok++
      } catch { fail++ }
    }
    selectedOrders.value = []
    showSnack(`Обновлено: ${ok}${fail ? `, ошибок: ${fail}` : ''}`, fail ? 'warning' : 'success')
  }

  const doDelete = async () => {
    deleteDialog.deleting = true
    try {
      if (deleteDialog.bulk) {
        const ids = selectedOrders.value.map(o => o.id)
        const res = await apiFetch<{ deleted: number[]; failed?: any[] }>('/purchases/bulk', {
          method: 'DELETE',
          body: JSON.stringify(ids),
        })
        const deletedIds = new Set<number>(res.deleted)
        selectedOrders.value = selectedOrders.value.filter(o => !deletedIds.has(o.id))
        if (res.failed?.length) {
          showSnack(`Удалено: ${res.deleted.length}, не удалось: ${res.failed.length}`, 'warning')
        } else {
          showSnack(`Удалено ${res.deleted.length} закупок`, 'warning')
        }
      } else {
        await apiFetch(`/purchases/${deleteDialog.single!.id}`, { method: 'DELETE' })
        showSnack('Закупка удалена', 'warning')
      }
      deleteDialog.show = false
      await loadOrders()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка удаления', 'error')
    } finally {
      deleteDialog.deleting = false
    }
  }

  return {
    orders, duplicateGroupsMap, dupGroupFor, subsidies, contractors, loading, transitioning,
    contractorsForFilter, expanded, selectedOrders, guardDialog, deleteDialog,
    filteredOrders, filteredOrdersWithRowNum,
    cardsPage, cardsPageSize, cardsSource, cardsTotalPages, pagedCards,
    isOrderSelected, toggleOrderSelected, filteredSum,
    loadOrders, loadDuplicateGroups, loadSubsidies,
    doTransition, doForceStatus, confirmDeleteOne, confirmBulkDelete, bulkChangeStatus, doDelete,
  }
}
