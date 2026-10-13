/**
 * Плавный переход со старой схемы (JWT в localStorage('auth_token')) на
 * httpOnly-cookie gala_session, 2026-10-13. Вызывается ОДИН раз на старте
 * приложения, до первого роутер-гварда: если в localStorage остался
 * старый токен — отправляем его бэкенду (POST /api/auth/session-from-token),
 * он ставит cookie, и уже вошедшего пользователя не выкидывает. Токен из
 * localStorage удаляется в любом случае (успех/ошибка) — дальше источник
 * истины только cookie + флаг useAuthFlag.
 */
import { setLoggedIn, clearLoggedIn } from '@/composables/useAuthFlag'

const LEGACY_TOKEN_KEY = 'auth_token'

export async function migrateLegacyToken(): Promise<void> {
  let legacyToken: string | null = null
  try {
    legacyToken = localStorage.getItem(LEGACY_TOKEN_KEY)
  } catch {
    return
  }
  if (!legacyToken) return
  try {
    const res = await fetch('/api/auth/session-from-token', {
      method: 'POST',
      headers: { Authorization: `Bearer ${legacyToken}` },
    })
    if (res.ok) {
      setLoggedIn()
    } else {
      clearLoggedIn()
    }
  } catch {
    // Сеть недоступна — не считаем вошедшим, следующая попытка (перезагрузка)
    // повторит миграцию, пока старый ключ ещё не удалён... но мы его всё
    // равно удаляем ниже (п.10 задачи: удалить независимо от исхода), чтобы
    // не слать протухающий токен на каждый старт бесконечно.
    clearLoggedIn()
  } finally {
    try { localStorage.removeItem(LEGACY_TOKEN_KEY) } catch {}
  }
}
