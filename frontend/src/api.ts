const BASE = '/api'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// 27.4-24: счётчик подряд 5xx/502 ошибок для авто-восстановления PWA из stale-SW кеша.
// Если 3+ raз подряд получаем 5xx — это сильный сигнал на сломанный кеш / SW: чистим всё и reload.
let _consecutive5xx = 0
let _autoRecoveryTriggered = false

// Глобальный индикатор загрузки: счётчик активных запросов.
// App.vue слушает 'api-loading' и показывает полосу прогресса сверху.
let _inflight = 0
function emitLoading() {
  try { window.dispatchEvent(new CustomEvent('api-loading', { detail: { count: _inflight } })) } catch {}
}

export async function forceClearCacheAndReload(): Promise<void> {
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map(r => r.unregister().catch(() => {})))
    }
    if ('caches' in window) {
      const keys = await caches.keys()
      await Promise.all(keys.map(k => caches.delete(k).catch(() => false)))
    }
  } catch (e) {
    console.warn('[recovery] cache clear failed', e)
  }
  // localStorage намеренно НЕ чистим — иначе разлогинивает.
  window.location.reload()
}

export interface ApiFetchOptions extends RequestInit {
  /** Не показывать глобальный ApiErrorDialog — вызывающий обрабатывает ошибку сам (имеет fallback). */
  suppressErrorDialog?: boolean
  /**
   * Владелец, 29.09: разрешить ОДНУ автоматическую повторную попытку при
   * сетевой ошибке (`TypeError: Failed to fetch` — сервер/DNS/обрыв
   * соединения, НЕ HTTP-ошибка с телом ответа), для не-GET запроса.
   * GET-запросы ретраятся всегда без этой пометки (чтение идемпотентно по
   * природе) — ставить её нужно только на явно безопасные для повтора
   * POST/PUT-запросы вроде предпросмотра импорта (запрос ничего не создаёт
   * в БД, dry-run). Обычный создающий POST (например, создание товара) эту
   * пометку не ставит — повтор при неопределённом исходе первой попытки мог
   * бы задвоить запись.
   */
  retryOnNetworkError?: boolean
}

// Сетевая ошибка (сервер недоступен/DNS/CORS/обрыв соединения — браузерный
// `TypeError: Failed to fetch`, НЕ HTTP-ответ с кодом) — владелец, 29.09:
// «Заявка из плана» после «Товар добавлен» и импорт ФЭО после «Оставить из
// файла (обновит каталог)» показывали пользователю голый текст браузера
// «Failed to fetch» (describeApiError/аналоги читают err.message, когда нет
// err.payload/err.detail — см. frontend/src/utils/apiErrorMessage.ts).
// Раньше эта ветка просто пробрасывала fetchErr как есть — единственная
// обработка ошибки fetch() была на AbortError (таймаут) ниже. Основная
// причина обрывов — внешний nginx на проде пересоздаётся раз в минуту
// (инфраструктура, чинится не здесь), но фронт обязан объяснить это
// по-человечески.
//
// Экспортированы (владелец, 29.09, доработка): несколько мест в проекте
// (useFeoImport.ts, useItemsImport.ts и т.п.) шлют FormData через СЫРОЙ
// fetch() напрямую, в обход apiFetch (нужен свой разбор ответа/прогресс) —
// они ловили ту же голую «Failed to fetch» в своих catch-блоках. Правило №6:
// одно сообщение об ошибке сети — здесь, вызывающий код переиспользует эти
// же функции вместо копии текста.
export function buildFetchError(code: string, message: string, details = '', suppressErrorDialog = false): any {
  const payload = { code, message, details, correlation_id: '' }
  if (!suppressErrorDialog) {
    window.dispatchEvent(new CustomEvent('api-error', { detail: payload }))
  }
  const err: any = new Error(payload.message)
  err.status = 0
  err.detail = payload.message
  err.payload = payload
  return err
}
export function translateFetchThrow(fetchErr: any, suppressErrorDialog = false): any {
  if (fetchErr?.name === 'AbortError') {
    return buildFetchError('REQUEST_TIMEOUT', 'Сервер не ответил за 60 секунд — повторите попытку', '', suppressErrorDialog)
  }
  return buildFetchError('NETWORK_ERROR', 'Нет связи с сервером — повторите действие', fetchErr?.message || '', suppressErrorDialog)
}

/**
 * Один тихий повтор сырого fetch() при сетевой ошибке (не HTTP-ответе) —
 * та же логика, что canRetryNetworkError/doRawFetch внутри apiFetch, для
 * вызывающих, которым apiFetch не подходит (FormData + свой разбор Response).
 * Бросает translateFetchThrow() — тот же формат ошибки, что и apiFetch,
 * так что общий err.payload.message/describeApiError() читают его одинаково.
 * `retryable=false` (обычно — операция НЕ dry-run, реально пишет в БД) —
 * повтора нет, ошибка транслируется сразу же.
 */
export async function fetchWithNetworkRetry(
  doFetch: () => Promise<Response>,
  opts?: { retryable?: boolean; suppressErrorDialog?: boolean },
): Promise<Response> {
  const retryable = opts?.retryable !== false
  try {
    return await doFetch()
  } catch (fetchErr: any) {
    if (fetchErr?.name !== 'AbortError' && retryable) {
      await new Promise(r => setTimeout(r, 1500))
      try {
        return await doFetch()
      } catch (retryErr: any) {
        throw translateFetchThrow(retryErr, opts?.suppressErrorDialog)
      }
    }
    throw translateFetchThrow(fetchErr, opts?.suppressErrorDialog)
  }
}

// Прод, 2026-09-20: apiFetch не имел таймаута вовсе — если бэкенд/сеть зависли
// (например, на заявке №76 из-за тяжёлой загрузки), спиннер крутился вечно, а
// пользователь не понимал, ждать или перезагружать страницу. 60с — заведомо
// больше любого нормального ответа (самые тяжёлые ручки — секунды), но конечно.
const REQUEST_TIMEOUT_MS = 60_000

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const body = options.body && typeof options.body === 'object' && !(options.body instanceof FormData)
    ? JSON.stringify(options.body)
    : options.body
  _inflight += 1
  emitLoading()
  // Внешний AbortController поверх пользовательского options.signal (если он
  // когда-нибудь появится у вызывающих) — на сегодня ни один вызов apiFetch в
  // проекте signal не передаёт, но на всякий случай не затираем его молча.
  const timeoutController = new AbortController()
  const timeoutId = setTimeout(() => timeoutController.abort(), REQUEST_TIMEOUT_MS)
  if (options.signal) {
    if (options.signal.aborted) timeoutController.abort()
    else options.signal.addEventListener('abort', () => timeoutController.abort(), { once: true })
  }
  const method = (options.method || 'GET').toUpperCase()
  // GET (и HEAD) — идемпотентны по природе, ретраим всегда; для остальных
  // методов повтор только по явной пометке retryOnNetworkError (см. её
  // докстринг выше).
  const canRetryNetworkError = method === 'GET' || method === 'HEAD' || options.retryOnNetworkError === true
  const doRawFetch = () => fetch(BASE + path, {
    ...options,
    body,
    signal: timeoutController.signal,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  })
  try {
  let res: Response
  try {
    res = await doRawFetch()
  } catch (fetchErr: any) {
    // Сетевая ошибка (не таймаут) на идемпотентном/явно безопасном запросе —
    // один тихий повтор перед тем, как показать человеку что-либо (владелец,
    // 29.09, см. докстринг canRetryNetworkError выше).
    if (fetchErr?.name !== 'AbortError' && canRetryNetworkError) {
      await new Promise(r => setTimeout(r, 1500))
      try {
        res = await doRawFetch()
      } catch (retryErr: any) {
        throw translateFetchThrow(retryErr, options.suppressErrorDialog)
      }
    } else {
      throw translateFetchThrow(fetchErr, options.suppressErrorDialog)
    }
  }
  // 27.4-24: успешный ответ → сбрасываем счётчик 5xx
  if (res.ok) _consecutive5xx = 0
  if (!res.ok) {
    // Счётчик подряд 5xx — если 3+, авто-чистим SW/кеш (stale bundle)
    if (res.status >= 500 && res.status < 600) {
      _consecutive5xx += 1
      if (_consecutive5xx >= 3 && !_autoRecoveryTriggered) {
        _autoRecoveryTriggered = true
        console.warn(`[recovery] ${_consecutive5xx} consecutive 5xx, clearing SW caches and reloading`)
        // Показываем пользователю что мы делаем (не молча)
        try {
          window.dispatchEvent(new CustomEvent('api-error', {
            detail: {
              code: 'AUTO_RECOVERY',
              message: 'Похоже что бэкенд или кеш не отвечают. Чистим кеш и перезагружаемся через 2 сек...',
              details: '',
              correlation_id: '',
            },
          }))
        } catch {}
        setTimeout(() => { forceClearCacheAndReload() }, 2000)
      }
    } else if (res.status !== 401) {
      // 4xx (кроме 401) — не сбрасываем, но и не считаем как 5xx
    }
    if (res.status === 401) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('user_role')
      localStorage.removeItem('user_name')
      window.location.href = '/'
      throw new Error('Сессия истекла, войдите снова')
    }
    const text = await res.text()
    let parsed: any = null
    try { parsed = JSON.parse(text) } catch {}
    // FastAPI 422 returns detail as array of validation errors or structured object
    let rawDetail = parsed?.detail
    // If detail is a structured object with a code field (e.g. RECEIPT_DUPLICATE) — preserve it
    const structuredDetail = (rawDetail && typeof rawDetail === 'object' && !Array.isArray(rawDetail)) ? rawDetail : null
    if (structuredDetail?.message) {
      rawDetail = structuredDetail.message
    }
    let detailMsg = parsed?.message || rawDetail || text || 'Ошибка запроса'
    if (Array.isArray(detailMsg)) {
      detailMsg = detailMsg.map((e: any) => {
        const field = (e.loc || []).filter((l: any) => l !== 'body').join(' → ')
        return field ? `${field}: ${e.msg}` : e.msg
      }).join('; ')
    }
    const payload = {
      code: structuredDetail?.code || parsed?.code || `HTTP_${res.status}`,
      message: detailMsg,
      details: structuredDetail || parsed?.details || text || '',
      correlation_id: parsed?.correlation_id || res.headers.get('X-Correlation-ID') || '',
    }
    // 409 Conflict = expected business logic error; handled locally by callers, no global dialog
    // INN_NOT_FOUND = user-facing "not found", handled locally with friendly snackbar
    const suppressGlobal = res.status === 409 || payload.code === 'INN_NOT_FOUND' || options.suppressErrorDialog === true
    if (!suppressGlobal) {
      window.dispatchEvent(new CustomEvent('api-error', { detail: payload }))
    }
    const err: any = new Error(payload.message)
    err.status = res.status
    err.detail = payload.message
    err.payload = payload
    throw err
  }
  // 204 No Content (DELETE endpoints) или пустое тело — нечего парсить.
  // Раньше падало с "Failed to execute 'json' on 'Response': Unexpected end of JSON input"
  // при успешном DELETE /api/organizations/{id} → status_code=204.
  if (res.status === 204) return undefined as unknown as T
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('application/json')) {
    const txt = await res.text()
    return (txt ? txt : undefined) as unknown as T
  }
  // Защита от пустого JSON-ответа (Content-Length: 0)
  const text = await res.text()
  if (!text) return undefined as unknown as T
  try {
    return JSON.parse(text) as T
  } catch {
    return undefined as unknown as T
  }
  } finally {
    clearTimeout(timeoutId)
    _inflight -= 1
    emitLoading()
  }
}
