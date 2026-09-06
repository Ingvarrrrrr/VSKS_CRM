// Запрос коммерческих предложений (КП) — подбор контрагентов/писем, отправка,
// сохранение запроса в реестр, xlsx сравнения. Вынесено из CreateOrderView.vue
// без изменения поведения — те же apiFetch-пути.
import { ref, computed, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export interface KpFormSlice {
  subject: string
  item_name?: string
  execution_term?: string
  contractor_id: number | null
}

interface ContractorKp {
  id: number; name: string; email?: string
  product_categories: string[]
}
interface KpItem {
  id: number; item_name: string; quantity: number; unit: string
  unit_price: number; category: string | null
}

export function usePurchaseKp(
  purchaseId: ComputedRef<number | null>,
  form: KpFormSlice,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { duration?: number }) {
    toast.addToast(text, color, opts)
  }

  const kpDialog      = ref(false)
  const kpSelected    = ref<number[]>([])
  const kpIntroText   = ref('')
  const kpDeliveryDate = ref('')
  const kpItemsLoading = ref(false)
  const kpFreeRecipients = ref<{ name: string; email: string }[]>([])
  const kpEditEmailId  = ref<number | null>(null)
  const kpEditEmailValue = ref('')
  const kpSavingEmail  = ref(false)
  const kpSaving       = ref(false)
  const kpSendingAll   = ref(false)

  const kpContractorList = ref<ContractorKp[]>([])
  const kpItems = ref<KpItem[]>([])

  const kpAllEmails = computed(() => {
    const emails: string[] = []
    for (const cid of kpSelected.value) {
      const c = kpContractorList.value.find(c => c.id === cid)
      if (c?.email) emails.push(c.email)
    }
    for (const fr of kpFreeRecipients.value) {
      if (fr.email.trim()) emails.push(fr.email.trim())
    }
    return emails
  })

  const kpContractorOptions = computed(() =>
    kpContractorList.value.map(c => ({
      id: c.id,
      label: c.email ? `${c.name} <${c.email}>` : `${c.name} (нет email)`,
    }))
  )

  /** Items matching a contractor's categories. If contractor has no categories → all items. */
  function kpItemsForContractor(cid: number): KpItem[] {
    const contractor = kpContractorList.value.find(c => c.id === cid)
    if (!contractor) return kpItems.value
    const cats = contractor.product_categories
    if (!cats.length) return kpItems.value  // no categories known → send all
    return kpItems.value.filter(item => item.category && cats.includes(item.category))
  }

  function buildContractorEmail(cid: number): string {
    const contractor = kpContractorList.value.find(c => c.id === cid)
    if (!contractor) return ''
    const items = kpItemsForContractor(cid)
    const subject = form.subject || form.item_name || '—'
    const delivery = kpDeliveryDate.value || form.execution_term || '—'
    const intro = kpIntroText.value || 'Просим Вас направить коммерческое предложение на поставку товаров.'

    const itemLines = items.map((it, i) =>
      `${i + 1}. ${it.item_name}${it.category ? ` [${it.category}]` : ''} — ${it.quantity} ${it.unit}`
    ).join('\n')

    return `Уважаемые коллеги,

${intro}

Закупка: ${subject}
Срок поставки: ${delivery}

Перечень товаров (${items.length} поз.):
${itemLines || '— (товары не указаны)'}

Просим указать в КП:
— наименование и характеристики товара;
— стоимость за единицу и общую стоимость;
— срок поставки;
— гарантийные обязательства.

С уважением`
  }

  function kpStartEditEmail(cid: number) {
    kpEditEmailId.value = cid
    kpEditEmailValue.value = kpContractorList.value.find(c => c.id === cid)?.email || ''
  }

  async function kpSaveEmail(cid: number) {
    if (!kpEditEmailValue.value.trim()) return
    kpSavingEmail.value = true
    try {
      await apiFetch(`/contractors/${cid}/email`, {
        method: 'PATCH',
        body: JSON.stringify({ email: kpEditEmailValue.value.trim() }),
      })
      const c = kpContractorList.value.find(c => c.id === cid)
      if (c) c.email = kpEditEmailValue.value.trim()
      kpEditEmailId.value = null
      showSnack('Email контрагента сохранён')
    } catch (e: any) {
      showSnack('Ошибка сохранения email', 'error')
    } finally {
      kpSavingEmail.value = false
    }
  }

  function buildGenericEmail(): string {
    const subject = form.subject || form.item_name || '—'
    const delivery = kpDeliveryDate.value || form.execution_term || '—'
    const intro = kpIntroText.value || 'Просим Вас направить коммерческое предложение на поставку товаров.'
    const itemLines = kpItems.value.map((it, i) =>
      `${i + 1}. ${it.item_name} — ${it.quantity} ${it.unit}`
    ).join('\n')
    return `Уважаемые коллеги,\n\n${intro}\n\nЗакупка: ${subject}\nСрок поставки: ${delivery}\n\nПеречень товаров (${kpItems.value.length} поз.):\n${itemLines || '— (товары не указаны)'}\n\nС уважением`
  }

  function openMailtoFree(fr: { name: string; email: string }) {
    if (!fr.email) return
    const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
    const body = encodeURIComponent(buildGenericEmail())
    window.open(`mailto:${fr.email}?subject=${subject}&body=${body}`, '_blank')
  }

  // fr не используется в теле (текст письма общий, buildGenericEmail() не зависит от
  // конкретного получателя) — так же было и в оригинале, помечаем `_fr`, чтобы не менять
  // сигнатуру вызова (кнопка в шаблоне передаёт получателя).
  function copyFreeEmail(_fr: { name: string; email: string }) {
    navigator.clipboard.writeText(buildGenericEmail()).then(
      () => showSnack('Текст письма скопирован', 'success', { duration: 2500 }),
      () => showSnack('Не удалось скопировать', 'error')
    )
  }

  async function openKpDialog() {
    kpDialog.value = true
    kpIntroText.value = ''
    kpDeliveryDate.value = form.execution_term || ''
    kpFreeRecipients.value = []
    kpEditEmailId.value = null

    // Load contractors with product categories
    if (!kpContractorList.value.length) {
      try {
        const list = await apiFetch<any[]>('/contractors/with-stats')
        kpContractorList.value = list.map((c: any) => ({
          id: c.id, name: c.name, email: c.email || '',
          product_categories: c.product_categories || [],
        }))
        if (form.contractor_id) kpSelected.value = [form.contractor_id]
      } catch { showSnack('Ошибка загрузки контрагентов', 'error') }
    }

    // Load purchase items with categories
    if (purchaseId.value && !kpItems.value.length) {
      kpItemsLoading.value = true
      try {
        kpItems.value = await apiFetch<KpItem[]>(`/purchases/${purchaseId.value}/kp-items`)
      } catch { showSnack('Ошибка загрузки позиций', 'error') }
      finally { kpItemsLoading.value = false }
    }
  }

  function openMailtoForContractor(cid: number) {
    const contractor = kpContractorList.value.find(c => c.id === cid)
    if (!contractor?.email) return
    const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
    const body = encodeURIComponent(buildContractorEmail(cid))
    window.open(`mailto:${contractor.email}?subject=${subject}&body=${body}`, '_blank')
  }

  function copyContractorEmail(cid: number) {
    navigator.clipboard.writeText(buildContractorEmail(cid)).then(
      () => showSnack('Текст письма скопирован', 'success', { duration: 2500 }),
      () => showSnack('Не удалось скопировать', 'error')
    )
  }

  function sendAllKp() {
    // Opens mailto: as fallback
    const emails = kpAllEmails.value
    if (!emails.length) return
    const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
    const body = encodeURIComponent(buildGenericEmail())
    const [first, ...rest] = emails
    const bcc = rest.length ? `&bcc=${encodeURIComponent(rest.join(','))}` : ''
    window.open(`mailto:${first}?subject=${subject}${bcc}&body=${body}`, '_blank')
  }

  async function sendAllKpViaApi() {
    kpSendingAll.value = true
    try {
      // Auto-save КП request before sending if purchase exists
      if (purchaseId.value) {
        const validFree = kpFreeRecipients.value.filter(r => r.email.trim())
        try {
          await apiFetch('/commercial-requests/', {
            method: 'POST',
            body: JSON.stringify({
              purchase_id: purchaseId.value,
              subject: `Запрос КП: ${form.subject || form.item_name || ''}`.trim(),
              intro_text: kpIntroText.value || null,
              delivery_date: kpDeliveryDate.value || null,
              recipient_ids: kpSelected.value,
              free_recipients: validFree.length ? validFree.map(r => ({ name: r.name || null, email: r.email })) : null,
            }),
          })
        } catch { /* silent — save failure shouldn't block send */ }
      }

      // Build recipients list
      const recipients: { name: string | null; email: string }[] = []
      for (const cid of kpSelected.value) {
        const c = kpContractorList.value.find(c => c.id === cid)
        if (c?.email) recipients.push({ name: c.name, email: c.email })
      }
      for (const fr of kpFreeRecipients.value) {
        if (fr.email.trim()) recipients.push({ name: fr.name || null, email: fr.email.trim() })
      }
      if (!recipients.length) {
        showSnack('Нет получателей с email', 'warning')
        return
      }

      const result = await apiFetch<{ sent: number; failed: { email: string; error: string }[] }>(
        '/commercial-requests/send',
        {
          method: 'POST',
          body: JSON.stringify({
            recipients,
            subject: `Запрос КП: ${form.subject || form.item_name || 'закупка'}`,
            body: buildGenericEmail(),
          }),
        }
      )

      if (result.failed.length) {
        showSnack(`Отправлено: ${result.sent}, ошибки: ${result.failed.length}`, 'warning')
      } else {
        showSnack(`Отправлено ${result.sent} письмо(а)`)
        kpDialog.value = false
      }
    } catch (e: any) {
      const msg = e.message || 'Ошибка отправки'
      if (msg.includes('SMTP не настроен')) {
        showSnack('SMTP не настроен. Перейдите в Настройки организации → Email.', 'error')
      } else {
        showSnack(msg, 'error')
      }
    } finally {
      kpSendingAll.value = false
    }
  }

  async function saveKpRequest() {
    if (!purchaseId.value) return
    kpSaving.value = true
    try {
      const validFree = kpFreeRecipients.value.filter(r => r.email.trim())
      await apiFetch('/commercial-requests/', {
        method: 'POST',
        body: JSON.stringify({
          purchase_id: purchaseId.value,
          subject: `Запрос КП: ${form.subject || form.item_name || ''}`.trim(),
          intro_text: kpIntroText.value || null,
          delivery_date: kpDeliveryDate.value || null,
          recipient_ids: kpSelected.value,
          free_recipients: validFree.length ? validFree.map(r => ({ name: r.name || null, email: r.email })) : null,
        }),
      })
      showSnack('Запрос КП сохранён в реестре')
      kpDialog.value = false
    } catch (e: any) {
      showSnack(e.message || 'Ошибка сохранения', 'error')
    } finally {
      kpSaving.value = false
    }
  }

  async function downloadKpXlsx() {
    if (!purchaseId.value) return
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
      const resp = await fetch(`/api/documents/purchases/${purchaseId.value}/kp-xlsx`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!resp.ok) throw new Error('error')
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Сравнение_КП_закупка_${purchaseId.value}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      showSnack('Ошибка загрузки xlsx', 'error')
    }
  }

  return {
    kpDialog, kpSelected, kpIntroText, kpDeliveryDate, kpItemsLoading, kpFreeRecipients,
    kpEditEmailId, kpEditEmailValue, kpSavingEmail, kpSaving, kpSendingAll,
    kpContractorList, kpItems, kpAllEmails, kpContractorOptions,
    kpItemsForContractor, buildContractorEmail, kpStartEditEmail, kpSaveEmail,
    openMailtoFree, copyFreeEmail, openKpDialog, openMailtoForContractor,
    copyContractorEmail, sendAllKp, sendAllKpViaApi, saveKpRequest, downloadKpXlsx,
  }
}
