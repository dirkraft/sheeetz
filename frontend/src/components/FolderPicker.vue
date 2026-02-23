<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { browseFolders, addFolder, type BrowseFolder, type BackendType } from '../api'

const props = defineProps<{ selectedIds: Set<string>; backends: BackendType[] }>()
const emit = defineEmits<{
  (e: 'added'): void
  (e: 'close'): void
}>()

const activeBackend = ref<BackendType>(props.backends[0])
const folders = ref<BrowseFolder[]>([])
const loading = ref(false)
const error = ref('')
const breadcrumbs = ref<{ id: string; name: string }[]>([])

function defaultBreadcrumb(): { id: string; name: string } {
  return activeBackend.value === 'local'
    ? { id: '', name: 'Home' }
    : { id: 'root', name: 'My Drive' }
}

async function navigate(folderId: string, folderName?: string) {
  loading.value = true
  error.value = ''
  try {
    const data = await browseFolders(activeBackend.value, folderId)
    folders.value = data.folders

    if (!folderId || folderId === 'root') {
      breadcrumbs.value = [{ id: folderId, name: folderName || defaultBreadcrumb().name }]
    } else {
      const idx = breadcrumbs.value.findIndex(b => b.id === folderId)
      if (idx >= 0) {
        breadcrumbs.value = breadcrumbs.value.slice(0, idx + 1)
      } else {
        breadcrumbs.value.push({ id: folderId, name: folderName || folderId })
      }
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function switchBackend(backend: BackendType) {
  activeBackend.value = backend
  const def = defaultBreadcrumb()
  breadcrumbs.value = [def]
  await navigate(def.id, def.name)
}

async function selectFolder(folder: BrowseFolder) {
  try {
    await addFolder(activeBackend.value, folder.id, folder.name)
    emit('added')
  } catch (e: any) {
    error.value = e.message
  }
}

onMounted(() => {
  const def = defaultBreadcrumb()
  breadcrumbs.value = [def]
  navigate(def.id, def.name)
})
</script>

<template>
  <div class="picker-overlay">
    <div class="picker">
      <div class="picker-header">
        <span>Add Folder</span>
        <button class="close-btn" @click="emit('close')">Close</button>
      </div>

      <div v-if="backends.length > 1" class="backend-tabs">
        <button
          v-for="b in backends"
          :key="b"
          :class="['tab', { active: activeBackend === b }]"
          @click="switchBackend(b)"
        >{{ b === 'local' ? 'Local' : 'Google Drive' }}</button>
      </div>

      <div class="breadcrumbs">
        <span
          v-for="(crumb, i) in breadcrumbs"
          :key="crumb.id"
          class="crumb"
          @click="navigate(crumb.id, crumb.name)"
        >
          <span v-if="i > 0"> / </span>
          {{ crumb.name }}
        </span>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <div v-if="loading" class="loading">Loading...</div>
      <div v-else class="folder-list">
        <div v-if="folders.length === 0" class="empty">No subfolders here.</div>
        <div v-for="folder in folders" :key="folder.id" class="folder-row">
          <span class="folder-name" @click="navigate(folder.id, folder.name)">
            {{ folder.name }}
          </span>
          <button
            v-if="selectedIds.has(folder.id)"
            class="selected-btn"
            disabled
          >Added</button>
          <button
            v-else
            class="select-btn"
            @click.stop="selectFolder(folder)"
          >Select</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.picker {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 540px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #eee;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.25rem 0.75rem;
  cursor: pointer;
}

.backend-tabs {
  display: flex;
  border-bottom: 1px solid #eee;
}

.tab {
  flex: 1;
  padding: 0.6rem;
  border: none;
  background: #f9f9f9;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
  color: #666;
}

.tab.active {
  background: white;
  color: #4285f4;
  border-bottom: 2px solid #4285f4;
}

.breadcrumbs {
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  color: #666;
  border-bottom: 1px solid #f0f0f0;
}

.crumb {
  cursor: pointer;
}

.crumb:hover {
  color: #4285f4;
}

.folder-list {
  overflow-y: auto;
  flex: 1;
}

.folder-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid #f5f5f5;
}

.folder-name {
  cursor: pointer;
  flex: 1;
}

.folder-name:hover {
  color: #4285f4;
}

.select-btn {
  background: #4285f4;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.75rem;
  cursor: pointer;
  font-size: 0.85rem;
}

.select-btn:hover {
  background: #3367d6;
}

.selected-btn {
  background: #e8f5e9;
  color: #2e7d32;
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.75rem;
  font-size: 0.85rem;
}

.loading, .empty {
  padding: 2rem;
  text-align: center;
  color: #999;
}

.error {
  padding: 0.5rem 1rem;
  color: #d32f2f;
  font-size: 0.85rem;
}
</style>
