import { defineStore } from 'pinia'

interface UserMe {
  username: string
  is_admin: boolean
}

interface AuthState {
  token: string | null
  user: UserMe | null
}

const TOKEN_KEY = 'audio_intel_token'

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: null,
    user: null,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token),
  },

  actions: {
    hydrate() {
      if (process.client) {
        const stored = localStorage.getItem(TOKEN_KEY)
        if (stored) this.token = stored
      }
    },
    setToken(token: string) {
      this.token = token
      if (process.client) localStorage.setItem(TOKEN_KEY, token)
    },
    setUser(user: UserMe | null) {
      this.user = user
    },
    logout() {
      this.token = null
      this.user = null
      if (process.client) localStorage.removeItem(TOKEN_KEY)
    },
  },
})
