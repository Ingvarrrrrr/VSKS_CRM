import { ref, computed, watch, type Ref } from 'vue'
import { useDisplay } from 'vuetify'

/**
 * Reusable table↔cards view-mode for list views.
 *
 * - On desktop the user toggles `viewMode` ('table' | 'cards'); persisted to localStorage.
 * - On mobile `effectiveView` is forced to 'cards' (every table becomes cards).
 * - Provides search-aware client pagination over an already-filtered source list.
 *
 * The source getter is read ONLY lazily (inside computeds), never synchronously
 * during setup — so `useCardView` is safe to call BEFORE the `source` getter's
 * underlying computed/ref (or its own dependencies) are declared. There is no
 * Temporal-Dead-Zone trap: nothing here evaluates `opts.source()` at call time.
 */
export function useCardView<T>(opts: {
  /** localStorage key for persisting the desktop view mode. */
  storageKey: string
  /** Getter returning the already-filtered (by panel filters) list. */
  source: () => T[]
  /** Optional free-text query getter (the toolbar "Поиск" field). */
  search?: () => string
  /** Fields of an item to match the free-text query against. */
  searchFields?: (item: T) => unknown[]
  /** Cards per page (default 24). */
  pageSize?: number
}) {
  const { mobile } = useDisplay()
  const pageSize = opts.pageSize ?? 24

  const viewMode = ref<'table' | 'cards'>(
    (localStorage.getItem(opts.storageKey) as 'table' | 'cards') || 'table',
  )
  watch(viewMode, v => localStorage.setItem(opts.storageKey, v))

  const effectiveView = computed<'table' | 'cards'>(() =>
    mobile.value ? 'cards' : viewMode.value,
  )

  // Raw page chosen by the user. Never read the source here.
  const rawPage = ref(1)

  const filtered = computed(() => {
    const base = opts.source()
    const q = (opts.search?.() || '').trim().toLowerCase()
    if (!q || !opts.searchFields) return base
    return base.filter(it =>
      opts.searchFields!(it).some(v => String(v ?? '').toLowerCase().includes(q)),
    )
  })

  const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))

  // Clamp lazily inside a computed instead of an eager `watch(totalPages, …)`,
  // which would read the source synchronously at call time and risk a TDZ crash.
  const page = computed<number>({
    get: () => Math.min(Math.max(1, rawPage.value), totalPages.value),
    set: v => { rawPage.value = v },
  })

  const paged = computed(() => {
    const s = (page.value - 1) * pageSize
    return filtered.value.slice(s, s + pageSize)
  })

  return { mobile, viewMode, effectiveView, page, totalPages, paged, filtered }
}

/** Ref-source overload helper for callers holding a Ref instead of a getter. */
export function refGetter<T>(r: Ref<T[]>): () => T[] {
  return () => r.value
}
