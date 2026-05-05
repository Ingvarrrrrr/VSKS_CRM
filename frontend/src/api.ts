const BASE = '/api'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
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
  if (!res.ok) {
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
    // If detail is a structured object with a message field (e.g. STATUS_TRANSITION_BLOCKED)
    if (rawDetail && typeof rawDetail === 'object' && !Array.isArray(rawDetail) && rawDetail.message) {
      rawDetail = rawDetail.message
    }
    let detailMsg = parsed?.message || rawDetail || text || 'Ошибка запроса'
    if (Array.isArray(detailMsg)) {
      detailMsg = detailMsg.map((e: any) => {
        const field = (e.loc || []).filter((l: any) => l !== 'body').join(' → ')
        return field ? `${field}: ${e.msg}` : e.msg
      }).join('; ')
    }
    const payload = {
      code: parsed?.code || `HTTP_${res.status}`,
      message: detailMsg,
      details: parsed?.details || text || '',
      correlation_id: parsed?.correlation_id || res.headers.get('X-Correlation-ID') || '',
    }
    // 409 Conflict = expected business logic error; handled locally by callers, no global dialog
    if (res.status !== 409) {
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
