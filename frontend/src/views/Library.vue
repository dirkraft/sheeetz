<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getConfig, getSelectedFolders, getScanStatus, removeFolder, scanFolder, type BackendType, type LibraryFolder, type ScanStatus } from '../api'
import FolderPicker from '../components/FolderPicker.vue'

const selectedFolders = ref<LibraryFolder[]>([])
const backends = ref<BackendType[]>([])
const showPicker = ref(false)
const loading = ref(true)
const error = ref('')
const scanStates = ref<Map<number, ScanStatus>>(new Map())

const selectedIds = computed(() => new Set(selectedFolders.value.map(f => f.backend_folder_id)))

let pollTimer: ReturnType<typeof setInterval> | null = null

function isScanning(id: number): boolean {
  return scanStates.value.get(id)?.status === 'scanning'
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollActiveScan, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function hasActiveScans(): boolean {
  for (const s of scanStates.value.values()) {
    if (s.status === 'scanning') return true
  }
  return false
}

async function pollActiveScan() {
  const scanning = [...scanStates.value.entries()].filter(([, s]) => s.status === 'scanning')
  if (!scanning.length) {
    stopPolling()
    return
  }
  await Promise.all(
    scanning.map(async ([id]) => {
      try {
        const status = await getScanStatus(id)
        scanStates.value = new Map([...scanStates.value, [id, status]])
      } catch {
        // ignore polling errors
      }
    })
  )
  // Stop polling if no more active scans
  if (!hasActiveScans()) stopPolling()
}

onMounted(async () => {
  try {
    const [foldersData, configData] = await Promise.all([getSelectedFolders(), getConfig()])
    selectedFolders.value = foldersData.folders
    backends.value = configData.backends

    // Check for any in-progress scans
    await Promise.all(
      foldersData.folders.map(async (f: LibraryFolder) => {
        try {
          const status = await getScanStatus(f.id)
          if (status.status !== 'idle') {
            scanStates.value = new Map([...scanStates.value, [f.id, status]])
          }
        } catch {
          // ignore
        }
      })
    )
    if (hasActiveScans()) startPolling()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopPolling()
})

async function handleRemove(id: number) {
  await removeFolder(id)
  selectedFolders.value = selectedFolders.value.filter(f => f.id !== id)
  scanStates.value.delete(id)
  scanStates.value = new Map(scanStates.value)
}

async function handleAdded() {
  const data = await getSelectedFolders()
  selectedFolders.value = data.folders
}

async function handleScan(id: number) {
  try {
    const status = await scanFolder(id)
    scanStates.value = new Map([...scanStates.value, [id, status]])
    if (status.status === 'scanning') startPolling()
  } catch (e: any) {
    error.value = e.message
  }
}
</script>

<template>
  <div class="library">
    <h1>Library</h1>

    <div v-if="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <section class="folders-section">
        <h2>Music Folders</h2>
        <div v-if="selectedFolders.length === 0" class="empty">
          <p>No folders selected yet. Add local or Google Drive folders containing your sheet music.</p>
        </div>
        <ul v-else class="folder-list">
          <li v-for="f in selectedFolders" :key="f.id" class="folder-item">
            <div class="folder-info">
              <div>
                <span class="badge" :class="f.backend_type">{{ f.backend_type === 'local' ? 'Local' : 'Drive' }}</span>
                <strong>{{ f.folder_name }}</strong>
                <small class="folder-path">{{ f.folder_path }}</small>
              </div>
              <div v-if="scanStates.has(f.id)" class="scan-status">
                <template v-if="scanStates.get(f.id)!.status === 'scanning'">
                  <span class="scan-progress">
                    Scanning{{ scanStates.get(f.id)!.total_count != null
                      ? ` (${scanStates.get(f.id)!.processed}/${scanStates.get(f.id)!.total_count})`
                      : '...' }}
                  </span>
                  <span v-if="scanStates.get(f.id)!.current_file" class="scan-file">
                    {{ scanStates.get(f.id)!.current_file }}
                  </span>
                </template>
                <template v-else-if="scanStates.get(f.id)!.status === 'complete'">
                  <span class="scan-result">
                    {{ scanStates.get(f.id)!.new_count }} new, {{ scanStates.get(f.id)!.total_count }} total PDFs
                  </span>
                </template>
                <template v-else-if="scanStates.get(f.id)!.status === 'error'">
                  <span class="scan-error">
                    Scan failed: {{ scanStates.get(f.id)!.error }}
                  </span>
                </template>
              </div>
            </div>
            <div class="folder-actions">
              <button class="scan-btn" :disabled="isScanning(f.id)" @click="handleScan(f.id)">
                {{ isScanning(f.id) ? 'Scanning...' : 'Scan' }}
              </button>
              <button class="remove-btn" @click="handleRemove(f.id)">Remove</button>
            </div>
          </li>
        </ul>
        <button class="add-btn" @click="showPicker = true">Add Folder</button>
      </section>

      <FolderPicker
        v-if="showPicker"
        :selectedIds="selectedIds"
        :backends="backends"
        @added="handleAdded"
        @close="showPicker = false"
      />
    </template>
  </div>
</template>

<style scoped>
.library {
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.folders-section {
  margin: 1.5rem 0;
}

.folder-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
}

.folder-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.75rem 0;
  border-bottom: 1px solid #eee;
}

.folder-info {
  flex: 1;
  min-width: 0;
}

.folder-path {
  display: block;
  color: #888;
  font-size: 0.85rem;
}

.folder-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
  margin-left: 1rem;
}

.scan-status {
  margin-top: 0.25rem;
}

.scan-progress {
  display: block;
  color: #1976d2;
  font-size: 0.8rem;
  font-weight: 500;
}

.scan-file {
  display: block;
  color: #888;
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.scan-result {
  display: block;
  color: #4caf50;
  font-size: 0.8rem;
}

.scan-error {
  display: block;
  color: #d32f2f;
  font-size: 0.8rem;
}

.scan-btn {
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.75rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.scan-btn:hover:not(:disabled) {
  background: #388e3c;
}

.scan-btn:disabled {
  background: #a5d6a7;
  cursor: default;
}

.remove-btn {
  background: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.25rem 0.75rem;
  cursor: pointer;
  color: #666;
  font-size: 0.85rem;
}

.remove-btn:hover {
  border-color: #d32f2f;
  color: #d32f2f;
}

.add-btn {
  background: #4285f4;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  cursor: pointer;
  margin-top: 0.5rem;
}

.add-btn:hover {
  background: #3367d6;
}

.empty {
  color: #666;
  margin: 1rem 0;
}

.badge {
  display: inline-block;
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  margin-right: 0.4rem;
  font-weight: 600;
  text-transform: uppercase;
  vertical-align: middle;
}

.badge.local {
  background: #e3f2fd;
  color: #1565c0;
}

.badge.gdrive {
  background: #fce4ec;
  color: #c62828;
}

.error {
  color: #d32f2f;
}
</style>
