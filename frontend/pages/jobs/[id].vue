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
            <h1 class="text-xl font-semibold truncate">{{ job.original_filename }}</h1>
            <div class="text-sm text-slate-500 mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
              <span>{{ humanSize(job.size_bytes) }}</span>
              <span v-if="job.duration_seconds">{{ humanDuration(job.duration_seconds) }}</span>
              <span>created {{ formatDate(job.created_at) }}</span>
              <span v-if="job.completed_at">finished {{ formatDate(job.completed_at) }}</span>
            </div>
          </div>
          <JobStatusBadge :status="job.status" />
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
}

interface Transcript {
  language: string | null
  raw_text: string | null
  cleaned_text: string | null
  summary: string | null
  key_points: unknown[] | null
  decisions: unknown[] | null
  action_items: unknown[] | null
  segments: { start: number; end: number; text: string }[] | null
}

const route = useRoute()
const api = useApi()
const auth = useAuthStore()
const id = computed(() => String(route.params.id))

const job = ref<Job | null>(null)
const transcript = ref<Transcript | null>(null)
const error = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function fetchJob() {
  try {
    job.value = await api.get<Job>(`/audio/jobs/${id.value}`)
    if (job.value.status === 'completed' && !transcript.value) {
      try {
        transcript.value = await api.get<Transcript>(`/audio/jobs/${id.value}/transcript`)
      } catch (_) { /* not ready */ }
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'failed to load job'
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
  link.download = m ? m[1] : `job-${id.value}.${fmt}`
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
