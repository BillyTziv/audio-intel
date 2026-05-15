<template>
  <div>
    <div v-if="!supported" class="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3">
      Your browser doesn't support in-page recording. Switch to the Upload tab.
    </div>

    <template v-else>
      <div class="flex flex-wrap items-center gap-3">
        <button v-if="!recording" :disabled="uploading" @click="start"
                class="inline-flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded font-medium hover:bg-red-700 disabled:opacity-60">
          <span class="h-2.5 w-2.5 rounded-full bg-white" /> Record
        </button>
        <button v-else @click="stop"
                class="inline-flex items-center gap-2 bg-slate-700 text-white px-4 py-2 rounded font-medium hover:bg-slate-800">
          <span class="h-2.5 w-2.5 bg-white" /> Stop
        </button>

        <span v-if="recording" class="font-mono text-sm text-slate-700 flex items-center gap-1.5">
          <span class="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          {{ elapsedText }}
        </span>
        <span v-if="uploading" class="text-sm text-slate-500">Uploading {{ pct }}%…</span>
      </div>

      <div v-if="recording" class="mt-3 h-2 bg-slate-200 rounded overflow-hidden">
        <div class="h-2 bg-red-500" :style="{ width: `${level}%` }" />
      </div>

      <label class="mt-2 inline-flex items-center gap-2 text-sm text-slate-700 select-none">
        <input type="checkbox" v-model="diarize" :disabled="recording || uploading"
               class="h-4 w-4 rounded border-slate-300" />
        <span>Identify speakers (diarization)</span>
        <span class="text-xs text-slate-500">— slower, separates who said what</span>
      </label>

      <p v-if="error" class="text-sm text-red-600 mt-2">{{ error }}</p>
      <p v-else class="text-xs text-slate-500 mt-2">
        Records your microphone + the shared tab/screen audio, mixed into one track ({{ mimeLabel || 'browser default codec' }}). In Chrome's share dialog tick "Share tab audio" (or "Share system audio" if you share the whole screen).
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{ (e: 'uploaded', jobId: string): void }>()
const config = useRuntimeConfig()
const auth = useAuthStore()

const supported = ref(false)
const recording = ref(false)
const uploading = ref(false)
const pct = ref(0)
const elapsed = ref(0)
const level = ref(0)
const error = ref<string | null>(null)
const mimeLabel = ref('')
const diarize = ref(false)

let micStream: MediaStream | null = null
let sysStream: MediaStream | null = null
let mixedStream: MediaStream | null = null
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let audioCtx: AudioContext | null = null
let analyser: AnalyserNode | null = null
let raf: number | null = null
let timer: ReturnType<typeof setInterval> | null = null
let mimeType = ''
let startedAt = 0

onMounted(() => {
  supported.value =
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
})

onBeforeUnmount(() => cleanup())

function pad(n: number) { return String(n).padStart(2, '0') }

function pickMime(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4;codecs=mp4a.40.2',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ]
  for (const c of candidates) {
    if (typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(c)) return c
  }
  return ''
}

function extFor(mime: string): string {
  if (mime.startsWith('audio/webm')) return 'webm'
  if (mime.startsWith('audio/mp4')) return 'mp4'
  if (mime.startsWith('audio/ogg')) return 'ogg'
  return 'webm'
}

async function start() {
  error.value = null
  chunks = []
  elapsed.value = 0
  level.value = 0

  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
  } catch (e) {
    error.value = e instanceof Error && e.name === 'NotAllowedError'
      ? 'Microphone permission denied. Allow access in browser settings and retry.'
      : 'Could not access microphone.'
    return
  }

  try {
    sysStream = await navigator.mediaDevices.getDisplayMedia({
      audio: true,
      video: true,
    })
  } catch (e) {
    cleanup()
    error.value = e instanceof Error && e.name === 'NotAllowedError'
      ? 'Screen/tab share was cancelled. To record the other side of the call, share the meeting tab and tick "Share tab audio".'
      : 'Could not capture system audio.'
    return
  }

  if (sysStream.getAudioTracks().length === 0) {
    cleanup()
    error.value = 'No audio was shared. Re-share the tab/screen and tick "Share tab audio" (or "Share system audio" for whole screen).'
    return
  }

  sysStream.getVideoTracks().forEach(t => t.stop())
  sysStream.getAudioTracks()[0].addEventListener('ended', () => {
    if (recorder && recorder.state !== 'inactive') recorder.stop()
  })

  try {
    audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    const dest = audioCtx.createMediaStreamDestination()
    const micSrc = audioCtx.createMediaStreamSource(micStream)
    const sysSrc = audioCtx.createMediaStreamSource(sysStream)
    micSrc.connect(dest)
    sysSrc.connect(dest)
    mixedStream = dest.stream

    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 256
    micSrc.connect(analyser)
    sysSrc.connect(analyser)
    drawLevel()
  } catch (e) {
    cleanup()
    error.value = 'Could not mix microphone and system audio.'
    return
  }

  mimeType = pickMime()
  if (!mimeType) {
    error.value = 'No supported audio codec in this browser.'
    cleanup()
    return
  }
  mimeLabel.value = mimeType

  try {
    recorder = new MediaRecorder(mixedStream, { mimeType, audioBitsPerSecond: 96000 })
  } catch (_) {
    recorder = new MediaRecorder(mixedStream)
    mimeType = recorder.mimeType || mimeType
    mimeLabel.value = mimeType
  }

  recorder.ondataavailable = (ev) => {
    if (ev.data && ev.data.size > 0) chunks.push(ev.data)
  }
  recorder.onstop = onStop
  recorder.start(1000)

  startedAt = Date.now()
  timer = setInterval(() => { elapsed.value = Math.floor((Date.now() - startedAt) / 1000) }, 250)
  recording.value = true
}

function drawLevel() {
  if (!analyser) return
  const data = new Uint8Array(analyser.frequencyBinCount)
  analyser.getByteFrequencyData(data)
  let sum = 0
  for (const v of data) sum += v
  const avg = sum / data.length
  level.value = Math.min(100, Math.round((avg / 180) * 100))
  raf = requestAnimationFrame(drawLevel)
}

function stop() {
  if (recorder && recorder.state !== 'inactive') recorder.stop()
}

function cleanup() {
  if (raf !== null) { cancelAnimationFrame(raf); raf = null }
  if (timer) { clearInterval(timer); timer = null }
  if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null }
  analyser = null
  if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null }
  if (sysStream) { sysStream.getTracks().forEach(t => t.stop()); sysStream = null }
  mixedStream = null
  recorder = null
}

async function onStop() {
  recording.value = false
  const blobs = chunks.slice()
  cleanup()

  if (blobs.length === 0) {
    error.value = 'No audio captured.'
    return
  }
  const blob = new Blob(blobs, { type: mimeType })
  if (blob.size < 1024) {
    error.value = 'Recording too short.'
    return
  }
  const ext = extFor(mimeType)
  const now = new Date()
  const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`
  const filename = `recording-${ts}.${ext}`
  await upload(blob, filename)
}

function upload(blob: Blob, filename: string): Promise<void> {
  uploading.value = true
  pct.value = 0
  const form = new FormData()
  form.append('file', new File([blob], filename, { type: blob.type }))
  form.append('diarize', diarize.value ? 'true' : 'false')

  return new Promise<void>((resolve) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${config.public.apiBase}/audio/upload`)
    if (auth.token) xhr.setRequestHeader('Authorization', `Bearer ${auth.token}`)

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) pct.value = Math.round((ev.loaded / ev.total) * 100)
    }
    xhr.onerror = () => {
      uploading.value = false
      error.value = 'Upload failed (network error).'
      resolve()
    }
    xhr.onload = () => {
      uploading.value = false
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText)
          emit('uploaded', data.job_id)
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
      resolve()
    }
    xhr.send(form)
  })
}

const elapsedText = computed(() => {
  const m = Math.floor(elapsed.value / 60)
  const s = elapsed.value % 60
  return `${pad(m)}:${pad(s)}`
})
</script>
