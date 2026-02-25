<script setup lang="ts">
import { ref } from 'vue'
import { clearIndex } from '../api'

const clearing = ref(false)
const result = ref<string | null>(null)
const error = ref('')

async function handleClearIndex() {
  if (!confirm('Clear the entire sheet music index? You can re-scan folders to rebuild it.')) return
  clearing.value = true
  error.value = ''
  result.value = null
  try {
    const data = await clearIndex()
    result.value = `Cleared ${data.deleted} sheet${data.deleted !== 1 ? 's' : ''} from the index.`
  } catch (e: any) {
    error.value = e.message
  } finally {
    clearing.value = false
  }
}
</script>

<template>
  <div class="admin">
    <h1>Admin</h1>

    <section class="admin-section">
      <h2>Index Management</h2>
      <p class="description">Clear all indexed sheet music. Folder selections are kept — re-scan to rebuild the index.</p>
      <button class="danger-btn" :disabled="clearing" @click="handleClearIndex">
        {{ clearing ? 'Clearing...' : 'Clear Index' }}
      </button>
      <p v-if="result" class="success">{{ result }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </div>
</template>

<style scoped>
.admin {
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.admin-section {
  margin: 1.5rem 0;
  padding: 1rem;
  border: 1px solid #eee;
  border-radius: 6px;
}

.description {
  color: #666;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.danger-btn {
  background: #d32f2f;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  cursor: pointer;
}

.danger-btn:hover:not(:disabled) {
  background: #b71c1c;
}

.danger-btn:disabled {
  background: #ef9a9a;
  cursor: default;
}

.success {
  color: #4caf50;
  margin-top: 0.75rem;
}

.error {
  color: #d32f2f;
  margin-top: 0.75rem;
}
</style>
