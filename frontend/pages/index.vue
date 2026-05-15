<template>
  <div class="space-y-6">
    <section class="bg-white border rounded-xl shadow-sm overflow-hidden">
      <div class="flex border-b">
        <button
          v-for="t in tabs" :key="t.id"
          @click="active = t.id"
          :class="[
            'flex-1 px-5 py-3 text-sm font-medium transition-colors',
            active === t.id
              ? 'text-blue-600 border-b-2 border-blue-600 bg-white'
              : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50 border-b-2 border-transparent'
          ]"
        >
          {{ t.label }}
        </button>
      </div>
      <div class="p-5">
        <Recorder v-show="active === 'record'" @uploaded="onUploaded" />
        <UploadForm v-show="active === 'upload'" @uploaded="onUploaded" />
      </div>
    </section>
    <JobList ref="jobListRef" />
  </div>
</template>

<script setup lang="ts">
import Recorder from '~/components/Recorder.vue'
import UploadForm from '~/components/UploadForm.vue'
import JobList from '~/components/JobList.vue'

const tabs = [
  { id: 'record', label: 'Record' },
  { id: 'upload', label: 'Upload' },
] as const
const active = ref<typeof tabs[number]['id']>('record')

const jobListRef = ref<InstanceType<typeof JobList> | null>(null)

function onUploaded() {
  jobListRef.value?.refresh()
}
</script>
