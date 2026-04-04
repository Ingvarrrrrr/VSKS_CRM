import { ref } from 'vue'
import { apiFetch } from '@/api'

// Module-level singleton — loads once per session, reset on page reload
const hiddenSections = ref<Set<string>>(new Set())
const loaded = ref(false)
const loading = ref(false)

export function useOrgConfig() {
  async function loadConfig() {
    if (loaded.value || loading.value) return
    loading.value = true
    try {
      const data = await apiFetch<{ hidden_sections: string[] }>('/org/section-config')
      hiddenSections.value = new Set(data.hidden_sections)
      loaded.value = true
    } catch {
      hiddenSections.value = new Set()
    } finally {
      loading.value = false
    }
  }

  function isSectionHidden(key: string): boolean {
    return hiddenSections.value.has(key)
  }

  async function updateConfig(items: { section_key: string; is_hidden: boolean }[]) {
    await apiFetch('/org/section-config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(items),
    })
    loaded.value = false
    await loadConfig()
  }

  return { hiddenSections, isSectionHidden, loadConfig, updateConfig, loading }
}
