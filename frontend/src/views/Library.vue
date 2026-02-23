<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getConfig, getSelectedFolders, removeFolder, type BackendType, type LibraryFolder } from '../api'
import FolderPicker from '../components/FolderPicker.vue'

const selectedFolders = ref<LibraryFolder[]>([])
const backends = ref<BackendType[]>([])
const showPicker = ref(false)
const loading = ref(true)
const error = ref('')

const selectedIds = computed(() => new Set(selectedFolders.value.map(f => f.backend_folder_id)))

onMounted(async () => {
  try {
    const [foldersData, configData] = await Promise.all([getSelectedFolders(), getConfig()])
    selectedFolders.value = foldersData.folders
    backends.value = configData.backends
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function handleRemove(id: number) {
  await removeFolder(id)
  selectedFolders.value = selectedFolders.value.filter(f => f.id !== id)
}

async function handleAdded() {
  const data = await getSelectedFolders()
  selectedFolders.value = data.folders
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
            <div>
              <span class="badge" :class="f.backend_type">{{ f.backend_type === 'local' ? 'Local' : 'Drive' }}</span>
              <strong>{{ f.folder_name }}</strong>
              <small class="folder-path">{{ f.folder_path }}</small>
            </div>
            <button class="remove-btn" @click="handleRemove(f.id)">Remove</button>
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
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid #eee;
}

.folder-path {
  display: block;
  color: #888;
  font-size: 0.85rem;
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
