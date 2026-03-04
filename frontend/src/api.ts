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
      window.location.href = '/login'
      throw new Error('Сессия истекла, войдите снова')
    }
    const text = await res.text()
    let detail = text
    try {
      const json = JSON.parse(text)
      if (json.detail) detail = json.detail
    } catch {}
    const err: any = new Error(detail)
    err.status = res.status
    err.detail = detail
    throw err
  }
  return res.json()
}
