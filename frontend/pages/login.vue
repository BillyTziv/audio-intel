<template>
  <div class="max-w-md mx-auto mt-12 bg-white border rounded-xl shadow-sm p-6">
    <h1 class="text-xl font-semibold mb-4">Sign in</h1>
    <form @submit.prevent="onSubmit" class="space-y-4">
      <div>
        <label class="block text-sm font-medium mb-1">Username</label>
        <input v-model="username" required autocomplete="username"
               class="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label class="block text-sm font-medium mb-1">Password</label>
        <input v-model="password" type="password" required autocomplete="current-password"
               class="w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button type="submit" :disabled="loading"
              class="w-full bg-blue-600 text-white rounded py-2 font-medium hover:bg-blue-700 disabled:opacity-60">
        {{ loading ? 'Signing in…' : 'Sign in' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const loading = ref(false)
const router = useRouter()
const { login } = useAuth()

async function onSubmit() {
  error.value = null
  loading.value = true
  try {
    await login(username.value, password.value)
    await router.push('/')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'login failed'
  } finally {
    loading.value = false
  }
}
</script>
