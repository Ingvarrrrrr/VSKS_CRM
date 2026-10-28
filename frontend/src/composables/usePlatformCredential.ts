import { ref, reactive, watch } from 'vue'
import { apiFetch } from '../api'

export interface PlatformCred {
  platform: string
  login: string
  has_password: boolean
}

/** Один и тот же CRUD учётных данных площадки (GET/PUT/DELETE
 * /users/{id}/platform-credentials/{platform}) — ПРАВИЛО №6: единственная
 * реализация, используется и для Фабриканта, и для Росэлторг.Бизнес
 * (UserPlatformCredentialsSection.vue инстанцирует этот composable дважды).
 *
 * `requireLogin=false` — для площадок без понятия логина (Росэлторг: только
 * интеграционный токен) — login отправляется пустой строкой (поле в БД
 * NOT NULL, но допускает "").
 */
export function usePlatformCredential(userId: () => number, platform: string, requireLogin = true) {
  const loading = ref(false)
  const saving = ref(false)
  const deleting = ref(false)
  const deleteConfirm = ref(false)

  const cred = ref<PlatformCred | null>(null)
  const form = reactive({ login: '', password: '' })

  async function loadCred() {
    loading.value = true
    try {
      const data = await apiFetch<PlatformCred[]>(`/users/${userId()}/platform-credentials`)
      const found = data.find(c => c.platform === platform) ?? null
      cred.value = found
      form.login = found?.login ?? ''
      form.password = ''
    } catch (e: any) {
      throw new Error(e?.payload?.message || e?.message || 'Ошибка загрузки учётки')
    } finally {
      loading.value = false
    }
  }

  async function saveCred() {
    if (requireLogin && !form.login.trim()) return
    saving.value = true
    try {
      const body: Record<string, string> = { login: requireLogin ? form.login.trim() : '' }
      if (form.password) body.password = form.password
      await apiFetch(`/users/${userId()}/platform-credentials/${platform}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      form.password = ''
      await loadCred()
    } catch (e: any) {
      throw new Error(e?.payload?.message || e?.message || 'Ошибка сохранения')
    } finally {
      saving.value = false
    }
  }

  function confirmDelete() {
    deleteConfirm.value = true
  }

  async function doDelete() {
    deleting.value = true
    try {
      await apiFetch(`/users/${userId()}/platform-credentials/${platform}`, { method: 'DELETE' })
      cred.value = null
      form.login = ''
      form.password = ''
      deleteConfirm.value = false
    } catch (e: any) {
      deleteConfirm.value = false
      throw new Error(e?.payload?.message || e?.message || 'Ошибка удаления')
    } finally {
      deleting.value = false
    }
  }

  watch(userId, (id) => {
    if (id) loadCred()
  }, { immediate: true })

  return { loading, saving, deleting, deleteConfirm, cred, form, loadCred, saveCred, confirmDelete, doDelete }
}
