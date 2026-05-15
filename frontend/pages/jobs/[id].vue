<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <NuxtLink to="/" class="text-sm text-blue-600 hover:underline">← Back</NuxtLink>
    </div>

    <section v-if="error" class="bg-white border rounded-xl p-5 shadow-sm">
      <p class="text-red-600 text-sm">{{ error }}</p>
    </section>

    <section v-else-if="!job" class="bg-white border rounded-xl p-5 shadow-sm">
      <p class="text-slate-500 text-sm">Loading…</p>
    </section>

    <template v-else>
      <section class="bg-white border rounded-xl p-5 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h1 class="text-xl font-semibold truncate">{{ job.title || job.original_filename }}</h1>
              <span v-if="job.project"
                    class="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5">
                {{ job.project }}
              </span>
            </div>
            <div class="text-sm text-slate-500 mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
              <span v-if="job.title">{{ job.original_filename }}</span>
              <span>{{ humanSize(job.size_bytes) }}</span>
              <span v-if="job.duration_seconds">{{ humanDuration(job.duration_seconds) }}</span>
              <span v-if="job.meeting_date">meeting {{ formatDate(job.meeting_date) }}</span>
              <span>uploaded {{ formatDate(job.created_at) }}</span>
              <span v-if="job.completed_at">finished {{ formatDate(job.completed_at) }}</span>
            </div>
            <div v-if="job.participants && job.participants.length" class="text-sm text-slate-600 mt-1">
              <span class="text-slate-500">Participants:</span> {{ job.participants.join(', ') }}
            </div>
            <p v-if="job.description" class="text-sm text-slate-700 mt-2 whitespace-pre-wrap">{{ job.description }}</p>
          </div>
          <div class="flex items-center gap-2">
            <JobStatusBadge :status="job.status" />
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="startEdit">Edit details</button>
          </div>
        </div>

        <div v-if="editing" class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-slate-50 border rounded">
          <label class="text-sm flex flex-col gap-1">
            <span class="text-slate-700">Title</span>
            <input type="text" v-model="form.title" maxlength="512" class="border rounded px-2 py-1 text-sm" />
          </label>
          <label class="text-sm flex flex-col gap-1">
            <span class="text-slate-700">Project</span>
            <input type="text" v-model="form.project" maxlength="255" class="border rounded px-2 py-1 text-sm" />
          </label>
          <label class="text-sm flex flex-col gap-1 sm:col-span-2">
            <span class="text-slate-700">Description</span>
            <textarea v-model="form.description" rows="2" class="border rounded px-2 py-1 text-sm"></textarea>
          </label>
          <label class="text-sm flex flex-col gap-1">
            <span class="text-slate-700">Meeting date</span>
            <input type="datetime-local" v-model="form.meetingDateLocal" class="border rounded px-2 py-1 text-sm" />
          </label>
          <label class="text-sm flex flex-col gap-1">
            <span class="text-slate-700">Participants <span class="text-xs text-slate-500">(comma-separated)</span></span>
            <input type="text" v-model="form.participants" class="border rounded px-2 py-1 text-sm" />
          </label>
          <div class="sm:col-span-2 flex items-center justify-end gap-2">
            <p v-if="saveError" class="text-sm text-red-600 mr-auto">{{ saveError }}</p>
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="cancelEdit" :disabled="saving">Cancel</button>
            <button class="text-sm bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded disabled:opacity-60"
                    @click="saveEdit" :disabled="saving">
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>

        <div v-if="!['completed','failed'].includes(job.status)" class="mt-4">
          <div class="h-2 bg-slate-200 rounded">
            <div class="h-2 bg-blue-500 rounded transition-all"
                 :style="{ width: `${Math.round((job.progress || 0) * 100)}%` }" />
          </div>
          <p class="text-xs text-slate-500 mt-1">
            {{ Math.round((job.progress || 0) * 100) }}% — {{ job.status }}
          </p>
        </div>

        <div v-if="job.status === 'failed' && job.error_message"
             class="mt-4 bg-red-50 border border-red-200 text-red-800 text-sm rounded p-3 whitespace-pre-wrap">
          {{ job.error_message }}
        </div>
      </section>

      <section v-if="transcript" class="bg-white border rounded-xl shadow-sm">
        <div class="border-b px-5 py-3 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-lg font-semibold">Transcript</h2>
          <div class="flex flex-wrap gap-2">
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="download('txt')">Download .txt</button>
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="download('clean')">.clean.txt</button>
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="download('summary')">.summary.md</button>
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="download('srt')">.srt</button>
            <button class="text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1 rounded" @click="download('json')">.json</button>
          </div>
        </div>
        <TranscriptViewer :transcript="transcript" />
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import JobStatusBadge from '~/components/JobStatusBadge.vue'
import TranscriptViewer from '~/components/TranscriptViewer.vue'

interface Job {
  id: string
  original_filename: string
  size_bytes: number
  duration_seconds: number | null
  status: string
  progress: number
  error_message: string | null
  created_at: string
  completed_at: string | null
  title: string | null
  project: string | null
  description: string | null
  meeting_date: string | null
  participants: string[] | null
}

interface Transcript {
  language: string | null
  raw_text: string | null
  cleaned_text: string | null
  summary: string | null
  key_points: unknown[] | null
  decisions: unknown[] | null
  action_items: unknown[] | null
  segments: { start: number; end: number; text: string; speaker?: string | null }[] | null
  speakers?: unknown[] | null
}

const route = useRoute()
const api = useApi()
const auth = useAuthStore()
const id = computed(() => String(route.params.id))

const job = ref<Job | null>(null)
const transcript = ref<Transcript | null>(null)
const error = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const editing = ref(false)
const saving = ref(false)
const saveError = ref<string | null>(null)
const form = ref({
  title: '',
  project: '',
  description: '',
  meetingDateLocal: '',
  participants: '',
})

async function fetchJob() {
  try {
    job.value = await api.get<Job>(`/audio/jobs/${id.value}`)
    if (job.value.status === 'completed' && !transcript.value) {
      try {
        transcript.value = await api.get<Transcript>(`/audio/jobs/${id.value}/transcript`)
      } catch (_) { /* not ready */ }
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'failed to load recording'
  }
}

function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function startEdit() {
  if (!job.value) return
  form.value = {
    title: job.value.title || '',
    project: job.value.project || '',
    description: job.value.description || '',
    meetingDateLocal: toLocalInput(job.value.meeting_date),
    participants: (job.value.participants || []).join(', '),
  }
  saveError.value = null
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  saveError.value = null
}

async function saveEdit() {
  if (!job.value) return
  saving.value = true
  saveError.value = null
  const parts = form.value.participants
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
  const payload: Record<string, unknown> = {
    title: form.value.title.trim() || null,
    project: form.value.project.trim() || null,
    description: form.value.description.trim() || null,
    meeting_date: form.value.meetingDateLocal ? new Date(form.value.meetingDateLocal).toISOString() : null,
    participants: parts.length ? parts : null,
  }
  try {
    const updated = await api.patch<Job>(`/audio/jobs/${id.value}`, payload)
    job.value = updated
    editing.value = false
  } catch (e: unknown) {
    saveError.value = e instanceof Error ? e.message : 'save failed'
  } finally {
    saving.value = false
  }
}

async function download(fmt: string) {
  const url = `${useRuntimeConfig().public.apiBase}/audio/jobs/${id.value}/download/${fmt}`
  const res = await fetch(url, { headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {} })
  if (!res.ok) {
    error.value = `download failed (${res.status})`
    return
  }
  const blob = await res.blob()
  const link = document.createElement('a')
  const cd = res.headers.get('Content-Disposition') || ''
  const m = /filename="?([^"]+)"?/i.exec(cd)
  link.href = URL.createObjectURL(blob)
  link.download = m ? m[1] : `recording-${id.value}.${fmt}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(link.href)
}

onMounted(() => {
  fetchJob()
  timer = setInterval(() => {
    if (!job.value || ['completed','failed'].includes(job.value.status)) return
    fetchJob()
  }, 3000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

function humanSize(b: number) {
  const u = ['B','KB','MB','GB']; let i = 0; let n = b
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(1)} ${u[i]}`
}

function humanDuration(s: number) {
  s = Math.round(s)
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${ss}s`
  return `${ss}s`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}
</script>
