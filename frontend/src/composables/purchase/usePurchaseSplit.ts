// Разбить закупку на несколько (kanban DnD по колонкам категорий). Вынесено из
// CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, computed, type ComputedRef, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { ADMIN_ROLES } from '@/constants/roles'

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
      return ADMIN_ROLES.includes(role as typeof ADMIN_ROLES[number])
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

    // Перф (сессия 2026-09-20): раньше здесь грузился ВЕСЬ каталог товаров
    // (`/products/?limit=10000`, единственно ради фото/категории уже
    // ПРИВЯЗАННЫХ позиций) — byName-подбор без product_id не нужен: позиции
    // закупки либо уже привязаны, либо остаются без фото/категории (как и
    // раньше, когда byName не находил совпадение). Грузим точечно по
    // product_id, без полного каталога (тот же приём, что и в
    // useWishActions.ts::openKanbanDialog, ПРАВИЛО №6).
    const ids = [...new Set(rawItems.map((it: any) => it.product_id).filter((id: any) => id != null))]
    let byId = new Map<number, any>()
    if (ids.length) {
      try {
        const productsList = await apiFetch<any[]>(`/products/?ids=${ids.join(',')}`)
        byId = new Map<number, any>((productsList || []).map((p: any) => [p.id, p]))
      } catch {}
    }

    splitKanbanItems.value = rawItems.map((it: any) => {
      const prod = it.product_id != null ? byId.get(it.product_id) : null
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
        // Владелец (2026-09-16): раскладка канбана переживает закрытие окна —
        // читаем сохранённый черновик (app/models/purchase_item.py::split_column_key),
        // PurchaseSplitKanban.vue восстанавливает по нему колонки при открытии.
        split_column_key: it.split_column_key ?? null,
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
