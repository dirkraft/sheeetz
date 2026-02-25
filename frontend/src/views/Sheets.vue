<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getSheets, getSelectedFolders, type SheetRecord, type LibraryFolder } from '../api'

const router = useRouter()

const sheets = ref<SheetRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50

const filterFilename = ref('')
const filterFolderId = ref<number | null>(null)
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
    const data = await getSheets({
      filename: filterFilename.value || undefined,
      folder_id: filterFolderId.value ?? undefined,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
      page: page.value,
      page_size: pageSize,
    })
    sheets.value = data.sheets
    total.value = data.total
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
watch([filterFolderId, sortBy, sortDir], () => {
  page.value = 1
  load()
})
watch(page, load)

onMounted(async () => {
  const foldersData = await getSelectedFolders()
  folders.value = foldersData.folders
  await load()
})

const totalPages = ref(0)
watch(total, (t) => {
  totalPages.value = Math.ceil(t / pageSize)
})

function toggleSort(col: string) {
  if (sortBy.value === col) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = col
    sortDir.value = 'asc'
  }
}

function sortIndicator(col: string) {
  if (sortBy.value !== col) return ''
  return sortDir.value === 'asc' ? ' ↑' : ' ↓'
}
</script>

<template>
  <div class="sheets">
    <h1>Sheet Music</h1>

    <div class="filters">
      <input
        v-model="filterFilename"
        type="text"
        placeholder="Search by filename..."
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
      <p class="result-count">{{ total }} sheet{{ total !== 1 ? 's' : '' }} found</p>

      <table class="sheets-table">
        <thead>
          <tr>
            <th @click="toggleSort('filename')" class="sortable">
              Filename{{ sortIndicator('filename') }}
            </th>
            <th @click="toggleSort('folder_path')" class="sortable">
              Folder{{ sortIndicator('folder_path') }}
            </th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sheets" :key="s.id" class="sheet-row" @click="router.push(`/sheets/${s.id}`)">
            <td>{{ s.filename }}</td>
            <td class="folder-cell">{{ s.folder_path || '—' }}</td>
            <td>
              <span class="badge" :class="s.backend_type">
                {{ s.backend_type === 'local' ? 'Local' : 'Drive' }}
              </span>
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
  max-width: 900px;
  margin: 2rem auto;
  padding: 0 1rem;
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

.folder-cell {
  color: #666;
  font-size: 0.9rem;
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
