import { ref } from 'vue'

// Singleton shared across all components — global "search the whole database" query.
const appSearch = ref('')

export function useAppSearch() {
  return { appSearch }
}
