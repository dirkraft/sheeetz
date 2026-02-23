<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getMe } from '../api'

const user = ref<{ id: number; email: string; name: string } | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    user.value = await getMe()
  } catch {
    user.value = null
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="home">
    <h1>Sheeetz</h1>
    <p>Sheet music filer &amp; viewer</p>

    <div v-if="loading">Loading...</div>
    <div v-else-if="user">
      <p>Signed in as <strong>{{ user.name }}</strong> ({{ user.email }})</p>
      <router-link to="/library">Go to Library</router-link>
      <br><br>
      <a href="/api/auth/logout" class="logout-btn">Logout</a>
    </div>
    <div v-else>
      <a href="/api/auth/login" class="login-btn">Login with Google</a>
    </div>
  </div>
</template>

<style scoped>
.home {
  max-width: 480px;
  margin: 4rem auto;
  text-align: center;
}

.login-btn {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  background: #4285f4;
  color: white;
  text-decoration: none;
  border-radius: 4px;
  font-weight: 500;
}

.login-btn:hover {
  background: #3367d6;
}

.logout-btn {
  color: #666;
  text-decoration: underline;
  font-size: 0.9rem;
}
</style>
