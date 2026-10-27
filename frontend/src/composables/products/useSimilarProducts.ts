// useSimilarProducts.ts — поиск похожих карточек каталога (бренд+модель/
// артикул) и ручное слияние дублей из диалога SimilarProductsDialog.vue
// (владелец, 27.10.2026). ПРАВИЛО №6: переиспользует существующий
// api-клиент (apiFetch), единственный эндпоинт слияния POST /products/merge
// (тот же самый механизм, что у «Удалить дубликаты» —
// composables/products/useProductsDedup.ts) и единственный Pinia-кеш
// контрагентов (stores/contractors.ts) для имени магазина по contractor_id —
// вторая реализация ни одного из них здесь не заводится.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { useContractorsStore } from '@/stores/contractors'

export const SIMILAR_MIN_QUERY_LEN = 3

export interface SimilarCard {
  id: number
  name: string
  manufacturer: string | null
  price: number | null
  contractor_id: number | null
  source_ref: string | null
  history_count: number
  has_photo: boolean
  has_description: boolean
  diff_tokens: string[]
  same_store_as_winner: boolean
}

export interface SimilarGroupUi {
  brand: string
  base_model: string
  // Исходное написание модели/артикула winner'а для заголовка — «ОП-2»/
  // «DF332DWME», не свёрнутый ключ группировки base_model «оп2»/«df332dwme»
  // (backend/app/services/product_similar.py::SimilarGroup.model_display,
  // владелец 27.10.2026, п.1 приёмки). Бэкенд всегда отдаёт непустую строку
  // (откат на base_model там же) — optional только на случай старого кеша.
  model_display?: string
  confidence: 'уверенно' | 'проверить'
  match_key: 'article' | 'model'
  suggested_winner_id: number | null
  cards: SimilarCard[]
  // Состояние выбора в диалоге (не из API) — победитель группы и карточки,
  // отмеченные к объединению в него.
  winnerId: number | null
  mergeIds: Set<number>
  merging: boolean
  mergedReport: string | null
}

interface MergeReport {
  winner_id: number
  loser_ids: number[]
  transferred: Record<string, number>
  filled_fields: string[]
}

// Подписи для отчёта о слиянии — то же множество таблиц, что в докстринге
// backend/app/services/product_merge.py::merge_products (единственная
// формула переноса, фронт просто переводит её ключи на русский).
const TRANSFERRED_LABELS: Record<string, string> = {
  product_price_history: 'цен', purchase_items: 'строк заявок на закупку',
  contract_items: 'строк договоров', wish_items: 'строк заявок',
  commercial_request_offers: 'коммерческих предложений',
  supplier_products: 'привязок к поставщикам',
  product_purchase_categories: 'категорий закупки', product_photo: 'фото',
  product_description_history: 'записей истории описания',
  product_description_proposals: 'предложений правок',
}

function formatMergeReport(report: MergeReport): string {
  const parts = Object.entries(report.transferred)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${TRANSFERRED_LABELS[k] || k}`)
  const losers = report.loser_ids.map(id => `№${id}`).join(', ')
  return parts.length
    ? `Объединено: карточки ${losers} перенесены — ${parts.join(', ')}.`
    : `Объединено: карточки ${losers} перенесены.`
}

// Дефолт галочек «Объединить в неё» (владелец, 27.10.2026): для
// confidence='уверенно' включена у карточек другого магазина; для
// 'проверить' — выключена (нужна ручная проверка); карточка того же
// магазина, что winner, никогда не предлагается (same_store_as_winner).
// Экспортирована отдельно от search() — покрыта юнит-тестом.
export function defaultMergeIds(cards: SimilarCard[], winnerId: number | null, confidence: string): Set<number> {
  const ids = new Set<number>()
  if (confidence !== 'уверенно') return ids
  for (const c of cards) {
    if (c.id === winnerId || c.same_store_as_winner) continue
    ids.add(c.id)
  }
  return ids
}

// Выделение отличающихся слов названия (diff_tokens с бэкенда,
// product_similar.py::_build_cards) — лучшее-усилие: diff_tokens уже
// нормализованы (гомоглифы/регистр), сравниваем с тем же простым фолдом слова
// названия. Не угадывает 100% совпадений при опечатках — только подсветка,
// не влияет на логику слияния.
export function highlightDiffTokens(name: string, diffTokens: string[]): { text: string; bold: boolean }[] {
  if (!diffTokens || !diffTokens.length) return [{ text: name, bold: false }]
  const diffSet = new Set(diffTokens)
  const parts = name.split(/(\s+)/)
  return parts.map(p => {
    const clean = p.trim().toLowerCase().replace(/[.,;:!?"'«»()]/g, '')
    return { text: p, bold: !!clean && diffSet.has(clean) }
  })
}

function apiErrorText(e: any): string {
  // Память проекта: показывать текст из ответа сервера + код, не общее
  // «Ошибка» (e.message уже = payload.message, см. frontend/src/api.ts).
  const msg = e?.message || 'Ошибка запроса'
  return e?.status ? `${msg} (код ${e.status})` : msg
}

export function useSimilarProducts(options: {
  showSnack: (text: string, color?: ToastType) => void
  reloadProducts: () => Promise<void>
}) {
  const { showSnack, reloadProducts } = options
  const contractorsStore = useContractorsStore()

  const query = ref('')
  const loading = ref(false)
  const searched = ref(false)
  const groups = ref<SimilarGroupUi[]>([])
  const confirmTarget = ref<SimilarGroupUi | null>(null)

  async function resolveContractorNames(ids: Set<number>) {
    const missing = [...ids].filter(id => id != null && !contractorsStore.getById(id))
    if (!missing.length) return
    await Promise.all(missing.map(async (id) => {
      try {
        const c = await apiFetch<{ id: number; name: string }>(`/contractors/${id}`)
        contractorsStore.putToCache(c)
      } catch {
        // Имя магазина необязательно для работы диалога — просто покажем «контрагент №id».
      }
    }))
  }

  function contractorName(contractorId: number | null): string {
    if (contractorId == null) return 'без магазина'
    return contractorsStore.getById(contractorId)?.name || `контрагент №${contractorId}`
  }

  async function search() {
    const q = query.value.trim()
    if (q.length < SIMILAR_MIN_QUERY_LEN) {
      showSnack(`Введите не меньше ${SIMILAR_MIN_QUERY_LEN} символов`, 'warning')
      return
    }
    loading.value = true
    searched.value = true
    confirmTarget.value = null
    try {
      const data = await apiFetch<{ groups: Omit<SimilarGroupUi, 'winnerId' | 'mergeIds' | 'merging' | 'mergedReport'>[] }>(
        `/products/similar-groups?q=${encodeURIComponent(q)}&limit=50`,
      )
      const contractorIds = new Set<number>()
      for (const g of data.groups) for (const c of g.cards) if (c.contractor_id != null) contractorIds.add(c.contractor_id)
      await resolveContractorNames(contractorIds)

      groups.value = data.groups.map((g): SimilarGroupUi => ({
        ...g,
        winnerId: g.suggested_winner_id,
        mergeIds: defaultMergeIds(g.cards, g.suggested_winner_id, g.confidence),
        merging: false,
        mergedReport: null,
      }))
    } catch (e: any) {
      showSnack(apiErrorText(e), 'error')
      groups.value = []
    } finally {
      loading.value = false
    }
  }

  function setWinner(group: SimilarGroupUi, cardId: number) {
    group.winnerId = cardId
    group.mergeIds.delete(cardId)
  }

  function toggleMerge(group: SimilarGroupUi, cardId: number) {
    if (cardId === group.winnerId) return
    const card = group.cards.find(c => c.id === cardId)
    if (card?.same_store_as_winner) return
    if (group.mergeIds.has(cardId)) group.mergeIds.delete(cardId)
    else group.mergeIds.add(cardId)
  }

  function requestMerge(group: SimilarGroupUi) {
    if (!group.winnerId || group.mergeIds.size === 0) return
    confirmTarget.value = group
  }

  function cancelMergeConfirm() {
    confirmTarget.value = null
  }

  async function confirmMerge() {
    const group = confirmTarget.value
    if (!group || !group.winnerId) return
    const loserIds = [...group.mergeIds]
    group.merging = true
    try {
      const report = await apiFetch<MergeReport>('/products/merge', {
        method: 'POST',
        body: JSON.stringify({ winner_id: group.winnerId, loser_ids: loserIds }),
      })
      group.mergedReport = formatMergeReport(report)
      group.cards = group.cards.filter(c => !loserIds.includes(c.id))
      group.mergeIds = new Set()
      showSnack('Карточки объединены')
      await reloadProducts()
    } catch (e: any) {
      showSnack(apiErrorText(e), 'error')
    } finally {
      group.merging = false
      confirmTarget.value = null
    }
  }

  return {
    query, loading, searched, groups, confirmTarget,
    search, setWinner, toggleMerge, requestMerge, cancelMergeConfirm, confirmMerge,
    contractorName,
  }
}
