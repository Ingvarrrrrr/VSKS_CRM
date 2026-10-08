// 152-ФЗ: гейт согласия после входа — ЕДИНСТВЕННОЕ место, которое знает,
// нужно ли показать /consent-required (ПРАВИЛО №6). Сервер решает сам
// (backend/app/routers/legal.py GET /api/legal/consent-status,
// backend/app/services/consent_status.py) — этот модуль только кэширует
// его ответ на сессию приложения, как totalUnread/wsConnected в useChat.ts
// (module-level singleton ref, без Pinia — тот же паттерн проекта).
//
// Кэш живёт, пока не вызван resetConsentGate() (логин/логаут без полной
// перезагрузки страницы — см. AppBar.vue:logout(); LoginView.vue делает
// window.location.href после входа, т.е. полную перезагрузку, и кэш
// обновится сам при следующем импорте модуля).
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface ConsentStatus {
  pd_consent_required: boolean
  poruchenie_required: boolean
  poruchenie_org: { id: number; name: string } | null
  pd_version: string
  poruchenie_version: string
}

const checked = ref(false)
const status = ref<ConsentStatus | null>(null)

export function resetConsentGate(): void {
  checked.value = false
  status.value = null
}

export function consentGateRequired(s: ConsentStatus | null): boolean {
  return !!s && (s.pd_consent_required || s.poruchenie_required)
}

/**
 * Запрашивает статус согласия с сервера, если ещё не запрашивал в этой
 * сессии (router/index.ts beforeEach вызывает на каждой навигации — кэш
 * избавляет от запроса на каждый переход). Сетевая ошибка НЕ блокирует
 * навигацию навсегда: checked остаётся false, следующая навигация попробует
 * снова (задание — «пропустить и попробовать при следующей навигации»).
 */
export async function ensureConsentGateLoaded(): Promise<ConsentStatus | null> {
  if (checked.value) return status.value
  try {
    const data = await apiFetch<ConsentStatus>('/legal/consent-status', {
      suppressErrorDialog: true,
    })
    status.value = data
    checked.value = true
  } catch (e) {
    console.warn('[consent-gate] GET /legal/consent-status failed, skipping for this navigation', e)
  }
  return status.value
}
