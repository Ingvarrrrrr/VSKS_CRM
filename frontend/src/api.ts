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
