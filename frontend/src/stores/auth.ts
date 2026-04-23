import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const effectiveTabs = ref<Set<string>>(new Set())
  const effectiveActions = ref<Set<string>>(new Set())
  const loaded = ref(false)

  async function loadPermissions(orgId?: number | string | null) {
    const qs = orgId ? `?org_id=${orgId}` : ''
    try {
      const me = await apiFetch<any>(`/users/me${qs}`)
      effectiveTabs.value = new Set(me?.permissions?.tabs ?? [])
      effectiveActions.value = new Set(me?.permissions?.actions ?? [])
      loaded.value = true
      if (me?.role) localStorage.setItem('user_role', me.role)
    } catch (e) {
      console.warn('[auth] loadPermissions failed', e)
      effectiveTabs.value = new Set()
      effectiveActions.value = new Set()
      loaded.value = true  // fail-open — don't block router forever
    }
  }

  function hasTab(key: string): boolean {
    const role = localStorage.getItem('user_role')
    if (role === 'superadmin') return true
    return effectiveTabs.value.has(key)
  }

  function hasAction(key: string): boolean {
    const role = localStorage.getItem('user_role')
    if (role === 'superadmin') return true
    return effectiveActions.value.has(key)
  }

  function clear() {
    effectiveTabs.value = new Set()
    effectiveActions.value = new Set()
    loaded.value = false
  }

  return { effectiveTabs, effectiveActions, loaded, loadPermissions, hasTab, hasAction, clear }
})
