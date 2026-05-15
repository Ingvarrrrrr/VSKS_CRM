// Phase 26-ZZ: server-side search контрагентов вместо bulk-load.
// На больших каталогах bulk-load каталога не масштабируется. Read views
// используют purchase.contractor_name из backend JOIN, фронту нечего
// догружать. Выбор/фильтр — server-search с debounce на стороне view'а.
//
// Использование:
//   import { useContractorsStore } from '@/stores/contractors'
//   const store = useContractorsStore()
//   await store.search('сбербанк', 50)              // server search + cache fill
//   const c = store.getById(42)                      // sync, из cache
//   store.putToCache({ id: 1, name: '...' })         // ручное пополнение из purchase JSON
import { defineStore } from 'pinia'
import { apiFetch } from '@/api'

interface Contractor {
  id: number
  name: string
  inn?: string
  [k: string]: any
}

export const useContractorsStore = defineStore('contractors', {
  state: () => ({
    cache: new Map<number, Contractor>(),
    searchResults: [] as Contractor[],
    searching: false as boolean,
    _searchAbort: null as AbortController | null,
  }),
  getters: {
    getById: (s) => (id: number): Contractor | null => s.cache.get(id) || null,
  },
  actions: {
    putToCache(c: Contractor) {
      if (c && c.id) this.cache.set(c.id, c)
    },
    putManyToCache(arr: Contractor[]) {
      if (!Array.isArray(arr)) return
      for (const c of arr) this.putToCache(c)
    },
    async search(q: string, limit = 50): Promise<Contractor[]> {
      // Отменяем in-flight запрос — пользователь продолжает печатать
      if (this._searchAbort) {
        try { this._searchAbort.abort() } catch {}
      }
      const ctrl = new AbortController()
      this._searchAbort = ctrl
      this.searching = true
      try {
        const qParam = q ? `&search=${encodeURIComponent(q)}` : ''
        const data = await apiFetch<Contractor[]>(
          `/contractors/?limit=${limit}${qParam}`,
          { signal: ctrl.signal }
        )
        if (ctrl.signal.aborted) return this.searchResults
        const arr = Array.isArray(data) ? data : []
        this.searchResults = arr
        this.putManyToCache(arr)
        return arr
      } catch (e: any) {
        if (e?.name === 'AbortError') return this.searchResults
        console.error('contractors search failed', e)
        return this.searchResults
      } finally {
        if (this._searchAbort === ctrl) {
          this._searchAbort = null
          this.searching = false
        }
      }
    },
    invalidate() {
      this.cache.clear()
      this.searchResults = []
    },
  },
})
