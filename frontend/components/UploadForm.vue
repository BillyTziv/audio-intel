<template>
  <section class="bg-white border rounded-xl p-5 shadow-sm">
    <h2 class="text-lg font-semibold mb-3">Upload audio</h2>
    <form @submit.prevent="onSubmit" class="flex flex-col gap-3 sm:flex-row sm:items-center">
      <input ref="fileInput" type="file" accept="audio/*,video/mp4,video/webm,.m4a,.mp3,.wav,.flac,.ogg,.aac,.webm,.mp4"
             @change="onChange" class="block flex-1 text-sm" />
      <button :disabled="!file || uploading" type="submit"
              class="bg-blue-600 text-white px-4 py-2 rounded font-medium hover:bg-blue-700 disabled:opacity-60">
        {{ uploading ? `Uploading ${pct}%` : 'Upload' }}
      </button>
    </form>
    <p v-if="error" class="text-sm text-red-600 mt-2">{{ error }}</p>
    <p v-if="file" class="text-sm text-slate-500 mt-2">
      {{ file.name }} · {{ humanSize(file.size) }}
    </p>
  </section>
</template>

<script setup lang="ts">
const emit = defineEmits<{ (e: 'uploaded', jobId: string): void }>()
const config = useRuntimeConfig()
const auth = useAuthStore()

const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const uploading = ref(false)
const pct = ref(0)
const error = ref<string | null>(null)

function onChange(e: Event) {
  const t = e.target as HTMLInputElement
  file.value = t.files && t.files[0] ? t.files[0] : null
  error.value = null
}

function humanSize(b: number) {
  const u = ['B','KB','MB','GB']
  let i = 0; let n = b
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(1)} ${u[i]}`
}

function onSubmit() {
  if (!file.value) return
  error.value = null
  uploading.value = true
  pct.value = 0

  const form = new FormData()
  form.append('file', file.value)

  const xhr = new XMLHttpRequest()
  xhr.open('POST', `${config.public.apiBase}/audio/upload`)
  if (auth.token) xhr.setRequestHeader('Authorization', `Bearer ${auth.token}`)

  xhr.upload.onprogress = (ev) => {
    if (ev.lengthComputable) pct.value = Math.round((ev.loaded / ev.total) * 100)
  }
  xhr.onerror = () => {
    uploading.value = false
    error.value = 'network error'
  }
  xhr.onload = () => {
    uploading.value = false
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText)
        emit('uploaded', data.job_id)
        file.value = null
        if (fileInput.value) fileInput.value.value = ''
      } catch (_) { /* ignore */ }
    } else if (xhr.status === 401) {
      auth.logout()
      navigateTo('/login')
    } else {
      try {
        const data = JSON.parse(xhr.responseText)
        error.value = data.detail || `upload failed (${xhr.status})`
      } catch (_) {
        error.value = `upload failed (${xhr.status})`
      }
    }
  }
  xhr.send(form)
}
</script>
