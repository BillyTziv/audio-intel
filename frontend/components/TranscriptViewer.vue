<template>
  <div>
    <nav class="flex border-b text-sm">
      <button v-for="t in tabs" :key="t.key" @click="active = t.key"
              :class="['px-4 py-2 -mb-px border-b-2',
                       active === t.key ? 'border-blue-600 text-blue-700 font-medium' : 'border-transparent text-slate-600 hover:text-slate-900']">
        {{ t.label }}
      </button>
    </nav>

    <div class="p-5 text-sm">
      <div v-if="active === 'summary'" class="space-y-4">
        <div v-if="transcript.summary">
          <h3 class="font-semibold mb-1">Summary</h3>
          <p class="whitespace-pre-wrap text-slate-800">{{ transcript.summary }}</p>
        </div>
        <div v-if="(transcript.key_points || []).length">
          <h3 class="font-semibold mb-1">Key Points</h3>
          <ul class="list-disc list-inside space-y-0.5">
            <li v-for="(k, i) in transcript.key_points" :key="i">{{ k }}</li>
          </ul>
        </div>
        <div v-if="(transcript.decisions || []).length">
          <h3 class="font-semibold mb-1">Decisions</h3>
          <ul class="list-disc list-inside space-y-0.5">
            <li v-for="(d, i) in transcript.decisions" :key="i">{{ d }}</li>
          </ul>
        </div>
        <div v-if="(transcript.action_items || []).length">
          <h3 class="font-semibold mb-1">Action Items</h3>
          <ul class="space-y-1">
            <li v-for="(a, i) in transcript.action_items" :key="i" class="bg-slate-50 border rounded p-2">
              <div class="font-medium">{{ taskOf(a) }}</div>
              <div class="text-xs text-slate-500">
                <span v-if="ownerOf(a)">owner: {{ ownerOf(a) }}</span>
                <span v-if="dueOf(a)" class="ml-3">due: {{ dueOf(a) }}</span>
              </div>
            </li>
          </ul>
        </div>
        <p v-if="!transcript.summary && !(transcript.key_points || []).length"
           class="text-slate-500">No summary generated. Set LLM_PROVIDER to ollama/openai/anthropic to enable.</p>
      </div>

      <div v-else-if="active === 'cleaned'" class="whitespace-pre-wrap leading-relaxed text-slate-800">
        {{ transcript.cleaned_text || transcript.raw_text || '(empty)' }}
      </div>

      <div v-else-if="active === 'raw'" class="whitespace-pre-wrap leading-relaxed text-slate-800">
        {{ transcript.raw_text || '(empty)' }}
      </div>

      <div v-else-if="active === 'segments'" class="space-y-1 max-h-[60vh] overflow-y-auto pr-2">
        <div v-if="(transcript.speakers || []).length" class="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span class="text-slate-500">Speakers:</span>
          <span v-for="sp in (transcript.speakers || [])" :key="String(sp)"
                :class="['inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-medium', speakerClass(String(sp))]">
            <span class="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
            {{ sp }}
          </span>
        </div>
        <div v-for="(seg, i) in (transcript.segments || [])" :key="i"
             class="grid grid-cols-[max-content_1fr] gap-3 py-1 border-b last:border-b-0">
          <span class="text-xs font-mono text-slate-500 whitespace-nowrap">
            {{ ts(seg.start) }} → {{ ts(seg.end) }}
          </span>
          <span class="text-slate-800">
            <span v-if="seg.speaker"
                  :class="['mr-2 inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold align-middle', speakerClass(seg.speaker)]">
              {{ seg.speaker }}
            </span>
            {{ seg.text }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  transcript: {
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
}>()

const tabs = [
  { key: 'summary',  label: 'Summary' },
  { key: 'cleaned',  label: 'Cleaned' },
  { key: 'raw',      label: 'Raw' },
  { key: 'segments', label: 'Segments' },
] as const

const active = ref<typeof tabs[number]['key']>('summary')

function taskOf(a: unknown): string {
  if (typeof a === 'string') return a
  if (a && typeof a === 'object' && 'task' in a) return String((a as Record<string, unknown>).task ?? '')
  return JSON.stringify(a)
}
function ownerOf(a: unknown): string | null {
  if (a && typeof a === 'object' && 'owner' in a) {
    const o = (a as Record<string, unknown>).owner
    return o ? String(o) : null
  }
  return null
}
function dueOf(a: unknown): string | null {
  if (a && typeof a === 'object' && 'due' in a) {
    const d = (a as Record<string, unknown>).due
    return d ? String(d) : null
  }
  return null
}

const speakerPalette = [
  'bg-sky-100 text-sky-800',
  'bg-emerald-100 text-emerald-800',
  'bg-amber-100 text-amber-800',
  'bg-violet-100 text-violet-800',
  'bg-rose-100 text-rose-800',
  'bg-teal-100 text-teal-800',
  'bg-fuchsia-100 text-fuchsia-800',
  'bg-lime-100 text-lime-800',
]

function speakerClass(label: string): string {
  let hash = 0
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) >>> 0
  return speakerPalette[hash % speakerPalette.length]
}

function ts(s: number) {
  s = Math.max(0, s)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  const ms = Math.round((s - Math.floor(s)) * 1000)
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(h)}:${pad(m)}:${pad(sec)}.${pad(ms, 3)}`
}
</script>
