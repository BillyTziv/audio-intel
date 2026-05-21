<template>
  <div class="space-y-6">
    <section class="bg-white border rounded-xl shadow-sm">
      <header class="px-5 py-3 border-b flex items-center justify-between">
        <h2 class="text-lg font-semibold">Microsoft Teams</h2>
        <div class="text-xs text-slate-500">Import meeting recordings &amp; transcripts via Microsoft Graph</div>
      </header>

      <div class="p-5 space-y-4">
        <div v-if="banner" :class="bannerClass" class="rounded border px-3 py-2 text-sm">{{ banner }}</div>

        <div v-if="statusLoading" class="text-sm text-slate-500">Checking connection…</div>

        <div v-else-if="status?.connected" class="flex items-center justify-between gap-4">
          <div class="text-sm">
            <div class="font-medium text-slate-900">
              Connected as {{ status.ms_display_name || status.ms_user_principal_name }}
            </div>
            <div class="text-slate-500 text-xs">
              <span v-if="status.ms_user_principal_name">{{ status.ms_user_principal_name }}</span>
              <span v-if="status.token_expires_at"> · token expires {{ formatDate(status.token_expires_at) }}</span>
            </div>
          </div>
          <button
            class="text-sm bg-slate-100 hover:bg-slate-200 text-slate-800 rounded px-3 py-1.5 disabled:opacity-60"
            :disabled="disconnecting"
            @click="disconnect"
          >
            {{ disconnecting ? 'Disconnecting…' : 'Disconnect' }}
          </button>
        </div>

        <div v-else class="flex items-center justify-between gap-4">
          <div class="text-sm text-slate-600">Not connected. Sign in with your Microsoft work account to import meetings.</div>
          <button
            class="bg-blue-600 hover:bg-blue-700 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-60"
            :disabled="connecting"
            @click="connect"
          >
            {{ connecting ? 'Redirecting…' : 'Connect Microsoft account' }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="status?.connected" class="bg-white border rounded-xl shadow-sm">
      <header class="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h2 class="text-lg font-semibold">Recent meetings</h2>
        <div class="flex items-center gap-2">
          <label class="text-xs text-slate-500">Days</label>
          <select v-model.number="days" class="border rounded text-sm px-2 py-1">
            <option :value="7">7</option>
            <option :value="30">30</option>
            <option :value="90">90</option>
            <option :value="180">180</option>
          </select>
          <button class="text-sm text-blue-600 hover:underline" @click="loadMeetings">Refresh</button>
        </div>
      </header>

      <div v-if="meetingsError" class="px-5 py-4 text-sm text-red-600">{{ meetingsError }}</div>
      <div v-else-if="meetingsLoading && !meetings.length" class="px-5 py-6 text-sm text-slate-500">Loading meetings…</div>
      <div v-else-if="!meetings.length" class="px-5 py-8 text-sm text-slate-500">
        No Teams meetings found in this window. Try widening the date range, or paste a join URL below.
      </div>
      <ul v-else class="divide-y">
        <li v-for="m in meetings" :key="m.event_id" class="px-5 py-3 flex items-start gap-3">
          <div class="flex-1 min-w-0">
            <div class="font-medium text-slate-900 truncate">{{ m.subject || '(no subject)' }}</div>
            <div class="text-xs text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
              <span>{{ formatDate(m.start) }}</span>
              <span v-if="m.organizer">· {{ m.organizer }}</span>
              <span v-if="m.attendees && m.attendees.length" class="truncate max-w-md">· {{ m.attendees.join(', ') }}</span>
            </div>
          </div>
          <button
            class="text-sm bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-1.5 disabled:opacity-60 whitespace-nowrap"
            :disabled="!m.join_url || importingId === m.event_id"
            @click="importMeeting(m.join_url, m.subject || undefined, m.event_id)"
          >
            {{ importingId === m.event_id ? 'Importing…' : 'Import' }}
          </button>
        </li>
      </ul>
    </section>

    <section v-if="status?.connected" class="bg-white border rounded-xl shadow-sm">
      <header class="px-5 py-3 border-b">
        <h2 class="text-lg font-semibold">Import by join URL</h2>
      </header>
      <form class="p-5 space-y-3" @submit.prevent="importFromInput">
        <input
          v-model="joinUrl"
          type="url"
          required
          placeholder="https://teams.microsoft.com/l/meetup-join/..."
          class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            v-model="customTitle"
            type="text"
            placeholder="Title (optional)"
            class="border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            v-model="customProject"
            type="text"
            placeholder="Project (optional)"
            class="border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <label class="flex items-center gap-2 text-sm text-slate-700">
          <input v-model="diarize" type="checkbox" class="rounded" />
          Enable speaker diarization
        </label>
        <div class="flex items-center gap-3">
          <button
            type="submit"
            :disabled="!joinUrl || importingId === 'manual'"
            class="bg-blue-600 hover:bg-blue-700 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-60"
          >
            {{ importingId === 'manual' ? 'Importing…' : 'Import meeting' }}
          </button>
          <p v-if="lastImportSummary" class="text-xs text-slate-500">{{ lastImportSummary }}</p>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
interface TeamsStatus {
  connected: boolean
  ms_display_name?: string | null
  ms_user_principal_name?: string | null
  token_expires_at?: string | null
}

interface MeetingItem {
  event_id: string
  subject: string | null
  start: string | null
  end: string | null
  organizer: string | null
  join_url: string
  web_link: string | null
  attendees: string[]
}

interface ImportResponse {
  job_id: string
  status: string
  recording_downloaded: boolean
  transcript_imported: boolean
  attendance_imported: boolean
  notes: string[]
}

const api = useApi()
const router = useRouter()
const route = useRoute()

const status = ref<TeamsStatus | null>(null)
const statusLoading = ref(true)
const connecting = ref(false)
const disconnecting = ref(false)

const days = ref(30)
const meetings = ref<MeetingItem[]>([])
const meetingsLoading = ref(false)
const meetingsError = ref<string | null>(null)

const joinUrl = ref('')
const customTitle = ref('')
const customProject = ref('')
const diarize = ref(false)
const importingId = ref<string | null>(null)
const lastImportSummary = ref<string | null>(null)

const banner = ref<string | null>(null)
const bannerKind = ref<'info' | 'success' | 'error'>('info')
const bannerClass = computed(() => {
  if (bannerKind.value === 'success') return 'bg-green-50 border-green-200 text-green-800'
  if (bannerKind.value === 'error') return 'bg-red-50 border-red-200 text-red-700'
  return 'bg-slate-50 border-slate-200 text-slate-700'
})

function setBanner(msg: string, kind: 'info' | 'success' | 'error' = 'info') {
  banner.value = msg
  bannerKind.value = kind
}

function formatDate(iso?: string | null) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

async function loadStatus() {
  statusLoading.value = true
  try {
    status.value = await api.get<TeamsStatus>('/teams/auth/status')
  } catch (e) {
    status.value = { connected: false }
    setBanner(e instanceof Error ? e.message : 'failed to load Teams status', 'error')
  } finally {
    statusLoading.value = false
  }
}

async function connect() {
  connecting.value = true
  try {
    const data = await api.get<{ authorize_url: string; state: string }>('/teams/auth/start')
    window.location.href = data.authorize_url
  } catch (e) {
    setBanner(e instanceof Error ? e.message : 'failed to start Microsoft sign-in', 'error')
    connecting.value = false
  }
}

async function disconnect() {
  if (!confirm('Disconnect the Microsoft account? You will need to sign in again to import more meetings.')) return
  disconnecting.value = true
  try {
    await api.del('/teams/auth')
    status.value = { connected: false }
    meetings.value = []
    setBanner('Microsoft account disconnected.', 'info')
  } catch (e) {
    setBanner(e instanceof Error ? e.message : 'failed to disconnect', 'error')
  } finally {
    disconnecting.value = false
  }
}

async function loadMeetings() {
  meetingsLoading.value = true
  meetingsError.value = null
  try {
    const data = await api.get<{ items: MeetingItem[] }>(`/teams/meetings?days=${days.value}`)
    meetings.value = data.items
  } catch (e) {
    meetingsError.value = e instanceof Error ? e.message : 'failed to load meetings'
  } finally {
    meetingsLoading.value = false
  }
}

async function importMeeting(url: string, title: string | undefined, key: string) {
  importingId.value = key
  lastImportSummary.value = null
  try {
    const body: Record<string, unknown> = { join_url: url, diarize: diarize.value }
    if (title) body.title = title
    const res = await api.post<ImportResponse>('/teams/meetings/import', body)
    summarizeImport(res)
    setBanner(`Import queued (job ${res.job_id.slice(0, 8)}…). You can follow it on the home page.`, 'success')
    await router.push(`/jobs/${res.job_id}`)
  } catch (e) {
    setBanner(e instanceof Error ? e.message : 'import failed', 'error')
  } finally {
    importingId.value = null
  }
}

async function importFromInput() {
  if (!joinUrl.value) return
  importingId.value = 'manual'
  lastImportSummary.value = null
  try {
    const body: Record<string, unknown> = {
      join_url: joinUrl.value.trim(),
      diarize: diarize.value,
    }
    if (customTitle.value) body.title = customTitle.value
    if (customProject.value) body.project = customProject.value
    const res = await api.post<ImportResponse>('/teams/meetings/import', body)
    summarizeImport(res)
    setBanner(`Import queued (job ${res.job_id.slice(0, 8)}…).`, 'success')
    await router.push(`/jobs/${res.job_id}`)
  } catch (e) {
    setBanner(e instanceof Error ? e.message : 'import failed', 'error')
  } finally {
    importingId.value = null
  }
}

function summarizeImport(res: ImportResponse) {
  const parts: string[] = []
  parts.push(res.recording_downloaded ? 'recording downloaded' : 'no recording')
  parts.push(res.transcript_imported ? 'Teams transcript imported' : 'no Teams transcript')
  parts.push(res.attendance_imported ? 'attendance imported' : 'no attendance report')
  if (res.notes && res.notes.length) parts.push(`notes: ${res.notes.join('; ')}`)
  lastImportSummary.value = parts.join(' · ')
}

onMounted(async () => {
  const q = route.query
  if (q.ms_status === 'connected') {
    setBanner('Microsoft account connected.', 'success')
  } else if (q.ms_status === 'error') {
    const reason = typeof q.reason === 'string' ? q.reason : 'unknown error'
    setBanner(`Microsoft sign-in failed: ${reason}`, 'error')
  }
  if (q.ms_status) {
    await router.replace({ path: route.path, query: {} })
  }
  await loadStatus()
  if (status.value?.connected) {
    await loadMeetings()
  }
})

watch(days, () => {
  if (status.value?.connected) loadMeetings()
})
</script>
