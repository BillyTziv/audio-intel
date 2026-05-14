<template>
  <section class="bg-white border rounded-xl shadow-sm">
    <header class="flex items-center justify-between px-5 py-3 border-b">
      <h2 class="text-lg font-semibold">Jobs</h2>
      <button class="text-sm text-blue-600 hover:underline" @click="refresh">Refresh</button>
    </header>
    <div v-if="error" class="px-5 py-4 text-sm text-red-600">{{ error }}</div>
    <div v-else-if="loading && !items.length" class="px-5 py-6 text-sm text-slate-500">Loading…</div>
    <div v-else-if="!items.length" class="px-5 py-8 text-sm text-slate-500">No jobs yet — upload a file above.</div>
    <ul v-else class="divide-y">
      <li v-for="job in items" :key="job.id" class="px-5 py-3 flex items-center gap-3 hover:bg-slate-50">
        <div class="flex-1 min-w-0">
          <NuxtLink :to="`/jobs/${job.id}`" class="font-medium text-slate-900 hover:underline truncate block">
            {{ job.original_filename }}
          </NuxtLink>
          <div class="text-xs text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
            <span>{{ humanSize(job.size_bytes) }}</span>
            <span v-if="job.duration_seconds">{{ humanDuration(job.duration_seconds) }}</span>
            <span>{{ formatDate(job.created_at) }}</span>
          </div>
        </div>
        <div class="w-32">
          <div v-if="job.status !== 'completed' && job.status !== 'failed'" class="h-1.5 bg-slate-200 rounded">
            <div class="h-1.5 bg-blue-500 rounded transition-all" :style="{ width: `${Math.round((job.progress || 0) * 100)}%` }" />
          </div>
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
}

const api = useApi()
const items = ref<Job[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

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
