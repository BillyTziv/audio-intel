<template>
  <span :class="['inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium', cls]">
    <span :class="['h-1.5 w-1.5 rounded-full', dotCls]" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{ status: string }>()

const map: Record<string, { cls: string; dotCls: string; label: string }> = {
  pending:      { cls: 'bg-slate-100 text-slate-700',     dotCls: 'bg-slate-400',  label: 'pending' },
  queued:       { cls: 'bg-slate-100 text-slate-700',     dotCls: 'bg-slate-400',  label: 'queued' },
  validating:   { cls: 'bg-amber-100 text-amber-800',     dotCls: 'bg-amber-500',  label: 'validating' },
  converting:   { cls: 'bg-amber-100 text-amber-800',     dotCls: 'bg-amber-500',  label: 'converting' },
  chunking:     { cls: 'bg-amber-100 text-amber-800',     dotCls: 'bg-amber-500',  label: 'chunking' },
  transcribing: { cls: 'bg-blue-100 text-blue-800',       dotCls: 'bg-blue-500',   label: 'transcribing' },
  summarizing:  { cls: 'bg-indigo-100 text-indigo-800',   dotCls: 'bg-indigo-500', label: 'summarizing' },
  completed:    { cls: 'bg-emerald-100 text-emerald-800', dotCls: 'bg-emerald-500',label: 'completed' },
  failed:       { cls: 'bg-red-100 text-red-800',         dotCls: 'bg-red-500',    label: 'failed' },
}

const entry = computed(() => map[props.status] || map.pending)
const cls = computed(() => entry.value.cls)
const dotCls = computed(() => entry.value.dotCls)
const label = computed(() => entry.value.label)
</script>
