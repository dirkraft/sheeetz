<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
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
  isCustom?: boolean
}

const STATIC_COLUMNS: ColumnDef[] = [
  { key: 'filename', label: 'Filename', sortKey: 'filename', render: (s) => s.filename },
  { key: 'title', label: 'Title', sortKey: 'title', render: (s) => s.metadata?.title || '\u2014' },
  { key: 'composer', label: 'Composer', sortKey: 'composer', render: (s) => s.metadata?.composer || '\u2014' },
  { key: 'tags', label: 'Tags', sortKey: 'tags', render: (s) => s.metadata?.tags || '\u2014' },
  { key: 'pages', label: 'Pages', sortKey: 'pages', render: (s) => s.metadata?.pages || '\u2014' },
  { key: 'folder', label: 'Folder', sortKey: 'folder_path', render: (s) => s.folder_path || '\u2014' },
  { key: 'source', label: 'Source', sortKey: 'backend_type', isSource: true, render: (s) => s.backend_type === 'local' ? 'Local' : 'Drive' },
]

const STATIC_KEYS = new Set(STATIC_COLUMNS.map((c) => c.key))

function makeCustomColumn(key: string): ColumnDef {
  const label = key.charAt(0).toUpperCase() + key.slice(1)
  return { key, label, sortKey: key, isCustom: true, render: (s) => s.metadata?.[key] || '\u2014' }
}

const customColumns = ref<ColumnDef[]>([])

const allColumns = computed(() => [...STATIC_COLUMNS, ...customColumns.value])
const columnMap = computed(() => Object.fromEntries(allColumns.value.map((c) => [c.key, c])))
const allKeys = computed(() => allColumns.value.map((c) => c.key))

const DEFAULT_COLUMNS = ['filename', 'composer', 'folder', 'source']

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

const filterFilename = ref('')
const filterFolderId = ref<number | null>(null)
const filterComposer = ref('')
const sortBy = ref('filename')
const sortDir = ref<'asc' | 'desc'>('asc')

const folders = ref<LibraryFolder[]>([])
const loading = ref(false)
const error = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null

async function load() {
  loading.value = true
  error.value = ''
  try {
    const metaFilters: Record<string, string> = {}
    if (filterComposer.value) metaFilters.composer = filterComposer.value

    const data = await getSheets({
      filename: filterFilename.value || undefined,
      folder_id: filterFolderId.value ?? undefined,
      meta_filters: Object.keys(metaFilters).length ? metaFilters : undefined,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
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

watch(filterFilename, debouncedLoad)
watch(filterComposer, debouncedLoad)
watch([filterFolderId, sortBy, sortDir], () => {
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
      if (saved.length) {
        activeSet.value = new Set(saved)
        // Active columns first in saved order, then remaining keys
        const remaining = allKeys.value.filter((k) => !activeSet.value.has(k))
        columnOrder.value = [...saved, ...remaining]
      }
    }
  } catch {
    // use defaults
  }
  const foldersData = await getSelectedFolders()
  folders.value = foldersData.folders
  await load()
})

const totalPages = ref(0)
watch(total, (t) => {
  totalPages.value = Math.ceil(t / pageSize)
})

function toggleSort(col: ColumnDef) {
  if (!col.sortKey) return
  if (sortBy.value === col.sortKey) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = col.sortKey
    sortDir.value = 'asc'
  }
}

function sortIndicator(col: ColumnDef) {
  if (!col.sortKey || sortBy.value !== col.sortKey) return ''
  return sortDir.value === 'asc' ? ' \u2191' : ' \u2193'
}

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
const organizeTemplate = ref('($composer or $artist)/($title or $filename).$file_ext')
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
    previews.value = result.previews
    // Re-sync confirmedIds to only include sheet_ids in previews
    confirmedIds.value = new Set(result.previews.map((p) => p.sheet_id))
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
        v-model="filterFilename"
        type="text"
        placeholder="Search by filename..."
        class="filter-input"
      />
      <input
        v-model="filterComposer"
        type="text"
        placeholder="Composer..."
        class="filter-input filter-short"
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
              :class="{ sortable: !!col.sortKey }"
              @click="toggleSort(col)"
            >
              {{ col.label }}{{ sortIndicator(col) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in sheets"
            :key="s.id"
            class="sheet-row"
            :class="{ selected: selectedIds.has(s.id) }"
            @click="router.push(`/sheets/${s.id}`)"
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
              placeholder="($composer or $artist)/($title or $filename).$file_ext"
              spellcheck="false"
            />
            <div class="template-help">
              <strong>Syntax:</strong>
              <code>$key</code> references a metadata field.
              <code>($a or $b)</code> uses the first non-empty value.
              Built-ins: <code>$filename</code> (stem), <code>$file_ext</code> (extension).
              Segments separated by <code>/</code> become folders.
            </div>
            <div v-if="previewError" class="error">{{ previewError }}</div>
            <div class="modal-footer">
              <button class="btn-secondary" @click="closeWizard">Cancel</button>
              <button
                class="btn-primary"
                :disabled="previewLoading || !organizeTemplate.trim()"
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
                    <th>Filename</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="p in previews"
                    :key="p.sheet_id"
                    :class="{ 'row-disabled': !p.can_move }"
                  >
                    <td class="select-col">
                      <input
                        v-if="p.can_move"
                        type="checkbox"
                        :checked="confirmedIds.has(p.sheet_id)"
                        @change="togglePreviewSheet(p.sheet_id)"
                      />
                    </td>
                    <td class="filename-cell">{{ p.filename }}</td>
                    <td class="path-cell">{{ p.from_path }}</td>
                    <td class="path-cell">{{ p.to_path ?? '—' }}</td>
                    <td>
                      <span v-if="!p.can_move" class="warning-badge" :title="p.warning">
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
  background: white;
  border: 1px solid #ccc;
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
  background: #f5f5f5;
}

.column-picker-wrap {
  position: relative;
}

.columns-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 0.85rem;
}

.columns-btn:hover {
  background: #f5f5f5;
}

.column-picker {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: white;
  border: 1px solid #ccc;
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
  background: #f5f5f5;
}

.column-option.dragging {
  opacity: 0.4;
}

.column-option.drag-over {
  border-top: 2px solid #1976d2;
}

.drag-handle {
  color: #aaa;
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
  color: #888;
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
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}

.filter-short {
  flex: 0 1 160px;
  min-width: 120px;
}

.filter-select {
  padding: 0.5rem;
  border: 1px solid #ccc;
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
  color: #666;
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
  border-bottom: 1px solid #eee;
}

.sheets-table th {
  font-weight: 600;
  font-size: 0.85rem;
  color: #555;
  border-bottom: 2px solid #ddd;
}

.select-col {
  width: 2rem;
  padding-right: 0;
}

.sortable {
  cursor: pointer;
  user-select: none;
}

.sortable:hover {
  color: #333;
}

.sheet-row {
  cursor: pointer;
}

.sheet-row:hover {
  background: #f5f5f5;
}

.sheet-row.selected {
  background: #e3f2fd;
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
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

.pagination button:disabled {
  opacity: 0.4;
  cursor: default;
}

.pagination span {
  font-size: 0.9rem;
  color: #666;
}

.empty {
  color: #666;
  margin: 2rem 0;
}

.error {
  color: #d32f2f;
  margin-bottom: 1rem;
}

.loading {
  color: #666;
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
  background: white;
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
  border-bottom: 1px solid #eee;
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
  color: #666;
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
  background: white;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
}

.btn-secondary:hover {
  background: #f5f5f5;
}

.wizard-desc {
  color: #555;
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
  border: 1px solid #ccc;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.95rem;
}

.template-help {
  margin-top: 0.75rem;
  font-size: 0.82rem;
  color: #666;
  line-height: 1.5;
}

.template-help code {
  background: #f4f4f4;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-family: monospace;
}

/* Preview table */
.preview-table-wrap {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #eee;
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
  border-bottom: 1px solid #eee;
  text-align: left;
}

.preview-table th {
  font-weight: 600;
  color: #555;
  position: sticky;
  top: 0;
  background: white;
  border-bottom: 2px solid #ddd;
}

.row-disabled {
  opacity: 0.5;
}

.filename-cell {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-cell {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
  font-size: 0.8rem;
  color: #444;
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
  background: #eee;
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
  color: #555;
}

.current-file {
  color: #888;
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
