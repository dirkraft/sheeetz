<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getSheet, getSheetPDF, getPdfMetadata, updateSheetMetadata, getMetadataValues, getMetadataKeys,
  getSelectedFolders, type SheetRecord, type LibraryFolder,
} from '../api'
import AutocompleteInput from '../components/AutocompleteInput.vue'
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
const showMeta = ref(true)
const pdfMeta = ref<Record<string, string> | null>(null)
const metaLoading = ref(false)
const folders = ref<LibraryFolder[]>([])

const viewerRef = ref<HTMLElement | null>(null)
const pagesRef = ref<HTMLElement | null>(null)
const canvasLeftRef = ref<HTMLCanvasElement | null>(null)
const canvasRightRef = ref<HTMLCanvasElement | null>(null)

const editableFields = [
  { key: 'title', label: 'Title' },
  { key: 'composer', label: 'Composer' },
  { key: 'tags', label: 'Tags' },
]

const coreFields = [
  ...editableFields,
  { key: 'pages', label: 'Pages' },
]

// Editable form state
const editForm = reactive<Record<string, string>>({
  title: '',
  composer: '',
  tags: '',
})
const customFields = ref<Array<{ key: string; value: string }>>([])
const removedCustomKeys = ref<Set<string>>(new Set())
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref(false)

const coreKeySet = new Set([...editableFields.map(f => f.key), 'pages'])

function sheetFolderName(s: SheetRecord | null) {
  if (!s) return 'Unknown'
  const folder = folders.value.find((f) => f.id === s.library_folder_id)
  return folder?.folder_name || 'Unknown'
}

function relativeFolderPath(s: SheetRecord | null) {
  if (!s) return ''
  const raw = s.folder_path || ''
  if (!raw) return ''
  const folder = folders.value.find((f) => f.id === s.library_folder_id)
  if (!folder) return raw

  const base = folder.folder_path.replace(/\/+$/, '')
  if (!base) return raw
  if (raw === base) return ''
  if (raw.startsWith(`${base}/`)) return raw.slice(base.length + 1)
  return raw
}

function relativeFilePath(s: SheetRecord | null) {
  if (!s) return ''
  const relDir = relativeFolderPath(s)
  return relDir ? `${relDir}/${s.filename}` : s.filename
}


function populateEditForm(metadata: Record<string, string>) {
  for (const field of editableFields) {
    editForm[field.key] = metadata[field.key] || ''
  }
  // Populate custom fields from metadata keys not in core set
  customFields.value = Object.entries(metadata)
    .filter(([k]) => !coreKeySet.has(k))
    .map(([k, v]) => ({ key: k, value: v }))
  removedCustomKeys.value = new Set()
}

function addCustomField() {
  customFields.value.push({ key: '', value: '' })
}

function removeCustomField(index: number) {
  const key = customFields.value[index].key.trim()
  if (key) removedCustomKeys.value.add(key)
  customFields.value.splice(index, 1)
}

async function saveMetadata() {
  if (!sheet.value) return
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    // Merge core fields and custom fields into one payload
    const payload: Record<string, string> = { ...editForm }
    for (const cf of customFields.value) {
      const k = cf.key.trim()
      if (!k) continue
      payload[k] = cf.value
    }
    // Send removed keys as "" so backend clears them from PDF XMP
    for (const k of removedCustomKeys.value) {
      if (!(k in payload)) payload[k] = ''
    }
    const result = await updateSheetMetadata(sheet.value.id, payload)
    // Update local sheet metadata and re-populate forms
    sheet.value.metadata = result.metadata
    populateEditForm(result.metadata)
    saveSuccess.value = true
    // Re-fetch raw metadata to reflect changes
    try {
      const rawResult = await getPdfMetadata(sheet.value.id)
      pdfMeta.value = rawResult.metadata
    } catch {
      // Non-critical — raw section will show stale data
    }
    setTimeout(() => { saveSuccess.value = false }, 2000)
  } catch (e: any) {
    saveError.value = e.message
  } finally {
    saving.value = false
  }
}

let pdfDoc: pdfjsLib.PDFDocumentProxy | null = null

// Render generation counter — incremented every time renderSpread() starts so
// that any in-flight async render that was launched for a previous generation
// knows to abort rather than write stale pixels to the canvas.
let renderGen = 0

// Active pdfjs render tasks keyed by canvas identity so we can cancel them
// before starting a new render on the same canvas.
const activeRenderTasks = new Map<HTMLCanvasElement, pdfjsLib.RenderTask>()

// Page cache for pre-rendered bitmaps
interface CachedPage {
  bitmap: ImageBitmap
  cssWidth: string
  cssHeight: string
  pixelWidth: number
  pixelHeight: number
}
const pageCache = new Map<number, CachedPage>()
const PAGE_CACHE_MAX = 20

function evictCacheIfNeeded() {
  while (pageCache.size >= PAGE_CACHE_MAX) {
    const oldest = pageCache.keys().next().value
    const entry = pageCache.get(oldest!)
    if (entry) entry.bitmap.close()
    pageCache.delete(oldest!)
  }
}

function clearPageCache() {
  for (const entry of pageCache.values()) {
    entry.bitmap.close()
  }
  pageCache.clear()
}

function getRenderScale(
  viewport: pdfjsLib.PageViewport,
  container: HTMLElement,
  visiblePages: number,
) {
  const styles = getComputedStyle(container)
  const gap = parseFloat(styles.gap || '0') || 0
  const paddingX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0)
  const paddingY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0)
  const totalWidth = Math.max(container.clientWidth - paddingX - gap * Math.max(visiblePages - 1, 0), 1)
  const perPageWidth = Math.max(totalWidth / Math.max(visiblePages, 1), 1)
  const totalHeight = Math.max(container.clientHeight - paddingY, 1)

  const scaleByWidth = perPageWidth / viewport.width
  const scaleByHeight = totalHeight / viewport.height
  return Math.max(Math.min(scaleByWidth, scaleByHeight), 0.01)
}

async function renderPage(
  pageNum: number,
  canvas: HTMLCanvasElement,
  visiblePages: number,
  gen: number,
) {
  if (!pdfDoc || pageNum < 1 || pageNum > totalPages.value) return

  const cached = pageCache.get(pageNum)
  if (cached) {
    if (gen !== renderGen) return // stale — a newer render has already started
    canvas.width = cached.pixelWidth
    canvas.height = cached.pixelHeight
    canvas.style.width = cached.cssWidth
    canvas.style.height = cached.cssHeight
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(cached.bitmap, 0, 0)
    return
  }

  // Cancel any previous in-flight pdfjs render task on this canvas.
  const prevTask = activeRenderTasks.get(canvas)
  if (prevTask) {
    prevTask.cancel()
    activeRenderTasks.delete(canvas)
  }

  if (gen !== renderGen) return // stale before we even start

  const page = await pdfDoc.getPage(pageNum)
  if (gen !== renderGen || !pdfDoc) return // stale after async getPage

  const container = pagesRef.value || canvas.parentElement
  if (!container) return
  const viewport = page.getViewport({ scale: 1 })
  const scale = getRenderScale(viewport, container, visiblePages)
  const scaledViewport = page.getViewport({ scale })

  const dpr = window.devicePixelRatio || 1
  const pixelWidth = Math.floor(scaledViewport.width * dpr)
  const pixelHeight = Math.floor(scaledViewport.height * dpr)
  canvas.width = pixelWidth
  canvas.height = pixelHeight
  canvas.style.width = `${scaledViewport.width}px`
  canvas.style.height = `${scaledViewport.height}px`

  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)
  const renderTask = page.render({ canvasContext: ctx, viewport: scaledViewport })
  activeRenderTasks.set(canvas, renderTask)
  try {
    await renderTask.promise
  } catch (e: any) {
    // RenderingCancelledException is expected when we cancel — ignore it.
    if (e?.name === 'RenderingCancelledException') return
    throw e
  } finally {
    // Clean up task tracking regardless of outcome.
    if (activeRenderTasks.get(canvas) === renderTask) {
      activeRenderTasks.delete(canvas)
    }
  }

  if (gen !== renderGen || !pdfDoc) return // stale after async render

  // Cache the rendered result as an ImageBitmap
  try {
    evictCacheIfNeeded()
    const bitmap = await createImageBitmap(canvas)
    pageCache.set(pageNum, {
      bitmap,
      cssWidth: canvas.style.width,
      cssHeight: canvas.style.height,
      pixelWidth,
      pixelHeight,
    })
  } catch {
    // Non-critical — cache miss is fine
  }
}

async function prerenderPage(pageNum: number, visiblePages: number, gen: number) {
  if (!pdfDoc || pageNum < 1 || pageNum > totalPages.value) return
  if (pageCache.has(pageNum)) return
  if (gen !== renderGen) return // stale before starting

  const page = await pdfDoc.getPage(pageNum)
  if (gen !== renderGen || !pdfDoc) return // stale after async getPage
  if (pageCache.has(pageNum)) return // populated while we awaited

  const container = pagesRef.value
  if (!container) return
  const viewport = page.getViewport({ scale: 1 })
  const scale = getRenderScale(viewport, container, visiblePages)
  const scaledViewport = page.getViewport({ scale })

  const dpr = window.devicePixelRatio || 1
  const pixelWidth = Math.floor(scaledViewport.width * dpr)
  const pixelHeight = Math.floor(scaledViewport.height * dpr)

  const offscreen = document.createElement('canvas')
  offscreen.width = pixelWidth
  offscreen.height = pixelHeight

  const ctx = offscreen.getContext('2d')!
  ctx.scale(dpr, dpr)
  const renderTask = page.render({ canvasContext: ctx, viewport: scaledViewport })
  try {
    await renderTask.promise
  } catch (e: any) {
    if (e?.name === 'RenderingCancelledException') return
    return // Non-critical — skip caching on any error
  }

  if (gen !== renderGen || !pdfDoc) return // stale after async render

  try {
    evictCacheIfNeeded()
    const bitmap = await createImageBitmap(offscreen)
    pageCache.set(pageNum, {
      bitmap,
      cssWidth: `${scaledViewport.width}px`,
      cssHeight: `${scaledViewport.height}px`,
      pixelWidth,
      pixelHeight,
    })
  } catch {
    // Non-critical
  }
}

async function renderSpread() {
  if (!pdfDoc) return
  const left = canvasLeftRef.value
  const right = canvasRightRef.value
  if (!left) return

  // Bump the generation counter so any in-flight renders from previous
  // invocations know they are stale and should abort.
  const gen = ++renderGen

  const visiblePages = pageLeft.value + 1 <= totalPages.value ? 2 : 1

  await renderPage(pageLeft.value, left, visiblePages, gen)

  if (gen !== renderGen) return // page changed while rendering left page

  if (right && pageLeft.value + 1 <= totalPages.value) {
    right.style.display = ''
    await renderPage(pageLeft.value + 1, right, visiblePages, gen)
  } else if (right) {
    right.style.display = 'none'
  }

  if (gen !== renderGen) return // page changed while rendering right page

  // Fire-and-forget: pre-render adjacent spreads in the background
  const pl = pageLeft.value
  setTimeout(() => {
    prerenderPage(pl + 2, 2, gen)
    prerenderPage(pl + 3, 2, gen)
    prerenderPage(pl - 1, 2, gen)
    prerenderPage(pl - 2, 2, gen)
  }, 0)
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
  if (isFullscreen.value && showMeta.value) {
    showMeta.value = false
  }
  // ResizeObserver handles cache invalidation and re-render once dimensions settle
}

function onKeydown(e: KeyboardEvent) {
  // Don't intercept keyboard shortcuts when typing in form inputs
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return

  if (e.key === 'ArrowLeft') { prevSpread(); e.preventDefault() }
  if (e.key === 'ArrowRight') { nextSpread(); e.preventDefault() }
  if (e.key === 'f' || e.key === 'F') { toggleFullscreen(); e.preventDefault() }
  if (e.key === 'Escape' && !document.fullscreenElement) {
    router.back()
  }
}

async function toggleMeta() {
  showMeta.value = !showMeta.value
  if (showMeta.value) await loadPdfMeta()
  // ResizeObserver handles cache invalidation and re-render once dimensions settle
}

async function loadPdfMeta() {
  if (metaLoading.value || pdfMeta.value) return
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

// ResizeObserver: clear cache and re-render whenever the canvas container changes size.
// This covers fullscreen toggle, info panel open/close, window resize, and any future
// layout changes — no need to hook each trigger manually.
let resizeObserver: ResizeObserver | null = null
let resizeDebounceTimer: ReturnType<typeof setTimeout> | null = null
let lastObservedWidth = 0
let resizeObserverReady = false  // ignore initial callback fired on observe()

function onPagesResize(entries: ResizeObserverEntry[]) {
  const width = Math.round(entries[0].contentRect.width)
  if (!resizeObserverReady) {
    // First callback is the initial observation — record width and ignore
    lastObservedWidth = width
    resizeObserverReady = true
    return
  }
  if (width === lastObservedWidth) return
  lastObservedWidth = width
  if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer)
  resizeDebounceTimer = setTimeout(() => {
    clearPageCache()
    renderSpread()
  }, 80)
}

watch(pageLeft, renderSpread)

onMounted(async () => {
  const sheetId = Number(route.params.id)

  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)

  try {
    const [sheetData, pdfData, foldersData] = await Promise.all([
      getSheet(sheetId),
      getSheetPDF(sheetId),
      getSelectedFolders(),
    ])
    sheet.value = sheetData
    folders.value = foldersData.folders
    populateEditForm(sheetData.metadata || {})

    clearPageCache()
    pdfDoc = await pdfjsLib.getDocument({ data: pdfData }).promise
    totalPages.value = pdfDoc.numPages
    loading.value = false
    if (showMeta.value) await loadPdfMeta()

    await nextTick()
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))

    // Start ResizeObserver now that pagesRef is in the DOM.
    // resizeObserverReady starts false so the initial callback is treated as
    // the baseline measurement and does not trigger a re-render.
    if (pagesRef.value) {
      resizeObserver = new ResizeObserver(onPagesResize)
      resizeObserver.observe(pagesRef.value)
    }

    await renderSpread()
  } catch (e: any) {
    error.value = e.message
    loading.value = false
  }
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  resizeObserver?.disconnect()
  if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer)
  // Invalidate generation so any in-flight async render callbacks abort.
  renderGen++
  // Cancel any active pdfjs render tasks so they don't throw after destroy.
  for (const task of activeRenderTasks.values()) {
    task.cancel()
  }
  activeRenderTasks.clear()
  pdfDoc?.destroy()
  pdfDoc = null
  clearPageCache()
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
      <div v-if="!isFullscreen" class="filepath-line">
        <span class="badge" :class="sheet?.backend_type">{{ sheet?.backend_type === 'local' ? 'Local' : 'Drive' }}</span> {{ sheetFolderName(sheet) }} : {{ relativeFilePath(sheet) }}
      </div>
      <div class="content-area">
        <div class="pages" ref="pagesRef" @click="handlePagesClick">
          <canvas ref="canvasLeftRef" class="page-canvas"></canvas>
          <canvas ref="canvasRightRef" class="page-canvas"></canvas>
        </div>
        <div v-if="showMeta" class="meta-panel">
          <!-- Editable core fields -->
          <div class="meta-section">
            <h4 class="meta-heading">Sheet Info</h4>
            <div class="meta-fields">
              <div v-for="field in editableFields" :key="field.key" class="meta-field">
                <label>{{ field.label }}</label>
                <AutocompleteInput
                  v-model="editForm[field.key]"
                  :placeholder="field.label"
                  :fetchSuggestions="(q: string) => getMetadataValues(field.key, q).then(r => r.values)"
                />
              </div>
              <!-- Pages (read-only) -->
              <div class="meta-field">
                <label>Pages</label>
                <input type="text" :value="sheet?.metadata?.pages || '—'" readonly class="readonly" />
              </div>
            </div>
            <div class="meta-actions">
              <button class="save-btn" @click="saveMetadata" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save' }}
              </button>
              <span v-if="saveSuccess" class="save-ok">Saved</span>
              <span v-if="saveError" class="save-err">{{ saveError }}</span>
            </div>
          </div>
          <!-- Custom fields -->
          <div class="meta-section">
            <h4 class="meta-heading">Custom Fields</h4>
            <div class="meta-fields">
              <div v-for="(cf, idx) in customFields" :key="idx" class="custom-field-row">
                <div class="custom-field-key">
                  <AutocompleteInput
                    v-model="cf.key"
                    placeholder="Field name"
                    :fetchSuggestions="(q: string) => getMetadataKeys(q).then(r => r.keys.filter(k => !coreKeySet.has(k)))"
                  />
                </div>
                <div class="custom-field-value">
                  <AutocompleteInput
                    v-model="cf.value"
                    placeholder="Value"
                    :fetchSuggestions="(q: string) => cf.key ? getMetadataValues(cf.key, q).then(r => r.values) : Promise.resolve([])"
                  />
                </div>
                <button class="remove-field-btn" @click="removeCustomField(idx)" title="Remove field">&times;</button>
              </div>
            </div>
            <button class="add-field-btn" @click="addCustomField">+ Add Field</button>
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

.filepath-line {
  background: #2f2f2f;
  border-top: 1px solid #3c3c3c;
  border-bottom: 1px solid #3c3c3c;
  color: #bdbdbd;
  font-size: 0.8rem;
  padding: 0.3rem 1rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
}

.badge {
  display: inline-block;
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  margin-right: 0.5rem;
  font-weight: 600;
  text-transform: uppercase;
  vertical-align: middle;
  flex-shrink: 0;
}

.badge.local {
  background: #e3f2fd;
  color: #1565c0;
}

.badge.gdrive {
  background: #fce4ec;
  color: #c62828;
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

:global([data-pdf-filter="sepia"] .page-canvas) {
  filter: brightness(0.9) sepia(0.4);
}

:global([data-pdf-filter="invert"] .page-canvas) {
  filter: invert(1) hue-rotate(180deg);
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

.meta-field input {
  width: 100%;
  padding: 0.35rem 0.5rem;
  background: #3a3a3a;
  border: 1px solid #666;
  border-radius: 4px;
  color: #eee;
  font-size: 0.85rem;
  box-sizing: border-box;
}

.meta-field input:focus {
  outline: none;
  border-color: #4285f4;
}

.meta-field input.readonly {
  background: #444;
  border-color: #555;
  color: #bbb;
}

.meta-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.save-btn {
  background: #4285f4;
  border: none;
  color: #fff;
  border-radius: 4px;
  padding: 0.4rem 1rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.save-btn:hover:not(:disabled) {
  background: #3367d6;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.save-ok {
  color: #66bb6a;
  font-size: 0.85rem;
}

.save-err {
  color: #ef5350;
  font-size: 0.85rem;
}

.custom-field-row {
  display: flex;
  gap: 0.35rem;
  align-items: flex-start;
}

.custom-field-key {
  flex: 2;
  min-width: 0;
}

.custom-field-value {
  flex: 3;
  min-width: 0;
}

.remove-field-btn {
  background: none;
  border: none;
  color: #999;
  font-size: 1.1rem;
  cursor: pointer;
  padding: 0.25rem 0.4rem;
  line-height: 1;
  flex-shrink: 0;
}

.remove-field-btn:hover {
  color: #ef5350;
}

.add-field-btn {
  background: none;
  border: 1px dashed #666;
  color: #aaa;
  border-radius: 4px;
  padding: 0.3rem 0.7rem;
  cursor: pointer;
  font-size: 0.8rem;
  margin-top: 0.5rem;
  width: 100%;
}

.add-field-btn:hover {
  border-color: #888;
  color: #ccc;
}
</style>
