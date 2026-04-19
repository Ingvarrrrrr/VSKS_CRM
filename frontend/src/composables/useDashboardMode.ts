import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'

export type DashboardMode = 'classic' | 'radar'

const MODE_STORAGE_PREFIX = 'dashboard-mode-'

function getStorageKey(): string {
  const userId = localStorage.getItem('user_id')
  return MODE_STORAGE_PREFIX + (userId || 'default')
}

function readStoredMode(): DashboardMode {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw === 'classic' || raw === 'radar') return raw
  } catch { /* localStorage disabled — fall through */ }
  return 'classic'
}

function writeStoredMode(m: DashboardMode): void {
  try {
    localStorage.setItem(getStorageKey(), m)
  } catch { /* localStorage disabled — silent */ }
}

export interface UseDashboardModeReturn {
  mode: Ref<DashboardMode>
  setMode: (m: DashboardMode) => void
  /** Call from onMounted to sync URL with stored mode on first visit. */
  syncRouteWithMode: () => void
}

export function useDashboardMode(): UseDashboardModeReturn {
  const router = useRouter()
  const mode = ref<DashboardMode>(readStoredMode())

  function setMode(m: DashboardMode): void {
    if (m !== 'classic' && m !== 'radar') return
    mode.value = m
    writeStoredMode(m)
    const targetPath = m === 'radar' ? '/dashboard/radar' : '/dashboard'
    if (router.currentRoute.value.path !== targetPath) {
      router.push(targetPath)
    }
  }

  function syncRouteWithMode(): void {
    const current = router.currentRoute.value.path
    const desired = mode.value === 'radar' ? '/dashboard/radar' : '/dashboard'
    // Only redirect if user is on a dashboard route — do not redirect from unrelated routes.
    if ((current === '/dashboard' || current === '/dashboard/radar') && current !== desired) {
      router.push(desired)
    }
  }

  return { mode, setMode, syncRouteWithMode }
}
