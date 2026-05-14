import { useAuthStore } from '~/stores/auth'

export function useAuth() {
  const auth = useAuthStore()
  const api = useApi()
  const router = useRouter()

  async function login(username: string, password: string) {
    const data = await api.post<{ access_token: string; expires_in: number }>('/auth/login', {
      username, password,
    })
    auth.setToken(data.access_token)
    try {
      const me = await api.get<{ username: string; is_admin: boolean }>('/auth/me')
      auth.setUser(me)
    } catch (_) { /* ignore */ }
  }

  async function refreshMe() {
    if (!auth.token) return
    try {
      const me = await api.get<{ username: string; is_admin: boolean }>('/auth/me')
      auth.setUser(me)
    } catch (_) {
      auth.logout()
      await router.push('/login')
    }
  }

  return { login, refreshMe }
}
