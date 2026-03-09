<script setup lang="ts">
import ThemeControl from './components/ThemeControl.vue'
</script>

<template>
  <div id="app">
    <nav>
      <div class="nav-links">
        <router-link to="/">Home</router-link>
        <router-link to="/library">Library</router-link>
        <router-link to="/sheets">Sheets</router-link>
        <router-link to="/admin">Admin</router-link>
      </div>
      <ThemeControl />
    </nav>
    <main>
      <router-view v-slot="{ Component }">
        <keep-alive include="Sheets">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--c-border);
}

.nav-links {
  display: flex;
  gap: 1rem;
}

nav a {
  text-decoration: none;
  color: var(--c-text);
  font-weight: 500;
}

nav a.router-link-active {
  color: var(--c-link);
}

main {
  padding: 1rem;
}
</style>
