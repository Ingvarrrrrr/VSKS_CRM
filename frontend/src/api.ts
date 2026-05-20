const BASE = '/api'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// 27.4-24: счётчик подряд 5xx/502 ошибок для авто-восстановления PWA из stale-SW кеша.
// Если 3+ raз подряд получаем 5xx — это сильный сигнал на сломанный кеш / SW: чистим всё и reload.
let _consecutive5xx = 0
let _autoRecoveryTriggered = false

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

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const body = options.body && typeof options.body === 'object' && !(options.body instanceof FormData)
    ? JSON.stringify(options.body)
    : options.body
  const res = await fetch(BASE + path, {
    ...options,
    body,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  })
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
    const suppressGlobal = res.status === 409 || payload.code === 'INN_NOT_FOUND'
    if (!suppressGlobal) {
      window.dispatchEvent(new CustomEvent('api-error', { detail: payload }))
    }
    const err: any = new Error(payload.message)
    err.status = res.status
    err.detail = payload.message
    err.payload = payload
    throw err
  }
  return res.json()
}
