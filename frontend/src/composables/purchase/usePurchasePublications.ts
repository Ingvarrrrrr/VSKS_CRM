// Публикация закупки на торговых площадках (Фабрикант / Росэлторг.Бизнес):
// список публикаций, диалог настроек публикации (в т.ч. поля Фабрикант — ОКПД2,
// даты, редукцион), опрос статуса после отправки, повтор при ошибке с указанием
// на нужное поле через guideArrow. Вынесено из CreateOrderView.vue без изменения
// поведения — те же apiFetch-пути (/publications/...).
import { computed, nextTick, ref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { numOrNull } from '@/utils/numberFormat'
import type { ToastType } from '@/composables/useToast'

export interface Publication {
  id: number; purchase_id: number; platform: string; status: string
  external_id?: string; external_url?: string; error_text?: string
  published_at?: string; created_at?: string
  platform_number?: string; platform_state?: string
}

export const AVAILABLE_PLATFORMS = [
  { value: 'fabrikant',    title: 'Фабрикант',          subtitle: 'fabrikant.ru — коммерческие и 223-ФЗ', color: 'orange-darken-2', icon: 'mdi-factory' },
  { value: 'roseltorg_rb', title: 'Росэлторг.Бизнес',   subtitle: 'rb.roseltorg.ru — коммерческие закупки', color: 'blue-darken-2',   icon: 'mdi-domain' },
]

export const PLATFORM_LABELS: Record<string, string> = {
  fabrikant:    'Фабрикант',
  roseltorg_rb: 'Росэлторг.Бизнес',
}

export const PUB_STATUS_COLOR: Record<string, string> = {
  pending:    'grey',
  publishing: 'blue',
  published:  'success',
  draft:      'orange',
  error:      'error',
}

export const PUB_STATUS_LABEL: Record<string, string> = {
  pending:    'Ожидает',
  publishing: 'Публикуется...',
  published:  'Опубликовано',
  draft:      'Черновик на ЭТП',
  error:      'Ошибка',
}

export const ROSELTORG_PROCEDURE_TYPES = [
  { value: 'request_quotations', title: 'Запрос котировок' },
  { value: 'request_proposals',  title: 'Запрос предложений' },
  { value: 'competition',        title: 'Конкурс' },
  { value: 'auction',            title: 'Аукцион' },
]

export const FABRIKANT_PROCEDURE_TYPES = [
  { value: 'zp',               title: 'Запрос предложений' },
  { value: 'reduction',        title: 'Редукцион (аукцион на понижение)' },
  { value: 'price_monitoring', title: 'Мониторинг цен' },
]

export type PublishTarget = 'subject' | 'items' | 'nmck' | 'auction-date' | 'auction-bet' | 'region' | 'address'

export function usePurchasePublications(
  purchaseId: ComputedRef<number | null>,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
  form: Record<string, any>,
  items: Ref<{ item_name?: string }[]>,
  subsidies: Ref<{ id: number; org_inn?: string | null }[]>,
  isEdit: ComputedRef<boolean>,
  performAutosave: () => Promise<void>,
  autosaveState: Ref<string>,
  resolveRegionOkato: (region: string) => any,
  customerPreview: Ref<{ address?: string } | null>,
  displayNmck: ComputedRef<number>,
  savedNmck: Ref<number | null>,
  guideArrowTo: (target: string) => void,
) {
  const publications = ref<Publication[]>([])
  const publishDialog = ref(false)
  const publishingPlatform = ref<string | null>(null)
  const pendingPlatform = ref<string | null>(null)
  const roseltorgProcedureType = ref<string | null>(null)
  const publishErrors = ref<{text: string; target: PublishTarget}[]>([])

  const fabrikantDates = ref({ proposal_start: '', proposal_end: '', determination_date: '', summing_up_date: '' })
  const fabrikantOkpd2 = ref('')
  // ОКПД2 autocomplete state
  const okpd2Items = ref<{code: string; name: string; section: string | null}[]>([])
  const okpd2Loading = ref(false)
  const okpd2Error = ref('')
  let _okpd2SearchTimer: ReturnType<typeof setTimeout> | null = null

  function okpd2ItemTitle(item: {code: string; name: string}): string {
    return `${item.code} — ${item.name}`
  }

  async function searchOkpd2(q: string | undefined) {
    if (_okpd2SearchTimer) clearTimeout(_okpd2SearchTimer)
    if (!q || q.length < 2) {
      okpd2Items.value = []
      okpd2Error.value = ''
      return
    }
    _okpd2SearchTimer = setTimeout(async () => {
      okpd2Loading.value = true
      try {
        const token = localStorage.getItem('auth_token')
        const res = await fetch(`/api/okpd2?q=${encodeURIComponent(q)}&limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          okpd2Error.value = ''
          const data = await res.json()
          // Ensure current value stays in the list if it was previously selected
          if (fabrikantOkpd2.value && !data.find((d: {code: string}) => d.code === fabrikantOkpd2.value)) {
            // keep existing items that include the current selection
            const existing = okpd2Items.value.filter(i => i.code === fabrikantOkpd2.value)
            okpd2Items.value = [...existing, ...data]
          } else {
            okpd2Items.value = data
          }
        } else {
          okpd2Error.value = `Ошибка загрузки справочника (${res.status})`
        }
      } catch (_e) {
        okpd2Error.value = 'Не удалось загрузить справочник ОКПД2'
      } finally {
        okpd2Loading.value = false
      }
    }, 300)
  }

  const fabrikantAttachDocs = ref(true)
  const fabrikantNoNmcd = ref(false)
  const fabrikantProcedureType = ref<'zp' | 'reduction' | 'price_monitoring'>('zp')
  const fabrikantAuctionDateStart = ref('')
  const fabrikantAuctionBetFrom = ref<number | null>(null)
  const fabrikantAuctionBetTo = ref<number | null>(null)

  const publishNmck = computed(() => displayNmck.value || savedNmck.value || 0)

  function initFabrikantDates() {
    const pad = (n: number) => String(n).padStart(2, '0')
    const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    const now = new Date()
    const end = new Date(now.getTime() + 7*24*60*60*1000)
    fabrikantDates.value = {
      proposal_start: fmt(new Date(now.getTime() + 60*60*1000)),
      proposal_end: fmt(end),
      determination_date: fmt(new Date(end.getTime() + 24*60*60*1000)),
      summing_up_date: fmt(new Date(end.getTime() + 2*24*60*60*1000)),
    }
    // Preload current ОКПД2 selection so v-autocomplete can display the label
    if (fabrikantOkpd2.value && !okpd2Items.value.find(i => i.code === fabrikantOkpd2.value)) {
      void searchOkpd2(fabrikantOkpd2.value)
    }
  }

  function checkPublishReady(): {text: string; target: PublishTarget}[] {
    const errors: {text: string; target: PublishTarget}[] = []
    if (!form.subject?.trim()) errors.push({ text: 'Не заполнено наименование закупки', target: 'subject' })
    // Мониторинг цен не требует позиций (и deliveryPlace там опционален)
    if (fabrikantProcedureType.value !== 'price_monitoring') {
      if (!items.value.some(i => i.item_name?.trim())) errors.push({ text: 'Нет позиций в закупке (добавьте хотя бы одну)', target: 'items' })
      // Фабрикант требует lot_delivery_place.state/region/okato — нужен реальный субъект РФ (поле доставки, не мероприятия)
      if (!form.delivery_region || !resolveRegionOkato(form.delivery_region)) {
        errors.push({ text: 'Укажите субъект РФ (для места поставки)', target: 'region' })
      }
      // Адрес поставки: структурный → свободная строка → место оказания услуг → адрес организации субсидии
      const hasAddress = !!String(form.delivery_city || form.delivery_street || form.delivery_address || '').trim()
        || !!String(form.delivery_location || '').trim()
        || !!String(customerPreview.value?.address || '').trim()
      if (!hasAddress) errors.push({ text: 'Укажите адрес доставки', target: 'address' })
    }
    // Поля редукциона
    if (fabrikantProcedureType.value === 'reduction') {
      if (!fabrikantAuctionDateStart.value) errors.push({ text: 'Укажите дату и время начала редукциона', target: 'auction-date' })
      // numOrNull ловит и null, и '' (Vue кладёт '' при очистке v-model.number-поля,
      // голое === null это пропускало — редукцион на Фабрикант ушёл бы с auction_bet_limit_from: '').
      if (numOrNull(fabrikantAuctionBetFrom.value) === null || numOrNull(fabrikantAuctionBetTo.value) === null) errors.push({ text: 'Укажите границы ставки редукциона (от / до)', target: 'auction-bet' })
    }
    return errors
  }

  const currentSubsidyOrgInn = computed(() =>
    subsidies.value.find(s => s.id === form.subsidy_id)?.org_inn ?? null
  )

  const isPlatformPublished = (platform: string) =>
    publications.value.some(p => p.platform === platform && (p.status === 'published' || p.status === 'draft'))

  const refreshingPubId = ref<number | null>(null)

  async function loadPublications() {
    if (!purchaseId.value) return
    try {
      publications.value = await apiFetch<Publication[]>(`/publications/purchases/${purchaseId.value}`)
    } catch {}
  }

  async function refreshPubStatus(pub: Publication) {
    refreshingPubId.value = pub.id
    try {
      const updated = await apiFetch<Publication>(`/publications/${pub.id}/refresh`, { method: 'POST' })
      const idx = publications.value.findIndex(p => p.id === pub.id)
      if (idx !== -1) publications.value[idx] = updated
      if (updated.status === 'published') {
        showSnack(`Процедура размещена на ${PLATFORM_LABELS[updated.platform] || updated.platform}`, 'success')
      } else if (updated.status === 'draft') {
        showSnack(`Статус обновлён: черновик${updated.platform_number ? ' №' + updated.platform_number : ''} на Фабриканте`)
      }
    } catch (e: any) {
      const msg = e?.payload?.message || e?.detail || e?.message || 'Не удалось обновить статус'
      showSnack(msg, 'error')
    } finally {
      refreshingPubId.value = null
    }
  }

  async function doPublish(platform: string, procedureType?: string | null) {
    publishingPlatform.value = platform
    // Сначала сбрасываем несохранённые изменения в БД, иначе бэкенд читает устаревший delivery_region
    if (isEdit.value && purchaseId.value) {
      await performAutosave()
      if (autosaveState.value === 'error') {
        showSnack('Не удалось сохранить изменения карточки — публикация отменена', 'error')
        publishingPlatform.value = null
        return
      }
    }
    try {
      const body: Record<string, any> = { platform }
      if (procedureType) body.procedure_type = procedureType
      if (platform === 'fabrikant') {
        body.procedure_type = fabrikantProcedureType.value
        body.okpd2_code = fabrikantOkpd2.value
        body.proposal_start = fabrikantDates.value.proposal_start
        body.proposal_end = fabrikantDates.value.proposal_end
        body.summing_up_date = fabrikantDates.value.summing_up_date
        body.attach_documents = fabrikantAttachDocs.value
        if (fabrikantProcedureType.value === 'zp') {
          body.determination_date = fabrikantDates.value.determination_date
          body.no_nmcd = fabrikantNoNmcd.value
        } else if (fabrikantProcedureType.value === 'reduction') {
          body.no_nmcd = fabrikantNoNmcd.value
          body.auction_date_start = fabrikantAuctionDateStart.value
          body.auction_bet_limit_from = numOrNull(fabrikantAuctionBetFrom.value)
          body.auction_bet_limit_to = numOrNull(fabrikantAuctionBetTo.value)
        }
        // price_monitoring: no no_nmcd, no determination_date, no auction fields
      }
      const pub = await apiFetch<Publication>(`/publications/purchases/${purchaseId.value}`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      publications.value.unshift(pub)
      showSnack(`Отправлено на публикацию: ${PLATFORM_LABELS[platform]}`)
      publishDialog.value = false
      pendingPlatform.value = null
      roseltorgProcedureType.value = null
      // Poll status for 30s
      pollPublication(pub.id)
    } catch (e: any) {
      const errText = e?.detail || e?.payload?.message || e?.message || 'Ошибка при отправке на публикацию'
      if (platform === 'fabrikant') {
        const errTarget = fabrikantErrorTarget(errText)
        if (errTarget === 'okpd2') {
          showSnack(errText, 'error', {
            actionText: 'Показать поле',
            onAction: () => guideArrowTo(errTarget),
          })
          guideArrowTo(errTarget)
        } else if (errTarget === 'region' || errTarget === 'address') {
          showSnack(errText, 'error', {
            actionText: 'Показать поле',
            onAction: () => guideArrowTo(errTarget),
          })
          guideArrowTo(errTarget)
        } else {
          showSnack(errText, 'error')
        }
      } else {
        showSnack(errText, 'error')
      }
    } finally {
      publishingPlatform.value = null
    }
  }

  async function retryPublish(platform: string) {
    if (platform === 'fabrikant') {
      openFabrikantRetry(platform)
    } else {
      await doPublish(platform)
    }
  }

  // Маппинг бизнес-ошибок Фабриканта → поле карточки (одна точка правды:
  // используется и в openFabrikantRetry, и в снэкбаре поллинга)
  function fabrikantErrorTarget(errorText?: string | null): 'okpd2' | 'region' | 'address' | null {
    const t = (errorText || '').toLowerCase()
    if (!t) return null
    if (t.includes('окпд') || t.includes('okpd')) return 'okpd2'
    const isDeliveryPlace = /delivery_place|deliveryplace|место поставки/.test(t)
    // lot_delivery_place.okato / .state / .region → поле «Субъект РФ»
    if (/okato|окато|\bregion\b|\bstate\b|субъект/.test(t)) return 'region'
    // адрес внутри места поставки → поле адреса
    if (isDeliveryPlace && /adress|address|адрес/.test(t)) return 'address'
    if (isDeliveryPlace) return 'region'
    return null
  }

  function openFabrikantRetry(platform: string) {
    const lastPub = publications.value.find(p => p.platform === platform && p.status === 'error')
    publishErrors.value = checkPublishReady()
    publishDialog.value = true
    pendingPlatform.value = 'fabrikant'
    initFabrikantDates()
    // Сохраняем выбранный тип процедуры при повторе (fabrikantProcedureType не сбрасываем)
    if (fabrikantProcedureType.value !== 'price_monitoring') {
      fabrikantNoNmcd.value = !(publishNmck.value > 0)
    }
    const errTarget = fabrikantErrorTarget(lastPub?.error_text)
    if (errTarget === 'okpd2') {
      nextTick(() => guideArrowTo('okpd2'))
    } else if (errTarget === 'region' || errTarget === 'address') {
      // Показать блокер в списке ошибок диалога; клик → закрыть диалог → стрелка к полю
      if (!publishErrors.value.some(e => e.target === errTarget)) {
        publishErrors.value.push({
          text: errTarget === 'region' ? 'Укажите субъект РФ (для места поставки)' : 'Укажите адрес доставки',
          target: errTarget,
        })
      }
    }
  }

  function pollPublication(pubId: number, attempts = 0) {
    if (attempts > 60) return
    // Первые 15 попыток — каждые 2с (быстрый отклик), дальше — каждые 5с (не долбим сервер)
    const delay = attempts < 15 ? 2000 : 5000
    setTimeout(async () => {
      await loadPublications()
      const pub = publications.value.find(p => p.id === pubId)
      if (pub && pub.status === 'error') {
        const errTarget = pub.platform === 'fabrikant' ? fabrikantErrorTarget(pub.error_text) : null
        if (errTarget === 'region' || errTarget === 'address') {
          // АВТОМАТИЧЕСКИ запускаем стрелку без ожидания клика
          guideArrowTo(errTarget)
          showSnack(pub.error_text || 'Ошибка публикации', 'error', {
            actionText: 'Показать поле',
            onAction: () => guideArrowTo(errTarget),
          })
        } else if (errTarget === 'okpd2') {
          // Поле ОКПД2 находится в диалоге публикации — открываем диалог со стрелкой
          openFabrikantRetry('fabrikant')
          showSnack(pub.error_text || 'Ошибка публикации', 'error', {
            actionText: 'Показать поле',
            onAction: () => openFabrikantRetry('fabrikant'),
          })
        } else {
          showSnack(pub.error_text || 'Ошибка публикации', 'error')
        }
      } else if (pub && pub.status === 'published') {
        showSnack(`Закупка опубликована на ${PLATFORM_LABELS[pub.platform] || pub.platform}`, 'success')
      } else if (pub && pub.status === 'draft') {
        showSnack(
          `Черновик процедуры${pub.platform_number ? ' №' + pub.platform_number : ''} создан на Фабриканте. Разместите его в личном кабинете площадки.`,
          'warning',
        )
      } else if (pub && (pub.status === 'publishing' || pub.status === 'pending')) {
        pollPublication(pubId, attempts + 1)
      }
    }, delay)
  }

  return {
    publications, publishDialog, publishingPlatform, pendingPlatform, roseltorgProcedureType, publishErrors,
    fabrikantDates, fabrikantOkpd2, okpd2Items, okpd2Loading, okpd2Error, okpd2ItemTitle, searchOkpd2,
    fabrikantAttachDocs, fabrikantNoNmcd, fabrikantProcedureType,
    fabrikantAuctionDateStart, fabrikantAuctionBetFrom, fabrikantAuctionBetTo,
    publishNmck, initFabrikantDates, checkPublishReady, currentSubsidyOrgInn, isPlatformPublished,
    refreshingPubId, loadPublications, refreshPubStatus, doPublish, retryPublish,
    fabrikantErrorTarget, openFabrikantRetry, pollPublication,
  }
}
