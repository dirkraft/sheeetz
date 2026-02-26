<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSheet, getSheetPDF, getPdfMetadata, type SheetRecord } from '../api'
import * as pdfjsLib from 'pdfjs-dist'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

const route = useRoute()
const router = useRouter()

const sheet = ref<SheetRecord | null>(null)
const loading = ref(true)
const error = ref('')
const pageLeft = ref(1) // left page number (1-indexed)
const totalPages = ref(0)
const isFullscreen = ref(false)
const showMeta = ref(false)
const pdfMeta = ref<Record<string, string> | null>(null)
const metaLoading = ref(false)

const viewerRef = ref<HTMLElement | null>(null)
const pagesRef = ref<HTMLElement | null>(null)
const canvasLeftRef = ref<HTMLCanvasElement | null>(null)
const canvasRightRef = ref<HTMLCanvasElement | null>(null)

const coreFields = [
  { key: 'title', label: 'Title' },
  { key: 'composer', label: 'Composer' },
  { key: 'genre', label: 'Genre' },
  { key: 'key', label: 'Key' },
  { key: 'tags', label: 'Tags' },
  { key: 'pages', label: 'Pages' },
]

let pdfDoc: pdfjsLib.PDFDocumentProxy | null = null

async function renderPage(pageNum: number, canvas: HTMLCanvasElement) {
  if (!pdfDoc || pageNum < 1 || pageNum > totalPages.value) return
  const page = await pdfDoc.getPage(pageNum)
  const container = canvas.parentElement!
  const availHeight = container.clientHeight - 8 // small margin
  const viewport = page.getViewport({ scale: 1 })
  const scale = availHeight / viewport.height
  const scaledViewport = page.getViewport({ scale })

  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.floor(scaledViewport.width * dpr)
  canvas.height = Math.floor(scaledViewport.height * dpr)
  canvas.style.width = `${scaledViewport.width}px`
  canvas.style.height = `${scaledViewport.height}px`

  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)
  await page.render({ canvasContext: ctx, viewport: scaledViewport }).promise
}

async function renderSpread() {
  if (!pdfDoc) return
  const left = canvasLeftRef.value
  const right = canvasRightRef.value
  if (!left) return

  await renderPage(pageLeft.value, left)

  if (right && pageLeft.value + 1 <= totalPages.value) {
    right.style.display = ''
    await renderPage(pageLeft.value + 1, right)
  } else if (right) {
    right.style.display = 'none'
  }
}

function prevSpread() {
  if (pageLeft.value > 2) {
    pageLeft.value -= 2
  } else {
    pageLeft.value = 1
  }
}

function nextSpread() {
  if (pageLeft.value + 2 <= totalPages.value) {
    pageLeft.value += 2
  }
}

async function toggleFullscreen() {
  if (!viewerRef.value) return
  if (!document.fullscreenElement) {
    await viewerRef.value.requestFullscreen()
  } else {
    await document.exitFullscreen()
  }
}

function handlePagesClick(e: MouseEvent | TouchEvent) {
  const el = pagesRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const clientX = 'touches' in e ? e.changedTouches[0].clientX : e.clientX
  const midpoint = rect.left + rect.width / 2
  if (clientX < midpoint) {
    prevSpread()
  } else {
    nextSpread()
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  // Re-render after fullscreen change to fit new dimensions
  nextTick(() => setTimeout(renderSpread, 100))
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') { prevSpread(); e.preventDefault() }
  if (e.key === 'ArrowRight') { nextSpread(); e.preventDefault() }
  if (e.key === 'f' || e.key === 'F') { toggleFullscreen(); e.preventDefault() }
  if (e.key === 'Escape' && !document.fullscreenElement) {
    router.back()
  }
}

async function toggleMeta() {
  showMeta.value = !showMeta.value
  if (showMeta.value && !pdfMeta.value) {
    metaLoading.value = true
    try {
      const result = await getPdfMetadata(Number(route.params.id))
      pdfMeta.value = result.metadata
    } catch (e: any) {
      pdfMeta.value = { _error: e.message }
    } finally {
      metaLoading.value = false
    }
  }
  // Re-render since available width changed
  await nextTick()
  await renderSpread()
}

watch(pageLeft, renderSpread)

onMounted(async () => {
  const sheetId = Number(route.params.id)

  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)

  try {
    const [sheetData, pdfData] = await Promise.all([
      getSheet(sheetId),
      getSheetPDF(sheetId),
    ])
    sheet.value = sheetData

    pdfDoc = await pdfjsLib.getDocument({ data: pdfData }).promise
    totalPages.value = pdfDoc.numPages
    loading.value = false

    await nextTick()
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    await renderSpread()
  } catch (e: any) {
    error.value = e.message
    loading.value = false
  }
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  pdfDoc?.destroy()
})

window.addEventListener('resize', () => {
  renderSpread()
})
</script>

<template>
  <div ref="viewerRef" class="viewer" :class="{ fullscreen: isFullscreen }">
    <div v-if="loading" class="status">Loading...</div>
    <div v-else-if="error" class="status error">{{ error }}</div>
    <template v-else>
      <div class="toolbar">
        <button class="back-btn" @click="router.back()">Back</button>
        <span class="title">{{ sheet?.filename }}</span>
        <span class="page-info">
          {{ pageLeft }}{{ pageLeft + 1 <= totalPages ? '–' + (pageLeft + 1) : '' }}
          of {{ totalPages }}
        </span>
        <div class="toolbar-actions">
          <button :disabled="pageLeft <= 1" @click="prevSpread">Prev</button>
          <button :disabled="pageLeft + 2 > totalPages" @click="nextSpread">Next</button>
          <a
            v-if="sheet?.backend_type === 'gdrive'"
            :href="`https://drive.google.com/file/d/${sheet.backend_file_id}/view`"
            target="_blank"
            class="toolbar-link"
          >Drive</a>
          <button @click="toggleMeta" :class="{ active: showMeta }">Info</button>
          <button @click="toggleFullscreen">{{ isFullscreen ? 'Exit Fullscreen' : 'Fullscreen' }}</button>
        </div>
      </div>
      <div class="content-area">
        <div class="pages" ref="pagesRef" @click="handlePagesClick">
          <canvas ref="canvasLeftRef" class="page-canvas"></canvas>
          <canvas ref="canvasRightRef" class="page-canvas"></canvas>
        </div>
        <div v-if="showMeta" class="meta-panel">
          <!-- Indexed core fields -->
          <div class="meta-section">
            <h4 class="meta-heading">Sheet Info</h4>
            <div class="meta-fields">
              <div v-for="field in coreFields" :key="field.key" class="meta-field">
                <label>{{ field.label }}</label>
                <span class="meta-value">{{ sheet?.metadata?.[field.key] || '—' }}</span>
              </div>
            </div>
          </div>
          <!-- Raw PDF metadata -->
          <div class="meta-section">
            <h4 class="meta-heading">Raw PDF Metadata</h4>
            <div v-if="metaLoading" class="meta-loading">Loading metadata...</div>
            <template v-else-if="pdfMeta">
              <div v-if="Object.keys(pdfMeta).length === 0" class="meta-empty">No metadata found in this PDF.</div>
              <div v-else class="meta-fields">
                <div v-for="(value, key) in pdfMeta" :key="key" class="meta-field">
                  <label>{{ key }}</label>
                  <input type="text" :value="value" readonly class="readonly" />
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.viewer {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
  background: #2a2a2a;
}

.viewer.fullscreen {
  height: 100vh;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: #333;
  color: #eee;
  flex-shrink: 0;
}

.back-btn {
  background: none;
  border: 1px solid #666;
  color: #eee;
  border-radius: 4px;
  padding: 0.3rem 0.6rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.title {
  flex: 1;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.page-info {
  font-size: 0.85rem;
  color: #aaa;
  white-space: nowrap;
}

.toolbar-actions {
  display: flex;
  gap: 0.5rem;
}

.toolbar-actions button {
  background: #555;
  border: none;
  color: #eee;
  border-radius: 4px;
  padding: 0.3rem 0.7rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.toolbar-actions button:hover:not(:disabled) {
  background: #666;
}

.toolbar-actions button:disabled {
  opacity: 0.4;
  cursor: default;
}

.toolbar-link {
  background: #555;
  color: #eee;
  border-radius: 4px;
  padding: 0.3rem 0.7rem;
  font-size: 0.85rem;
  text-decoration: none;
}

.toolbar-link:hover {
  background: #666;
}

.content-area {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.pages {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  padding: 4px;
}

.page-canvas {
  max-height: 100%;
  object-fit: contain;
}

.status {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #aaa;
  font-size: 1.1rem;
}

.status.error {
  color: #ef5350;
}

.toolbar-actions button.active {
  background: #4285f4;
}

.meta-panel {
  width: 320px;
  flex-shrink: 0;
  background: #333;
  border-left: 1px solid #444;
  overflow-y: auto;
  padding: 1rem;
}

.meta-section {
  margin-bottom: 1.25rem;
}

.meta-heading {
  color: #ccc;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid #555;
}

.meta-loading {
  color: #aaa;
  font-size: 0.9rem;
}

.meta-empty {
  color: #888;
  font-size: 0.9rem;
}

.meta-fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.meta-field label {
  display: block;
  font-size: 0.75rem;
  color: #aaa;
  margin-bottom: 0.2rem;
  word-break: break-all;
}

.meta-value {
  display: block;
  color: #eee;
  font-size: 0.85rem;
  padding: 0.2rem 0;
}

.meta-field input {
  width: 100%;
  padding: 0.35rem 0.5rem;
  background: #444;
  border: 1px solid #555;
  border-radius: 4px;
  color: #bbb;
  font-size: 0.85rem;
  box-sizing: border-box;
}
</style>
