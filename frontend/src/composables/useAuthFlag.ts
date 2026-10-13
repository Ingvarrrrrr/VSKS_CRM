/**
 * Признак «пользователь вошёл» — единственный источник истины (Правило №6)
 * с 2026-10-13, когда сам JWT переехал в httpOnly-cookie gala_session и
 * перестал быть читаемым из JS вовсе (защита от XSS — см. задачу переноса
 * токена). Раньше весь фронт (роутер-гвард, AppBar, App.vue, api.ts, ~60
 * композаблов) проверял наличие `localStorage.getItem('auth_token')` —
 * теперь токена там нет, и этот флаг — единственная замена такой проверке.
 *
 * ВАЖНО: это НЕ токен и не секрет — просто признак «последний /login или
 * /me прошли успешно», обновляется при логине/логауте/401. Реальная
 * авторизация каждого запроса — только cookie на бэкенде.
 */

const AUTH_FLAG_KEY = 'gala_auth'

export function isLoggedIn(): boolean {
  try {
    return localStorage.getItem(AUTH_FLAG_KEY) === '1'
  } catch {
    return false
  }
}

export function setLoggedIn(): void {
  try {
    localStorage.setItem(AUTH_FLAG_KEY, '1')
  } catch {}
}

export function clearLoggedIn(): void {
  try {
    localStorage.removeItem(AUTH_FLAG_KEY)
  } catch {}
}
