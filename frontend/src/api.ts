const TOKEN_KEY = 'crm_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function errorMessage(detail: unknown): string {
  if (!detail) return 'Request failed'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.filter((x: unknown) => x !== 'body').join('.') : ''
        return loc ? `${loc}: ${d.msg}` : d.msg
      })
      .join('; ')
  if (typeof detail === 'object' && detail && 'message' in detail) return String((detail as { message: string }).message)
  return JSON.stringify(detail)
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>

export function qs(params?: Params): string {
  if (!params) return ''
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)))
    else sp.append(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; params?: Params; form?: FormData } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (options.form) body = options.form
  else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  const res = await fetch(`/api${path}${qs(options.params)}`, { method: options.method ?? 'GET', headers, body })
  if (res.status === 401 && path !== '/auth/login') {
    setToken(null)
    window.location.href = '/login'
  }
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      detail = res.statusText
    }
    throw new ApiError(res.status, errorMessage(detail), detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function download(path: string, params?: Params) {
  const token = getToken()
  const res = await fetch(`/api${path}${qs(params)}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? 'export'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}
