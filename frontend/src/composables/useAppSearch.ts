import { ref } from 'vue'

// Singleton shared across all components
const appSearch = ref('')
const appSearchScope = ref<'page' | 'global'>('page')

export function useAppSearch() {
  return { appSearch, appSearchScope }
}
