import { useAuthStore } from '~/stores/auth'

interface ApiOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  raw?: boolean
}

export function useApi() {
  const config = useRuntimeConfig()
  const auth = useAuthStore()
  const router = useRouter()

  async function request<T>(path: string, opts: ApiOptions = {}): Promise<T> {
    const url = `${config.public.apiBase}${path}`
    const headers: Record<string, string> = { ...(opts.headers || {}) }
    if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`
    let body: BodyInit | undefined
    if (opts.body instanceof FormData) {
      body = opts.body
    } else if (opts.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(opts.body)
    }

    const res = await fetch(url, { method: opts.method || 'GET', headers, body })
    if (res.status === 401) {
      auth.logout()
      if (process.client) await router.push('/login')
      throw new Error('unauthorized')
    }
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`
      try {
        const data = await res.json()
        if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      } catch (_) { /* ignore */ }
      throw new Error(detail)
    }
    if (opts.raw) return (res as unknown) as T
    if (res.status === 204) return undefined as T
    return (await res.json()) as T
  }

  return {
    get: <T>(path: string) => request<T>(path),
    post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
    patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
    upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
    downloadUrl: (path: string) => `${config.public.apiBase}${path}`,
    rawFetch: (path: string) => request<Response>(path, { raw: true }),
  }
}
