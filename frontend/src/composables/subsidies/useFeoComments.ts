// Комментарии (мини-чат) к плановым позициям ФЭО и категориям дерева ФЭО —
// Волна 4, п.16 владельца (2026-09-13). Единственный источник обращений к
// /api/feo-comments (Правило №6) — FeoCommentThread.vue (сам список/ввод) и
// FeoTreeRow.vue (общий переключатель видимости на всю субсидию) оба зовут
// ЭТИ ЖЕ функции, второго клиента к тому же API не заводим.
//
// Module-level singleton для visibilityCache/visibilityPromises (тот же приём,
// что и useFeoTreePrefs.ts/useKpiDrilldown.ts в этом проекте) — переключатель,
// нажатый в ОДНОМ месте (строка категории), обязан немедленно отразиться во
// ВСЕХ уже смонтированных ветках комментариев той же субсидии, без перезагрузки
// страницы и без повторного похода в сеть из каждого экземпляра.
import { reactive } from 'vue'
import { apiFetch } from '@/api'

export interface FeoComment {
  id: number
  feo_planned_item_id: number | null
  feo_category_id: number | null
  parent_id: number | null
  user_id: number | null
  author_name: string | null
  text: string
  created_at: string
}

let _api: ReturnType<typeof buildFeoComments> | null = null

export function useFeoComments() {
  if (!_api) _api = buildFeoComments()
  return _api
}

function buildFeoComments() {
  const visibilityCache = reactive<Record<number, boolean>>({})
  const visibilityPromises: Record<number, Promise<boolean>> = {}

  // Счётчики комментариев ПО СУБСИДИИ — один запрос вместо N (жалоба
  // владельца 2026-09-15: «раскрыть всё» открывало пустую карточку
  // «Комментариев пока нет» под каждым направлением/позицией; до этой правки
  // каждая раскрытая ветка ЕЩЁ И грузила себя отдельным GET). Источник и для
  // решения «раскрывать ли ветку при массовом раскрытии» (пустые не
  // раскрываются, см. FeoTreeRow.vue/FeoLevel5Panel.vue), и для бейджа-
  // счётчика у иконки — единственный, второй способ посчитать «есть ли
  // комментарии» не заводим (ПРАВИЛО №6). Кэш — по той же схеме, что и
  // visibilityCache выше (module-level singleton, дедуп параллельных
  // запросов при одновременном монтировании многих строк дерева).
  interface CommentCounts { category: Record<number, number>; plannedItem: Record<number, number> }
  const countsCache = reactive<Record<number, CommentCounts>>({})
  const countsPromises: Record<number, Promise<CommentCounts>> = {}

  async function loadCounts(subsidyId: number, force = false): Promise<CommentCounts> {
    if (!force && subsidyId in countsCache) return countsCache[subsidyId]!
    if (force) delete countsPromises[subsidyId]
    if (!(subsidyId in countsPromises)) {
      countsPromises[subsidyId] = (async () => {
        try {
          const res = await apiFetch<{ category_counts: Record<string, number>; planned_item_counts: Record<string, number> }>(
            `/feo-comments/counts?subsidy_id=${subsidyId}`,
          )
          countsCache[subsidyId] = {
            category: Object.fromEntries(Object.entries(res.category_counts || {}).map(([k, v]) => [Number(k), v])),
            plannedItem: Object.fromEntries(Object.entries(res.planned_item_counts || {}).map(([k, v]) => [Number(k), v])),
          }
        } catch {
          countsCache[subsidyId] = countsCache[subsidyId] || { category: {}, plannedItem: {} }
        } finally {
          delete countsPromises[subsidyId]
        }
        return countsCache[subsidyId]!
      })()
    }
    return countsPromises[subsidyId]!
  }

  /** Счётчик у категории/плановой позиции — 0 до первой загрузки или если
   * ключа нет в ответе (сущность без комментариев, см. докстринг
   * FeoCommentCountsOut на бэкенде). Синхронные, для шаблонов — как и
   * isVisibleCached ниже. */
  function categoryCommentCount(subsidyId: number | null | undefined, categoryId: number): number {
    if (subsidyId == null) return 0
    return countsCache[subsidyId]?.category[categoryId] ?? 0
  }
  function plannedItemCommentCount(subsidyId: number | null | undefined, itemId: number): number {
    if (subsidyId == null) return 0
    return countsCache[subsidyId]?.plannedItem[itemId] ?? 0
  }

  async function fetchThread(target: { feoPlannedItemId?: number | null; feoCategoryId?: number | null }): Promise<FeoComment[]> {
    const qs = target.feoPlannedItemId != null
      ? `feo_planned_item_id=${target.feoPlannedItemId}`
      : `feo_category_id=${target.feoCategoryId}`
    return await apiFetch<FeoComment[]>(`/feo-comments/?${qs}`)
  }

  async function addComment(target: { feoPlannedItemId?: number | null; feoCategoryId?: number | null; text: string; subsidyId?: number | null }): Promise<FeoComment> {
    const result = await apiFetch<FeoComment>('/feo-comments/', {
      method: 'POST',
      body: JSON.stringify({
        feo_planned_item_id: target.feoPlannedItemId ?? null,
        feo_category_id: target.feoCategoryId ?? null,
        text: target.text,
      }),
    })
    // Счётчик обязан обновиться сразу — иначе автор увидит «0»/пустую иконку
    // там, где только что написал (см. задачу владельца). Не блокируем ответ
    // пользователю ожиданием этого запроса.
    if (target.subsidyId != null) void loadCounts(target.subsidyId, true)
    return result
  }

  async function replyToComment(commentId: number, text: string, subsidyId?: number | null): Promise<FeoComment> {
    const result = await apiFetch<FeoComment>(`/feo-comments/${commentId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
    if (subsidyId != null) void loadCounts(subsidyId, true)
    return result
  }

  /** Видимость комментариев субсидии — с кэшем и дедупом параллельных запросов
   * (несколько строк дерева монтируются одновременно и все зовут это на mounted). */
  async function loadVisibility(subsidyId: number): Promise<boolean> {
    if (subsidyId in visibilityCache) return visibilityCache[subsidyId]!
    if (!(subsidyId in visibilityPromises)) {
      visibilityPromises[subsidyId] = (async () => {
        try {
          const res = await apiFetch<{ subsidy_id: number; comments_visible: boolean }>(
            `/feo-comments/settings?subsidy_id=${subsidyId}`,
          )
          visibilityCache[subsidyId] = res.comments_visible
        } catch {
          visibilityCache[subsidyId] = true
        }
        return visibilityCache[subsidyId]!
      })()
    }
    return visibilityPromises[subsidyId]!
  }

  async function setVisibility(subsidyId: number, visible: boolean): Promise<void> {
    await apiFetch('/feo-comments/settings', {
      method: 'PUT',
      body: JSON.stringify({ subsidy_id: subsidyId, comments_visible: visible }),
    })
    visibilityCache[subsidyId] = visible
  }

  /** Синхронное чтение для шаблонов — до первой загрузки считаем «видимо»
   * (умолчание сервера тоже True, см. get_comments_visibility). Смысл этого
   * флага сменился (правка 2026-09-14, жалоба владельца): раньше им прятали
   * саму иконку/ветку комментария, теперь иконка видна ВСЕГДА, а флаг задаёт
   * «развёрнуты все ветки по умолчанию» — общий переключатель в FeoTreeRow.vue. */
  function isVisibleCached(subsidyId: number | null | undefined): boolean {
    if (subsidyId == null) return true
    return visibilityCache[subsidyId] ?? true
  }

  /** Широковещательный сигнал «разверни/сверни ВСЕ ветки разом» — общий
   * переключатель субсидии (FeoTreeRow.vue) один физически, но веток много
   * (по одной на каждую уже смонтированную категорию в FeoTreeRow.vue и на
   * каждую плановую позицию в FeoLevel5Panel.vue), и каждая хранит своё
   * раскрытие в СВОЁМ локальном состоянии компонента (commentsExpanded /
   * commentsExpandedIds) — иначе никак не подвинуть их все одним кликом.
   * version растёт при каждом переключении (даже если expanded то же самое,
   * что и раньше) — наблюдатели реагируют на watch(version), а не на
   * (subsidyId, expanded), чтобы повторное «включили — выключили — включили»
   * снова применилось, а не было проигнорировано как «значение не менялось».
   * После применения сигнала индивидуальный клик по иконке ветки работает как
   * обычно и НИКАК не переписывает этот сигнал обратно — общий переключатель
   * лишь один раз проставляет состояние всем, не удерживает его насильно. */
  const expandAllSignal = reactive<{ subsidyId: number | null; expanded: boolean; version: number }>({
    subsidyId: null,
    expanded: false,
    version: 0,
  })
  function broadcastExpandAll(subsidyId: number, expanded: boolean): void {
    expandAllSignal.subsidyId = subsidyId
    expandAllSignal.expanded = expanded
    expandAllSignal.version++
  }

  return {
    fetchThread, addComment, replyToComment, loadVisibility, setVisibility, isVisibleCached,
    expandAllSignal, broadcastExpandAll,
    loadCounts, categoryCommentCount, plannedItemCommentCount,
  }
}

/** «11:39 Сегодня» / «11:39 Вчера» / «11:39 05.09» — формат времени комментария
 * по макету владельца. Не нашлось готового форматтера с такой формой нигде в
 * проекте (frontend/src/utils/relativeTime.ts даёт «N минут назад», chatFormat.
 * ts::formatTime — время без подписи «Сегодня/Вчера») — оба файла вне списка,
 * разрешённого для этой задачи, поэтому не расширяем их, а не потому что
 * подошли бы по форме. */
export function formatCommentTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000)
  if (diffDays === 0) return `${time} Сегодня`
  if (diffDays === 1) return `${time} Вчера`
  const sameYear = d.getFullYear() === now.getFullYear()
  const dateStr = d.toLocaleDateString('ru-RU', sameYear ? { day: '2-digit', month: '2-digit' } : { day: '2-digit', month: '2-digit', year: 'numeric' })
  return `${time} ${dateStr}`
}
