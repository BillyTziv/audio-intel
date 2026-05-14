<template>
  <div class="space-y-6">
    <UploadForm @uploaded="onUploaded" />
    <JobList ref="jobListRef" />
  </div>
</template>

<script setup lang="ts">
import UploadForm from '~/components/UploadForm.vue'
import JobList from '~/components/JobList.vue'

const jobListRef = ref<InstanceType<typeof JobList> | null>(null)

function onUploaded() {
  jobListRef.value?.refresh()
}
</script>
