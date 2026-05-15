<template>
  <section class="bg-white border rounded-xl shadow-sm">
    <header class="flex items-center justify-between px-5 py-3 border-b">
      <h2 class="text-lg font-semibold">Recordings</h2>
      <button class="text-sm text-blue-600 hover:underline" @click="refresh">Refresh</button>
    </header>
    <div v-if="error" class="px-5 py-4 text-sm text-red-600">{{ error }}</div>
    <div v-else-if="loading && !items.length" class="px-5 py-6 text-sm text-slate-500">Loading…</div>
    <div v-else-if="!items.length" class="px-5 py-8 text-sm text-slate-500">No recordings yet — record or upload above to get started.</div>
    <ul v-else class="divide-y">
      <li v-for="job in items" :key="job.id" class="px-5 py-3 flex items-center gap-3 hover:bg-slate-50">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <NuxtLink :to="`/jobs/${job.id}`" class="font-medium text-slate-900 hover:underline truncate">
              {{ job.title || job.original_filename }}
            </NuxtLink>
            <span v-if="job.project"
                  class="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5 whitespace-nowrap">
              {{ job.project }}
            </span>
          </div>
          <div class="text-xs text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
            <span v-if="job.title" class="truncate max-w-xs">{{ job.original_filename }}</span>
            <span>{{ humanSize(job.size_bytes) }}</span>
            <span v-if="job.duration_seconds">{{ humanDuration(job.duration_seconds) }}</span>
            <span>{{ formatDate(job.meeting_date || job.created_at) }}</span>
            <span v-if="job.participants && job.participants.length" class="truncate max-w-xs">
              · {{ job.participants.join(', ') }}
            </span>
          </div>
        </div>
        <div class="w-32">
          <template v-if="job.status !== 'completed' && job.status !== 'failed'">
            <div class="h-1.5 bg-slate-200 rounded">
              <div class="h-1.5 bg-blue-500 rounded transition-all" :style="{ width: `${Math.round((job.progress || 0) * 100)}%` }" />
            </div>
            <div class="mt-1 text-[11px] text-slate-500 text-right tabular-nums">
              {{ etaFor(job) || '' }}
            </div>
          </template>
        </div>
        <JobStatusBadge :status="job.status" />
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import JobStatusBadge from '~/components/JobStatusBadge.vue'

interface Job {
  id: string
  original_filename: string
  size_bytes: number
  duration_seconds: number | null
  status: string
  progress: number
  created_at: string
  started_at: string | null
  title: string | null
  project: string | null
  meeting_date: string | null
  participants: string[] | null
}

const api = useApi()
const items = ref<Job[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
let nowTimer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const data = await api.get<{ items: Job[]; total: number }>('/audio/jobs?limit=100')
    items.value = data.items
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'failed to load jobs'
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh })

onMounted(() => {
  refresh()
  timer = setInterval(() => {
    const inFlight = items.value.some(j => !['completed','failed'].includes(j.status))
    if (inFlight || items.value.length === 0) refresh()
  }, 3000)
  nowTimer = setInterval(() => { now.value = Date.now() }, 1000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (nowTimer) clearInterval(nowTimer)
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

function etaFor(job: Job): string | null {
  if (['completed', 'failed'].includes(job.status)) return null
  if (!job.started_at) return 'queued'
  const p = job.progress || 0
  if (p < 0.15) return 'loading model…'
  if (p >= 1) return null
  const elapsedMs = now.value - new Date(job.started_at).getTime()
  if (elapsedMs <= 0) return null
  const remainingSec = (elapsedMs / 1000) * (1 - p) / p
  if (!isFinite(remainingSec) || remainingSec <= 0) return null
  return `~${humanDuration(remainingSec)} left`
}
</script>
