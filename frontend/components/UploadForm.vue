<template>
  <div>
    <form @submit.prevent="onSubmit" class="flex flex-col gap-3 sm:flex-row sm:items-center">
      <input ref="fileInput" type="file" accept="audio/*,video/mp4,video/webm,.m4a,.mp3,.wav,.flac,.ogg,.aac,.webm,.mp4"
             @change="onChange" class="block flex-1 text-sm" />
      <button :disabled="!file || uploading" type="submit"
              class="bg-blue-600 text-white px-4 py-2 rounded font-medium hover:bg-blue-700 disabled:opacity-60">
        {{ uploading ? `Uploading ${pct}%` : 'Upload' }}
      </button>
    </form>

    <label class="mt-2 inline-flex items-center gap-2 text-sm text-slate-700 select-none">
      <input type="checkbox" v-model="diarize" class="h-4 w-4 rounded border-slate-300" />
      <span>Identify speakers (diarization)</span>
      <span class="text-xs text-slate-500">— slower, separates who said what</span>
    </label>

    <button type="button" @click="showDetails = !showDetails"
            class="mt-3 text-sm text-blue-600 hover:underline flex items-center gap-1">
      <span>{{ showDetails ? '▾' : '▸' }}</span>
      <span>Details (title, project, participants…)</span>
      <span class="text-xs text-slate-500">— optional</span>
    </button>

    <div v-if="showDetails" class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-slate-50 border rounded">
      <label class="text-sm flex flex-col gap-1">
        <span class="text-slate-700">Title</span>
        <input type="text" v-model="title" maxlength="512" placeholder="e.g. Atlas kickoff meeting"
               class="border rounded px-2 py-1 text-sm" />
      </label>
      <label class="text-sm flex flex-col gap-1">
        <span class="text-slate-700">Project</span>
        <input type="text" v-model="project" maxlength="255" placeholder="e.g. Atlas"
               class="border rounded px-2 py-1 text-sm" />
      </label>
      <label class="text-sm flex flex-col gap-1 sm:col-span-2">
        <span class="text-slate-700">Description</span>
        <textarea v-model="description" rows="2" placeholder="Optional context — fed to the summarizer"
                  class="border rounded px-2 py-1 text-sm"></textarea>
      </label>
      <label class="text-sm flex flex-col gap-1">
        <span class="text-slate-700">Meeting date</span>
        <input type="datetime-local" v-model="meetingDateLocal"
               class="border rounded px-2 py-1 text-sm" />
      </label>
      <label class="text-sm flex flex-col gap-1">
        <span class="text-slate-700">Participants <span class="text-xs text-slate-500">(comma-separated)</span></span>
        <input type="text" v-model="participants" placeholder="Maria, John, Alex"
               class="border rounded px-2 py-1 text-sm" />
      </label>
    </div>

    <p v-if="error" class="text-sm text-red-600 mt-2">{{ error }}</p>
    <p v-if="file" class="text-sm text-slate-500 mt-2">
      {{ file.name }} · {{ humanSize(file.size) }}
    </p>
  </div>
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
const diarize = ref(false)

const showDetails = ref(false)
const title = ref('')
const project = ref('')
const description = ref('')
const meetingDateLocal = ref('')
const participants = ref('')

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

function resetMetadata() {
  title.value = ''
  project.value = ''
  description.value = ''
  meetingDateLocal.value = ''
  participants.value = ''
}

function onSubmit() {
  if (!file.value) return
  error.value = null
  uploading.value = true
  pct.value = 0

  const form = new FormData()
  form.append('file', file.value)
  form.append('diarize', diarize.value ? 'true' : 'false')
  if (title.value.trim()) form.append('title', title.value.trim())
  if (project.value.trim()) form.append('project', project.value.trim())
  if (description.value.trim()) form.append('description', description.value.trim())
  if (meetingDateLocal.value) {
    form.append('meeting_date', new Date(meetingDateLocal.value).toISOString())
  }
  if (participants.value.trim()) form.append('participants', participants.value.trim())

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
        resetMetadata()
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
