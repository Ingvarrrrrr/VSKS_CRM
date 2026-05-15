// Phase 26-YY: клиентский кэш контрагентов с TTL 5 минут.
// Цель — не дёргать GET /api/contractors/ при каждом mount view'а
// (раньше это было mount-time bulk load 200+ rows на каждой странице).
//
// Использование:
//   import { useContractorsStore } from '@/stores/contractors'
//   const contractorsStore = useContractorsStore()
//   await contractorsStore.ensureLoaded()
//   contractors.value = contractorsStore.list
//
// Свежие данные при необходимости (после CRUD в ContractorsView):
//   contractorsStore.invalidate()
import { defineStore } from 'pinia'
import { apiFetch } from '@/api'

interface Contractor {
  id: number
  name: string
  inn?: string
  [k: string]: any
}

const TTL_MS = 5 * 60 * 1000

export const useContractorsStore = defineStore('contractors', {
  state: () => ({
    list: [] as Contractor[],
    loadedAt: 0 as number,
    loading: false as boolean,
  }),
  getters: {
    getById: (s) => (id: number) => s.list.find(c => c.id === id),
    isFresh: (s) => s.loadedAt > 0 && (Date.now() - s.loadedAt) < TTL_MS,
  },
  actions: {
    async ensureLoaded(force = false) {
      if (!force && this.isFresh && this.list.length) return this.list
      if (this.loading) {
        // Параллельный вызов — ждём окончания текущей загрузки, не делаем второй запрос
        while (this.loading) await new Promise(r => setTimeout(r, 50))
        return this.list
      }
      this.loading = true
      try {
        const data = await apiFetch<Contractor[]>('/contractors/?limit=2000')
        this.list = Array.isArray(data) ? data : []
        this.loadedAt = Date.now()
      } catch (e) {
        console.error('contractors load failed', e)
      } finally {
        this.loading = false
      }
      return this.list
    },
    invalidate() {
      this.loadedAt = 0
    },
  },
})
