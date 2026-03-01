<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getSheets, getSelectedFolders, getSettings, updateSettings,
  getMetadataKeys,
  type SheetRecord, type LibraryFolder,
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
</script>

<template>
  <div class="sheets">
    <div class="header-row">
      <h1>Sheet Music</h1>
      <div class="column-picker-wrap">
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
      <p class="result-count">{{ total }} sheet{{ total !== 1 ? 's' : '' }} found</p>

      <table class="sheets-table">
        <thead>
          <tr>
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
          <tr v-for="s in sheets" :key="s.id" class="sheet-row" @click="router.push(`/sheets/${s.id}`)">
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

.result-count {
  color: #666;
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
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
</style>
