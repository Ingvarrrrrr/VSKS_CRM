// Автокомплит адреса доставки/оказания услуг (история по org_id + поиск).
// Вынесено из CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'

export function useDeliveryAddress(
  form: Record<string, any>,
  currentSubsidyOrgId: ComputedRef<number | null>,
  subsidies: Ref<{ id: number; org_id?: number | null }[]>,
) {
  const deliveryAddressSuggestions = ref<string[]>([])
  let _deliverySearchTimer: ReturnType<typeof setTimeout> | null = null

  async function loadDeliveryAddressHistory() {
    try {
      const orgId = currentSubsidyOrgId.value
      if (!orgId) return
      const results = await apiFetch<{ id: number; address: string }[]>(
        `/delivery-addresses/?org_id=${orgId}&q=`
      )
      const addresses = results.map(r => r.address)
      // Добавим адрес организации первым если его нет в истории
      const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
      if (subsidy?.org_id) {
        try {
          const orgs = await apiFetch<any[]>('/auth/my-orgs')
          const org = orgs.find((o: any) => o.id === subsidy.org_id)
          if (org?.address && !addresses.includes(org.address)) {
            addresses.unshift(org.address)
          }
        } catch { /* silent */ }
      }
      deliveryAddressSuggestions.value = [...new Set(addresses)]
    } catch { deliveryAddressSuggestions.value = [] }
  }
  async function onDeliveryAddressSearch(q: string) {
    if (!q || q.length < 2) {
      // При пустом поле показать историю
      if (!deliveryAddressSuggestions.value.length) loadDeliveryAddressHistory()
      return
    }
    if (_deliverySearchTimer) clearTimeout(_deliverySearchTimer)
    _deliverySearchTimer = setTimeout(async () => {
      try {
        const orgId = currentSubsidyOrgId.value
        if (!orgId) return
        const results = await apiFetch<{ id: number; address: string }[]>(
          `/delivery-addresses/?org_id=${orgId}&q=${encodeURIComponent(q)}`
        )
        deliveryAddressSuggestions.value = results.map(r => r.address)
      } catch { deliveryAddressSuggestions.value = [] }
    }, 300)
  }
  async function onDeliveryAddressSelect(val: string | null) {
    // val is already a string (full_name), just set it
    if (val) form.delivery_address = val
  }
  async function saveDeliveryAddressIfNew(address: string) {
    if (!address?.trim()) return
    try {
      const orgId = currentSubsidyOrgId.value
      if (!orgId) return
      await apiFetch('/delivery-addresses/', { method: 'POST', body: JSON.stringify({ org_id: orgId, address: address.trim() }) })
    } catch { /* silent */ }
  }

  return {
    deliveryAddressSuggestions,
    loadDeliveryAddressHistory, onDeliveryAddressSearch, onDeliveryAddressSelect, saveDeliveryAddressIfNew,
  }
}
