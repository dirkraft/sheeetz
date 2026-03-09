<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type ThemePref = 'system' | 'light' | 'dark'

const THEME_KEY = 'sheeetz.theme'
const PDF_FILTER_KEY = 'sheeetz.pdf-filter'
const themePref = ref<ThemePref>('system')
const pdfFilterEnabled = ref(false)

let mediaQuery: MediaQueryList | null = null

function readSavedTheme(): ThemePref {
  const raw = localStorage.getItem(THEME_KEY)
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
}

const resolvedTheme = computed<'light' | 'dark'>(() => {
  if (themePref.value === 'system') {
    return mediaQuery?.matches ? 'dark' : 'light'
  }
  return themePref.value
})

function applyTheme() {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme.value
  root.style.colorScheme = resolvedTheme.value
  applyPdfFilter()
}

function applyPdfFilter() {
  const root = document.documentElement
  if (pdfFilterEnabled.value && resolvedTheme.value === 'dark') {
    root.dataset.pdfFilter = '1'
  } else {
    delete root.dataset.pdfFilter
  }
}

function onSystemThemeChange() {
  if (themePref.value === 'system') applyTheme()
}

watch(themePref, (value) => {
  localStorage.setItem(THEME_KEY, value)
  applyTheme()
})

watch(pdfFilterEnabled, (value) => {
  localStorage.setItem(PDF_FILTER_KEY, value ? '1' : '0')
  applyPdfFilter()
})

onMounted(() => {
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', onSystemThemeChange)
  themePref.value = readSavedTheme()
  pdfFilterEnabled.value = localStorage.getItem(PDF_FILTER_KEY) === '1'
  applyTheme()
})

onUnmounted(() => {
  mediaQuery?.removeEventListener('change', onSystemThemeChange)
})
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
      <div class="theme-control">
        <label>
          Theme
          <select v-model="themePref" class="theme-select" aria-label="Theme">
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label v-if="resolvedTheme === 'dark'" class="pdf-filter-label">
          <input type="checkbox" v-model="pdfFilterEnabled" />
          Invert PDF
        </label>
      </div>
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

.theme-control {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
  color: var(--c-text-muted);
}

.theme-control label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.pdf-filter-label {
  font-size: 0.8rem;
  color: var(--c-text-muted);
  cursor: pointer;
}

.theme-select {
  background: var(--c-surface);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  border-radius: 4px;
  padding: 0.2rem 0.45rem;
}

main {
  padding: 1rem;
}
</style>
