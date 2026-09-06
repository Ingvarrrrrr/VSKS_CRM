// Разбить закупку на несколько (kanban DnD по колонкам категорий). Вынесено из
// CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, computed, type ComputedRef, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

const ADMIN_ROLES_FE = ['superadmin', 'account_owner', 'org_admin', 'admin']
const LOCKED_SPLIT_STATUSES = ['contracted', 'delivered', 'paid']

export function usePurchaseSplit(
  router: Router,
  isEdit: ComputedRef<boolean>,
  form: Record<string, any>,
  items: Ref<any[]>,
  productPhotoSrc: (p: any) => string | undefined,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
) {
  const splitKanbanDialog = ref(false)
  const splitKanbanItems = ref<any[]>([])

  const canSplitPurchase = computed(() => {
    if (!isEdit.value) return false
    const st = (form.status || '').toString()
    if (st === 'split') return false
    if ((items.value?.length || 0) < 2) return false
    if (LOCKED_SPLIT_STATUSES.includes(st)) {
      const role = localStorage.getItem('user_role') || ''
      return ADMIN_ROLES_FE.includes(role)
    }
    return true
  })

  async function openSplitKanban(routeParamId: string | string[] | undefined) {
    // items.value в CreateOrderView НЕ содержит item.id (см. mapping @4025),
    // а канбану нужны настоящие pk для DnD и payload. Фетчим closedly.
    const pid = Number(routeParamId)
    let fresh: any = null
    try { fresh = await apiFetch<any>(`/purchases/${pid}`) } catch {}
    const rawItems: any[] = (fresh?.items || []).filter((it: any) => it && it.id != null)

    let productsList: any[] = []
    try { productsList = await apiFetch<any[]>('/products/?limit=10000') } catch {}
    const byId = new Map<number, any>(productsList.map((p: any) => [p.id, p]))
    const byName = new Map<string, any>(productsList.map((p: any) => [(p.name || '').trim().toLowerCase(), p]))

    splitKanbanItems.value = rawItems.map((it: any) => {
      let prod = it.product_id ? byId.get(it.product_id) : null
      if (!prod && it.item_name) prod = byName.get(it.item_name.trim().toLowerCase()) || null
      const category = (prod?.category || '').trim()
      return {
        id: it.id,
        product_id: it.product_id ?? prod?.id ?? null,
        item_name: it.item_name,
        quantity: Number(it.quantity) || 0,
        unit: it.unit || 'шт',
        total_price: Number(it.total_price) || 0,
        _photo_url: productPhotoSrc(prod) ?? null,
        _product_category: category,
        _column: category || '__uncategorized__',
      }
    })
    splitKanbanDialog.value = true
  }

  async function onPurchaseSplit(result: { purchase_ids: number[]; count: number; source_purchase_id: number }) {
    splitKanbanDialog.value = false
    showSnack(`Создано ${result.count} закупок. Исходная разбита.`, 'success')
    if (result.purchase_ids?.[0]) {
      router.push(`/orders/${result.purchase_ids[0]}/edit`)
    }
  }

  return { splitKanbanDialog, splitKanbanItems, canSplitPurchase, openSplitKanban, onPurchaseSplit }
}
