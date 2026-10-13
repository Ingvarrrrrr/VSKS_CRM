// Единый источник истины для выбора пользователя по cookie-плашке (ПРАВИЛО №6).
// Все компоненты (CookieBanner, LegalFooter, LegalDocView) читают/пишут выбор
// только через этот композабл — ни один из них не трогает localStorage напрямую.
import { computed, reactive } from 'vue'
import { LEGAL_DOCS } from '@/legal/documents.generated'

export type CookieChoice = 'all' | 'necessary'

interface CookieConsentState {
  choice: CookieChoice | null
  version: string | null
  at: string | null
}

const STORAGE_KEY = 'gala_cookie_choice'
const LEGACY_STORAGE_KEY = 'gala_cookie_consent_accepted'

const CURRENT_DOC_VERSION = LEGAL_DOCS.cookies?.version ?? '1.0'

function readState(): CookieConsentState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<CookieConsentState>
      if (parsed && (parsed.choice === 'all' || parsed.choice === 'necessary')) {
        return {
          choice: parsed.choice,
          version: typeof parsed.version === 'string' ? parsed.version : null,
          at: typeof parsed.at === 'string' ? parsed.at : null,
        }
      }
    }
  } catch {
    // localStorage недоступен (приватный режим/заблокированные cookies) —
    // трактуем как «выбора нет», плашка просто будет показываться каждый раз.
  }

  // Миграция со старого ключа: прежняя плашка знала только «Понятно»,
  // что по смыслу равнозначно «принять всё» предыдущей редакции документа.
  // Версию сознательно не ставим в текущую — если документ обновился,
  // needsChoice всё равно попросит выбрать заново.
  try {
    if (localStorage.getItem(LEGACY_STORAGE_KEY) === '1') {
      localStorage.removeItem(LEGACY_STORAGE_KEY)
      const migrated: CookieConsentState = { choice: 'all', version: null, at: null }
      writeState(migrated)
      return migrated
    }
  } catch {
    // см. выше
  }

  return { choice: null, version: null, at: null }
}

function writeState(state: CookieConsentState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Ничего не сохранится — плашка появится снова при следующей загрузке,
    // не критично (как и раньше в CookieBanner.vue).
  }
}

// Реактивное состояние живёт в модуле — один экземпляр на всё приложение,
// так что reset() в подвале немедленно показывает плашку без перезагрузки.
const state = reactive<CookieConsentState>(readState())

export function useCookieConsent() {
  const choice = computed(() => state.choice)
  const at = computed(() => state.at)

  const needsChoice = computed(() => {
    return state.choice === null || state.version !== CURRENT_DOC_VERSION
  })

  const allowsOptional = computed(() => state.choice === 'all' && !needsChoice.value)

  function choose(next: CookieChoice) {
    state.choice = next
    state.version = CURRENT_DOC_VERSION
    state.at = new Date().toISOString()
    writeState({ choice: state.choice, version: state.version, at: state.at })
  }

  function reset() {
    state.choice = null
    state.version = null
    state.at = null
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // см. выше
    }
  }

  return {
    choice,
    at,
    needsChoice,
    allowsOptional,
    choose,
    reset,
    docVersion: CURRENT_DOC_VERSION,
  }
}
