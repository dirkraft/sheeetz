<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import {
  getSheets, getSelectedFolders, getSettings, updateSettings,
  getMetadataKeys, previewOrganize, startOrganize, getOrganizeJob,
  type SheetRecord, type LibraryFolder, type SheetPreview, type OrganizeJobStatus,
} from '../api'

const router = useRouter()

// --- Column definitions ---

interface ColumnDef {
  key: string
  label: string
  sortKey?: string
  render: (s: SheetRecord) => string
  isSource?: boolean
  isFolder?: boolean
  isCustom?: boolean
}

function backendLabel(backendType: string) {
  return backendType === 'local' ? 'Local' : 'Drive'
}

function folderBackendType(s: SheetRecord) {
  const folder = folders.value.find((f) => f.id === s.library_folder_id)
  return folder?.backend_type || s.backend_type
}

function relativeFolderPath(s: SheetRecord) {
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

function relativeFilePath(s: SheetRecord) {
  const relDir = relativeFolderPath(s)
  return relDir ? `${relDir}/${s.filename}` : s.filename
}

const STATIC_COLUMNS: ColumnDef[] = [
  { key: 'filename', label: 'Filename', sortKey: 'filename', render: (s) => s.filename },
  { key: 'filepath', label: 'Filepath', sortKey: 'folder_path', render: (s) => relativeFilePath(s) },
  { key: 'title', label: 'Title', sortKey: 'title', render: (s) => s.metadata?.title || '\u2014' },
  { key: 'composer', label: 'Composer', sortKey: 'composer', render: (s) => s.metadata?.composer || '\u2014' },
  { key: 'tags', label: 'Tags', sortKey: 'tags', render: (s) => s.metadata?.tags || '\u2014' },
  { key: 'pages', label: 'Pages', sortKey: 'pages', render: (s) => s.metadata?.pages || '\u2014' },
  { key: 'folder', label: 'Folder', sortKey: 'folder_path', isFolder: true, render: (s) => {
    const f = folders.value.find(f => f.id === s.library_folder_id)
    return f ? f.folder_name : (s.folder_path || '\u2014')
  } },
  { key: 'source', label: 'Source', sortKey: 'backend_type', isSource: true, render: (s) => backendLabel(s.backend_type) },
]

const STATIC_KEYS = new Set(STATIC_COLUMNS.map((c) => c.key))

function makeCustomColumn(key: string): ColumnDef {
  return { key, label: key, sortKey: key, isCustom: true, render: (s) => s.metadata?.[key] || '\u2014' }
}

const customColumns = ref<ColumnDef[]>([])

const allColumns = computed(() => [...STATIC_COLUMNS, ...customColumns.value])
const columnMap = computed(() => Object.fromEntries(allColumns.value.map((c) => [c.key, c])))
const allKeys = computed(() => allColumns.value.map((c) => c.key))

const DEFAULT_COLUMNS = ['filename', 'composer', 'filepath', 'folder', 'source']

// columnOrder: all keys in display order (active first, then inactive)
const columnOrder = ref<string[]>(STATIC_COLUMNS.map((c) => c.key))
const activeSet = ref(new Set<string>(DEFAULT_COLUMNS))

const activeColumns = computed(() =>
  columnOrder.value.filter((k) => activeSet.value.has(k)).map((k) => columnMap.value[k]).filter(Boolean)
)

function mergeCustomKeys(keys: string[]) {
  const existingCustomKeys = new Set(customColumns.value.map((c) => c.key))
  const newKeys = keys.filter((k) => !STATIC_KEYS.has(k) && !existingCustomKeys.has(k))
  if (!newKeys.length) return
  customColumns.value = [...customColumns.value, ...newKeys.map(makeCustomColumn)]
  // Add new custom keys to columnOrder (at end) if not already present
  const orderSet = new Set(columnOrder.value)
  const toAdd = newKeys.filter((k) => !orderSet.has(k))
  if (toAdd.length) {
    columnOrder.value = [...columnOrder.value, ...toAdd]
  }
}

const showColumnPicker = ref(false)

function isColumnActive(key: string) {
  return activeSet.value.has(key)
}

function toggleColumn(key: string) {
  if (activeSet.value.has(key)) {
    if (activeSet.value.size <= 1) return
    activeSet.value.delete(key)
  } else {
    activeSet.value.add(key)
  }
  // Trigger reactivity
  activeSet.value = new Set(activeSet.value)
  saveColumns()
  page.value = 1
  load()
}

function getActiveKeysInOrder(): string[] {
  return columnOrder.value.filter((k) => activeSet.value.has(k))
}

async function saveColumns() {
  try {
    await updateSettings({ columns: getActiveKeysInOrder() })
  } catch {
    // silently ignore save failures
  }
}

// --- Drag and drop reordering ---

const dragIdx = ref<number | null>(null)
const dropIdx = ref<number | null>(null)

function onDragStart(idx: number, e: DragEvent) {
  dragIdx.value = idx
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
  }
}

function onDragOver(idx: number, e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropIdx.value = idx
}

function onDrop(idx: number) {
  if (dragIdx.value === null || dragIdx.value === idx) {
    dragIdx.value = null
    dropIdx.value = null
    return
  }
  const order = [...columnOrder.value]
  const [moved] = order.splice(dragIdx.value, 1)
  order.splice(idx, 0, moved)
  columnOrder.value = order
  dragIdx.value = null
  dropIdx.value = null
  saveColumns()
  page.value = 1
  load()
}

function onDragEnd() {
  dragIdx.value = null
  dropIdx.value = null
}

// --- Data ---

const sheets = ref<SheetRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50

const filterSearch = ref('')
const filterFolderId = ref<number | null>(null)

const folders = ref<LibraryFolder[]>([])
const loading = ref(false)
const error = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const initialized = ref(false)

function getSortKeysInOrder(): string[] {
  const seen = new Set<string>()
  const keys: string[] = []
  for (const key of getActiveKeysInOrder()) {
    const col = columnMap.value[key]
    const sortKey = col?.sortKey || key
    if (seen.has(sortKey)) continue
    seen.add(sortKey)
    keys.push(sortKey)
  }
  return keys
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await getSheets({
      search: filterSearch.value || undefined,
      folder_id: filterFolderId.value ?? undefined,
      sort_keys: getSortKeysInOrder(),
      page: page.value,
      page_size: pageSize,
    })
    sheets.value = data.sheets
    total.value = data.total
    // Discover any new custom metadata keys from loaded sheets
    const discoveredKeys = new Set<string>()
    for (const s of data.sheets) {
      if (s.metadata) {
        for (const k of Object.keys(s.metadata)) discoveredKeys.add(k)
      }
    }
    mergeCustomKeys([...discoveredKeys])
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function debouncedLoad() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
}

watch(filterSearch, debouncedLoad)
watch([filterFolderId], () => {
  page.value = 1
  load()
})
watch(page, load)

onMounted(async () => {
  // Fetch custom metadata keys so dynamic columns are available before restoring settings
  try {
    const { keys } = await getMetadataKeys()
    mergeCustomKeys(keys)
  } catch {
    // custom columns will be empty until sheets load
  }

  try {
    const settings = await getSettings()
    if (settings.columns?.length) {
      const saved = settings.columns.filter((k: string) => columnMap.value[k])
      if (!saved.includes('filepath')) {
        const filenameIdx = saved.indexOf('filename')
        if (filenameIdx >= 0) {
          saved.splice(filenameIdx + 1, 0, 'filepath')
        } else {
          saved.push('filepath')
        }
      }
      if (saved.length) {
        activeSet.value = new Set(saved)
        // Active columns first in saved order, then remaining keys
        const remaining = allKeys.value.filter((k) => !activeSet.value.has(k))
        columnOrder.value = [...saved, ...remaining]
      }
    }
    if (settings.organizeTemplate) {
      organizeTemplate.value = settings.organizeTemplate
    }
  } catch {
    // use defaults
  }
  const foldersData = await getSelectedFolders()
  folders.value = foldersData.folders
  await load()
  initialized.value = true
})

onActivated(() => {
  if (!initialized.value) return
  load()
})

const totalPages = ref(0)
watch(total, (t) => {
  totalPages.value = Math.ceil(t / pageSize)
})

// --- Selection ---

const selectedIds = ref(new Set<number>())

const allSelected = computed(
  () => sheets.value.length > 0 && sheets.value.every((s) => selectedIds.value.has(s.id))
)
const someSelected = computed(
  () => !allSelected.value && sheets.value.some((s) => selectedIds.value.has(s.id))
)

function toggleSelect(id: number) {
  if (selectedIds.value.has(id)) {
    selectedIds.value.delete(id)
  } else {
    selectedIds.value.add(id)
  }
  selectedIds.value = new Set(selectedIds.value)
}

function toggleSelectAll() {
  if (allSelected.value) {
    // Deselect all visible
    for (const s of sheets.value) selectedIds.value.delete(s.id)
  } else {
    for (const s of sheets.value) selectedIds.value.add(s.id)
  }
  selectedIds.value = new Set(selectedIds.value)
}

function clearSelection() {
  selectedIds.value = new Set()
}

// --- Template validation ---

function validateTemplate(template: string, vars: TemplateVar[]): string {
  if (!template.trim()) return ''
  const knownKeys = new Set(vars.map((v) => v.key))
  // Extract all $varname references (inside or outside fallback groups)
  const unknown: string[] = []
  const seen = new Set<string>()
  for (const m of template.matchAll(/\$(\w+)/g)) {
    const key = m[1]
    if (!knownKeys.has(key) && !seen.has(key)) {
      unknown.push(key)
      seen.add(key)
    }
  }
  if (unknown.length) {
    return `Unknown variable${unknown.length > 1 ? 's' : ''}: ${unknown.map((k) => '$' + k).join(', ')}`
  }
  return ''
}

const templateValidationError = computed(() =>
  validateTemplate(organizeTemplate.value, templateVars.value)
)

// --- Template variable hints ---

interface TemplateVar {
  key: string
  count: number
  total: number
  example: string
}

const templateVars = computed((): TemplateVar[] => {
  const selected = sheets.value.filter((s) => selectedIds.value.has(s.id))
  const total = selected.length
  if (!total) return []

  const counts: Record<string, number> = {}
  const examples: Record<string, string> = {}

  for (const sheet of selected) {
    if (sheet.metadata) {
      for (const [k, v] of Object.entries(sheet.metadata)) {
        if (k === 'pages') continue
        counts[k] = (counts[k] || 0) + 1
        if (!examples[k] && v) examples[k] = v
      }
    }
  }

  // Builtins: always available
  const firstFilename = selected[0]?.filename ?? ''
  const stem = firstFilename.replace(/\.[^.]+$/, '')
  const ext = firstFilename.includes('.') ? firstFilename.split('.').pop()! : 'pdf'

  const builtins: TemplateVar[] = [
    { key: 'filename', count: total, total, example: stem },
    { key: 'ext', count: total, total, example: ext },
  ]

  const metaVars: TemplateVar[] = Object.entries(counts)
    .map(([key, count]) => ({ key, count, total, example: examples[key] || '' }))
    .sort((a, b) => b.count - a.count)

  return [...builtins, ...metaVars]
})

// Close pickers when clicking outside
function onDocClick() {
  showColumnPicker.value = false
  showActionsMenu.value = false
}

// --- Actions menu ---

const showActionsMenu = ref(false)

// --- Organize wizard ---

type WizardStep = 'template' | 'preview' | 'progress' | 'done'

const wizardOpen = ref(false)
const wizardStep = ref<WizardStep>('template')
const organizeTemplate = ref('($composer or $artist)/($title or $filename).$ext')
const previews = ref<SheetPreview[]>([])
const previewError = ref('')
const previewLoading = ref(false)
// Sheet IDs confirmed for the actual job (user may deselect some in preview step)
const confirmedIds = ref(new Set<number>())
const organizeJob = ref<OrganizeJobStatus | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

function openOrganizeWizard() {
  showActionsMenu.value = false
  wizardOpen.value = true
  wizardStep.value = 'template'
  previews.value = []
  previewError.value = ''
  organizeJob.value = null
  confirmedIds.value = new Set(selectedIds.value)
}

function closeWizard() {
  wizardOpen.value = false
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  // Reload sheet list if we moved anything
  if (organizeJob.value && organizeJob.value.moved_count > 0) {
    clearSelection()
    load()
  }
}

async function runPreview() {
  previewLoading.value = true
  previewError.value = ''
  try {
    const ids = [...confirmedIds.value]
    const result = await previewOrganize(ids, organizeTemplate.value)
    updateSettings({ organizeTemplate: organizeTemplate.value }).catch(() => {})
    previews.value = result.previews
    // Re-sync confirmedIds to moveable sheets only (excludes no-ops and errors)
    confirmedIds.value = new Set(result.previews.filter((p) => p.can_move).map((p) => p.sheet_id))
    wizardStep.value = 'preview'
  } catch (e: any) {
    previewError.value = e.message
  } finally {
    previewLoading.value = false
  }
}

function togglePreviewSheet(sheetId: number) {
  if (confirmedIds.value.has(sheetId)) {
    confirmedIds.value.delete(sheetId)
  } else {
    confirmedIds.value.add(sheetId)
  }
  confirmedIds.value = new Set(confirmedIds.value)
}

const moveablePreviews = computed(() => previews.value.filter((p) => p.can_move))
const confirmedMoveCount = computed(
  () => moveablePreviews.value.filter((p) => confirmedIds.value.has(p.sheet_id)).length
)

async function submitOrganize() {
  const ids = [...confirmedIds.value].filter((id) => {
    const p = previews.value.find((p) => p.sheet_id === id)
    return p && p.can_move
  })
  if (!ids.length) return

  wizardStep.value = 'progress'
  try {
    const job = await startOrganize(ids, organizeTemplate.value)
    organizeJob.value = job
    pollTimer = setInterval(async () => {
      if (!organizeJob.value) return
      try {
        const updated = await getOrganizeJob(organizeJob.value.job_id)
        organizeJob.value = updated
        if (updated.status !== 'running') {
          if (pollTimer) clearInterval(pollTimer)
          pollTimer = null
          wizardStep.value = 'done'
        }
      } catch {
        // keep polling
      }
    }, 1000)
  } catch (e: any) {
    organizeJob.value = {
      job_id: '',
      status: 'error',
      total: ids.length,
      processed: 0,
      moved_count: 0,
      failed_count: 0,
      current_file: '',
      errors: [],
      error: e.message,
    }
    wizardStep.value = 'done'
  }
}

const progressPct = computed(() => {
  if (!organizeJob.value || !organizeJob.value.total) return 0
  return Math.round((organizeJob.value.processed / organizeJob.value.total) * 100)
})

function sheetHref(id: number) {
  return router.resolve(`/sheets/${id}`).href
}

function openSheetInNewTab(id: number) {
  window.open(sheetHref(id), '_blank', 'noopener')
}

function openSheet(id: number) {
  router.push(`/sheets/${id}`)
}

function onRowClick(e: MouseEvent, id: number) {
  // Respect common "open in new tab" shortcuts from desktop browsers.
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) {
    openSheetInNewTab(id)
    return
  }
  openSheet(id)
}

function onRowAuxClick(e: MouseEvent, id: number) {
  if (e.button === 1) {
    e.preventDefault()
    openSheetInNewTab(id)
  }
}
</script>

<template>
  <div class="sheets" @click="onDocClick">
    <div class="header-row">
      <h1>Sheet Music</h1>
      <div class="header-actions">
        <!-- Actions menu (shown when sheets selected) -->
        <div v-if="selectedIds.size > 0" class="actions-wrap" @click.stop>
          <button class="actions-btn" @click="showActionsMenu = !showActionsMenu">
            Actions ({{ selectedIds.size }}) ▾
          </button>
          <div v-if="showActionsMenu" class="actions-menu">
            <button class="action-item" @click="openOrganizeWizard">Organize files…</button>
          </div>
        </div>
        <div class="column-picker-wrap" @click.stop>
          <button class="columns-btn" @click="showColumnPicker = !showColumnPicker">
            Columns
          </button>
          <div v-if="showColumnPicker" class="column-picker">
            <div
              v-for="(key, idx) in columnOrder"
              :key="key"
              class="column-option"
              :class="{
                'drag-over': dropIdx === idx && dragIdx !== idx,
                dragging: dragIdx === idx,
              }"
              draggable="true"
              @dragstart="onDragStart(idx, $event)"
              @dragover="onDragOver(idx, $event)"
              @drop="onDrop(idx)"
              @dragend="onDragEnd"
            >
              <span class="drag-handle">&#x2630;</span>
              <label class="column-label" @click.stop>
                <input
                  type="checkbox"
                  :checked="isColumnActive(key)"
                  :disabled="isColumnActive(key) && activeSet.size <= 1"
                  @change="toggleColumn(key)"
                />
                {{ columnMap[key].label }}
                <span v-if="columnMap[key].isCustom" class="custom-tag">custom</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="filters">
      <input
        v-model="filterSearch"
        type="text"
        placeholder="Search sheets..."
        class="filter-input"
      />
      <select v-model="filterFolderId" class="filter-select">
        <option :value="null">All Folders</option>
        <option v-for="f in folders" :key="f.id" :value="f.id">
          {{ f.folder_name }}
        </option>
      </select>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="loading && sheets.length === 0" class="loading">Loading...</div>

    <div v-else-if="sheets.length === 0" class="empty">
      <p>No sheet music found. Go to <router-link to="/library">Library</router-link> to add folders and scan for PDFs.</p>
    </div>

    <template v-else>
      <div class="result-bar">
        <p class="result-count">{{ total }} sheet{{ total !== 1 ? 's' : '' }} found</p>
        <button v-if="selectedIds.size > 0" class="clear-selection-btn" @click="clearSelection">
          Clear selection
        </button>
      </div>

      <table class="sheets-table">
        <thead>
          <tr>
            <th class="select-col">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate="someSelected"
                @change="toggleSelectAll"
              />
            </th>
            <th
              v-for="col in activeColumns"
              :key="col.key"
            >
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in sheets"
            :key="s.id"
            class="sheet-row"
            :class="{ selected: selectedIds.has(s.id) }"
            @click="onRowClick($event, s.id)"
            @auxclick="onRowAuxClick($event, s.id)"
          >
            <td class="select-col" @click.stop="toggleSelect(s.id)">
              <input
                type="checkbox"
                :checked="selectedIds.has(s.id)"
              />
            </td>
            <td v-for="col in activeColumns" :key="col.key">
              <template v-if="col.isSource">
                <span class="badge" :class="s.backend_type">
                  {{ col.render(s) }}
                </span>
              </template>
              <template v-else-if="col.isFolder">
                <span class="folder-cell">
                  <span class="badge" :class="folderBackendType(s)">
                    {{ backendLabel(folderBackendType(s)) }}
                  </span>
                  <span>{{ col.render(s) }}</span>
                </span>
              </template>
              <template v-else>{{ col.render(s) }}</template>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="totalPages > 1" class="pagination">
        <button :disabled="page <= 1" @click="page--">Prev</button>
        <span>Page {{ page }} of {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="page++">Next</button>
      </div>
    </template>

    <!-- Organize Wizard Modal -->
    <teleport to="body">
      <div v-if="wizardOpen" class="modal-backdrop" @click.self="closeWizard">
        <div class="modal">
          <div class="modal-header">
            <h2>Organize Files</h2>
            <button class="modal-close" @click="closeWizard">✕</button>
          </div>

          <!-- Step: Template -->
          <div v-if="wizardStep === 'template'" class="modal-body">
            <p class="wizard-desc">
              Define a path template to rename and reorganize the selected
              <strong>{{ confirmedIds.size }}</strong> file{{ confirmedIds.size !== 1 ? 's' : '' }}.
              Files will be moved within their library folder.
            </p>
            <label class="field-label">Path template</label>
            <input
              v-model="organizeTemplate"
              class="template-input"
              placeholder="($composer or $artist)/($title or $filename).$ext"
              spellcheck="false"
            />
            <div class="template-help">
              <strong>Syntax:</strong>
              <code>$key</code> references a metadata field.
              <code>($a or $b)</code> uses the first non-empty value.
              Built-ins: <code>$filename</code> (stem), <code>$ext</code> (extension).
              Segments separated by <code>/</code> become folders.
            </div>

            <div v-if="templateVars.length" class="var-table-wrap">
              <p class="var-table-label">Available variables for selected sheets</p>
              <table class="var-table">
                <thead>
                  <tr>
                    <th>Variable</th>
                    <th>Coverage</th>
                    <th>Example</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="v in templateVars" :key="v.key">
                    <td><code class="var-name">${{ v.key }}</code></td>
                    <td :class="{ 'coverage-full': v.count === v.total, 'coverage-partial': v.count < v.total }">
                      {{ v.count }}/{{ v.total }}
                    </td>
                    <td class="example-cell">{{ v.example }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="templateValidationError" class="template-error">{{ templateValidationError }}</div>
            <div v-else-if="previewError" class="error">{{ previewError }}</div>
            <div class="modal-footer">
              <button class="btn-secondary" @click="closeWizard">Cancel</button>
              <button
                class="btn-primary"
                :disabled="previewLoading || !organizeTemplate.trim() || !!templateValidationError"
                @click="runPreview"
              >
                {{ previewLoading ? 'Computing…' : 'Preview →' }}
              </button>
            </div>
          </div>

          <!-- Step: Preview -->
          <div v-else-if="wizardStep === 'preview'" class="modal-body">
            <p class="wizard-desc">
              Review where each file will be moved. Uncheck any you want to skip.
            </p>
            <div class="preview-table-wrap">
              <table class="preview-table">
                <thead>
                  <tr>
                    <th class="select-col"></th>
                    <th>From → To</th>
                    <th class="status-col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="p in previews"
                    :key="p.sheet_id"
                    :class="{ 'row-disabled': !p.can_move, 'row-no-op': p.no_op }"
                  >
                    <td class="select-col">
                      <input
                        v-if="p.can_move"
                        type="checkbox"
                        :checked="confirmedIds.has(p.sheet_id)"
                        @change="togglePreviewSheet(p.sheet_id)"
                      />
                    </td>
                    <td class="path-cell">
                      <div class="path-from"><span class="path-label">from</span>{{ p.from_path }}</div>
                      <div v-if="!p.no_op" class="path-to"><span class="path-label">to</span>{{ p.to_path ?? '—' }}</div>
                    </td>
                    <td class="status-col">
                      <span v-if="p.no_op" class="noop-badge">already here</span>
                      <span v-else-if="!p.can_move" class="warning-badge" :title="p.warning">
                        ⚠ {{ p.warning }}
                      </span>
                      <span v-else-if="!confirmedIds.has(p.sheet_id)" class="skip-badge">
                        skip
                      </span>
                      <span v-else class="ok-badge">✓</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="modal-footer">
              <button class="btn-secondary" @click="wizardStep = 'template'">← Back</button>
              <button
                class="btn-primary"
                :disabled="confirmedMoveCount === 0"
                @click="submitOrganize"
              >
                Move {{ confirmedMoveCount }} file{{ confirmedMoveCount !== 1 ? 's' : '' }}
              </button>
            </div>
          </div>

          <!-- Step: Progress -->
          <div v-else-if="wizardStep === 'progress'" class="modal-body">
            <p class="wizard-desc">Moving files…</p>
            <div v-if="organizeJob" class="progress-wrap">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
              </div>
              <p class="progress-label">
                {{ organizeJob.processed }} / {{ organizeJob.total }}
                <span v-if="organizeJob.current_file" class="current-file">— {{ organizeJob.current_file }}</span>
              </p>
            </div>
          </div>

          <!-- Step: Done -->
          <div v-else-if="wizardStep === 'done'" class="modal-body">
            <div v-if="organizeJob">
              <div v-if="organizeJob.status === 'error'" class="error">
                Job failed: {{ organizeJob.error }}
              </div>
              <div v-else class="done-summary">
                <p class="done-title">
                  {{ organizeJob.moved_count === organizeJob.total ? '✓ Done!' : 'Completed with issues' }}
                </p>
                <p>Moved: {{ organizeJob.moved_count }} / {{ organizeJob.total }}</p>
                <p v-if="organizeJob.failed_count > 0">Failed: {{ organizeJob.failed_count }}</p>
                <ul v-if="organizeJob.errors.length" class="error-list">
                  <li v-for="(e, i) in organizeJob.errors" :key="i">{{ e }}</li>
                </ul>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn-primary" @click="closeWizard">Close</button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.sheets {
  max-width: 960px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.header-row h1 {
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Actions menu */
.actions-wrap {
  position: relative;
}

.actions-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid #1976d2;
  border-radius: 4px;
  background: #e3f2fd;
  color: #1565c0;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
}

.actions-btn:hover {
  background: #bbdefb;
}

.actions-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  z-index: 10;
  min-width: 160px;
  padding: 0.3rem 0;
}

.action-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.5rem 1rem;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.9rem;
}

.action-item:hover {
  background: var(--c-hover);
}

.column-picker-wrap {
  position: relative;
}

.columns-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
  color: var(--c-text);
  cursor: pointer;
  font-size: 0.85rem;
}

.columns-btn:hover {
  background: var(--c-hover);
}

.column-picker {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  color: var(--c-text);
  border-radius: 6px;
  padding: 0.5rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 10;
  min-width: 160px;
}

.column-option {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.4rem;
  font-size: 0.85rem;
  white-space: nowrap;
  border-radius: 3px;
  cursor: grab;
  user-select: none;
}

.column-option:hover {
  background: var(--c-hover);
}

.column-option.dragging {
  opacity: 0.4;
}

.column-option.drag-over {
  border-top: 2px solid #1976d2;
}

.drag-handle {
  color: var(--c-text-muted);
  font-size: 0.75rem;
  line-height: 1;
  flex-shrink: 0;
}

.column-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  flex: 1;
}

.custom-tag {
  font-size: 0.65rem;
  color: var(--c-text-muted);
  font-style: italic;
  margin-left: 0.2rem;
}

.filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.filter-input {
  flex: 1;
  min-width: 200px;
  padding: 0.5rem;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  font-size: 0.9rem;
}

.filter-short {
  flex: 0 1 160px;
  min-width: 120px;
}

.filter-select {
  padding: 0.5rem;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  font-size: 0.9rem;
}

.result-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.result-count {
  color: var(--c-text-muted);
  font-size: 0.85rem;
  margin: 0;
}

.clear-selection-btn {
  font-size: 0.8rem;
  color: #1976d2;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}

.sheets-table {
  width: 100%;
  border-collapse: collapse;
}

.sheets-table th,
.sheets-table td {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--c-border);
}

.sheets-table th {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--c-text-muted);
  border-bottom: 2px solid var(--c-border);
}

.select-col {
  width: 2rem;
  padding-right: 0;
}

.sheet-row {
  cursor: pointer;
}

.sheet-row:hover {
  background: var(--c-hover);
}

.sheet-row.selected {
  background: var(--c-selected);
}

:global(html[data-theme='dark']) .sheets-table th,
:global(html[data-theme='dark']) .sheets-table td {
  border-bottom-color: #3a4148;
}

:global(html[data-theme='dark']) .sheets-table th {
  color: #b8c0c8;
  border-bottom-color: #4a525b;
}

:global(html[data-theme='dark']) .sheets-table tbody .sheet-row:hover {
  background: #2b323a;
}



:global(html[data-theme='dark']) .pagination button {
  background: #22272e;
  border-color: #4a525b;
  color: #d8dee4;
}

:global(html[data-theme='dark']) .pagination span {
  color: #b8c0c8;
}

:global(html[data-theme='dark']) .columns-btn {
  background: #22272e;
  border-color: #4a525b;
  color: #d8dee4;
}

:global(html[data-theme='dark']) .columns-btn:hover {
  background: #2b323a;
}

:global(html[data-theme='dark']) .column-picker {
  background: #22272e;
  border-color: #4a525b;
  color: #d8dee4;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4);
}

:global(html[data-theme='dark']) .column-option:hover {
  background: #2b323a;
}

:global(html[data-theme='dark']) .drag-handle {
  color: #9ea7b0;
}

.badge {
  display: inline-block;
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.local {
  background: #e3f2fd;
  color: #1565c0;
}

.badge.gdrive {
  background: #fce4ec;
  color: #c62828;
}

.folder-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0.5rem 0;
}

.pagination button {
  padding: 0.4rem 0.8rem;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
  color: var(--c-text);
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: default;
}

.pagination span {
  font-size: 0.9rem;
  color: var(--c-text-muted);
}

.empty {
  color: var(--c-text-muted);
  margin: 2rem 0;
}

.error {
  color: #d32f2f;
  margin-bottom: 1rem;
}

.loading {
  color: var(--c-text-muted);
  margin: 2rem 0;
}

/* ---- Wizard Modal ---- */

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal {
  background: var(--c-surface);
  border-radius: 8px;
  width: min(860px, 95vw);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--c-border);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.1rem;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.1rem;
  cursor: pointer;
  color: var(--c-text-muted);
  padding: 0.2rem;
}

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.25rem;
}

.btn-primary {
  padding: 0.5rem 1.2rem;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: default;
}

.btn-secondary {
  padding: 0.5rem 1.2rem;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--c-text);
}

.btn-secondary:hover {
  background: var(--c-hover);
}

.wizard-desc {
  color: var(--c-text-muted);
  margin-bottom: 1rem;
}

.field-label {
  display: block;
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 0.35rem;
}

.template-input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.95rem;
  background: var(--c-bg);
  color: var(--c-text);
}

.template-help {
  margin-top: 0.75rem;
  font-size: 0.82rem;
  color: var(--c-text-muted);
  line-height: 1.5;
}

.template-help code {
  background: var(--c-hover);
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-family: monospace;
}

/* Variable hint table */
.template-error {
  margin-top: 0.6rem;
  font-size: 0.85rem;
  color: #b71c1c;
}

.var-table-wrap {
  margin-top: 1rem;
}

.var-table-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--c-text-muted);
  margin-bottom: 0.35rem;
}

.var-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.var-table th,
.var-table td {
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--c-border);
  text-align: left;
}

.var-table th {
  font-weight: 600;
  color: var(--c-text-muted);
  border-bottom: 1px solid var(--c-border);
}

.var-name {
  font-size: 0.82rem;
}

.coverage-full {
  color: #2e7d32;
  font-weight: 600;
}

.coverage-partial {
  color: #e65100;
}

.example-cell {
  color: var(--c-text-muted);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Preview table */
.preview-table-wrap {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: 4px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.preview-table th,
.preview-table td {
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--c-border);
  text-align: left;
}

.preview-table th {
  font-weight: 600;
  color: var(--c-text-muted);
  position: sticky;
  top: 0;
  background: var(--c-surface);
  border-bottom: 2px solid var(--c-border);
}

.row-disabled {
  opacity: 0.5;
}

.row-no-op {
  opacity: 0.4;
}

.path-cell {
  font-family: monospace;
  font-size: 0.8rem;
  word-break: break-all;
}

.path-from,
.path-to {
  padding: 0.15rem 0;
}

.path-from {
  color: var(--c-text-muted);
}

.path-to {
  color: #1565c0;
}

.path-label {
  display: inline-block;
  font-family: sans-serif;
  font-size: 0.7rem;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  width: 2.5rem;
  flex-shrink: 0;
}

.status-col {
  white-space: nowrap;
  vertical-align: top;
  padding-top: 0.5rem;
}

.warning-badge {
  color: #e65100;
  font-size: 0.78rem;
}

.skip-badge {
  color: #999;
  font-size: 0.78rem;
  font-style: italic;
}

.noop-badge {
  color: #999;
  font-size: 0.78rem;
  font-style: italic;
}

.ok-badge {
  color: #2e7d32;
  font-size: 0.85rem;
}

/* Progress */
.progress-wrap {
  margin: 1rem 0;
}

.progress-bar {
  height: 8px;
  background: var(--c-border);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: #1976d2;
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.85rem;
  color: var(--c-text-muted);
}

.current-file {
  color: var(--c-text-muted);
}

/* Done */
.done-summary {
  padding: 0.5rem 0;
}

.done-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #2e7d32;
}

.error-list {
  margin-top: 0.5rem;
  padding-left: 1.2rem;
  font-size: 0.85rem;
  color: #d32f2f;
}
</style>
