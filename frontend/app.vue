<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <header class="border-b bg-white">
      <div class="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
        <NuxtLink to="/" class="font-semibold text-lg">Audio Intelligence</NuxtLink>
        <div v-if="auth.isAuthenticated" class="flex items-center gap-3 text-sm">
          <span class="text-slate-500">{{ auth.user?.username }}</span>
          <button class="text-slate-700 hover:text-slate-900 underline" @click="logout">Logout</button>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-6xl px-4 py-6">
      <NuxtPage />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function logout() {
  auth.logout()
  await router.push('/login')
}
</script>
