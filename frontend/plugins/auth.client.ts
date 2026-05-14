import { useAuthStore } from '~/stores/auth'

export default defineNuxtPlugin(async () => {
  const auth = useAuthStore()
  auth.hydrate()
  if (auth.token && !auth.user) {
    const { refreshMe } = useAuth()
    await refreshMe()
  }
})
