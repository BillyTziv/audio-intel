import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuthStore()
  if (process.client && !auth.token && to.path !== '/login') {
    return navigateTo('/login')
  }
  if (process.client && auth.token && to.path === '/login') {
    return navigateTo('/')
  }
})
