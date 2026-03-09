<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type ThemePref = 'system' | 'light' | 'dark'
type PdfFilter = 'none' | 'sepia' | 'invert'

const THEME_KEY = 'sheeetz.theme'
const PDF_FILTER_KEY = 'sheeetz.pdf-filter'

const themePref = ref<ThemePref>('system')
const pdfFilter = ref<PdfFilter>('none')
const open = ref(false)

let mediaQuery: MediaQueryList | null = null

function readSavedTheme(): ThemePref {
  const raw = localStorage.getItem(THEME_KEY)
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
}

function readSavedFilter(): PdfFilter {
  const raw = localStorage.getItem(PDF_FILTER_KEY)
  return raw === 'sepia' || raw === 'invert' ? raw : 'none'
}

const resolvedTheme = computed<'light' | 'dark'>(() => {
  if (themePref.value === 'system') return mediaQuery?.matches ? 'dark' : 'light'
  return themePref.value
})

function applyAll() {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme.value
  root.style.colorScheme = resolvedTheme.value
  const activeFilter = resolvedTheme.value === 'dark' ? pdfFilter.value : 'none'
  if (activeFilter === 'none') {
    delete root.dataset.pdfFilter
  } else {
    root.dataset.pdfFilter = activeFilter
  }
}

watch(themePref, (val) => { localStorage.setItem(THEME_KEY, val); applyAll() })
watch(pdfFilter, (val) => { localStorage.setItem(PDF_FILTER_KEY, val); applyAll() })

function onSystemThemeChange() {
  if (themePref.value === 'system') applyAll()
}

function onDocClick(e: MouseEvent) {
  const el = document.querySelector('.theme-menu')
  if (el && !el.contains(e.target as Node)) open.value = false
}

onMounted(() => {
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', onSystemThemeChange)
  themePref.value = readSavedTheme()
  pdfFilter.value = readSavedFilter()
  applyAll()
  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  mediaQuery?.removeEventListener('change', onSystemThemeChange)
  document.removeEventListener('click', onDocClick)
})

const themeLabel = computed(() =>
  themePref.value === 'system' ? 'System' : themePref.value === 'light' ? 'Light' : 'Dark'
)
</script>

<template>
  <div class="theme-menu">
    <button class="theme-btn" @click.stop="open = !open" aria-label="Theme settings">
      {{ themeLabel }}
      <span class="caret">▾</span>
    </button>
    <div v-if="open" class="theme-panel" @click.stop>
      <div class="panel-section">
        <div class="section-label">Theme</div>
        <label v-for="opt in (['system', 'light', 'dark'] as ThemePref[])" :key="opt" class="option-row">
          <input type="radio" :value="opt" v-model="themePref" />
          {{ opt.charAt(0).toUpperCase() + opt.slice(1) }}
        </label>
      </div>
      <div v-if="resolvedTheme === 'dark'" class="panel-section">
        <div class="section-label">PDF Filter</div>
        <label v-for="opt in (['none', 'sepia', 'invert'] as PdfFilter[])" :key="opt" class="option-row">
          <input type="radio" :value="opt" v-model="pdfFilter" />
          {{ opt.charAt(0).toUpperCase() + opt.slice(1) }}
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.theme-menu {
  position: relative;
}

.theme-btn {
  background: none;
  border: 1px solid var(--c-border);
  color: var(--c-text-muted);
  border-radius: 4px;
  padding: 0.25rem 0.6rem;
  font-size: 0.85rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.theme-btn:hover {
  background: var(--c-surface);
}

.caret {
  font-size: 0.7rem;
  opacity: 0.7;
}

.theme-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 6px;
  padding: 0.5rem;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
}

.panel-section {
  padding: 0.3rem 0.2rem;
}

.panel-section + .panel-section {
  border-top: 1px solid var(--c-border);
  margin-top: 0.3rem;
  padding-top: 0.5rem;
}

.section-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-text-muted);
  margin-bottom: 0.3rem;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.2rem 0.1rem;
  font-size: 0.85rem;
  color: var(--c-text);
  cursor: pointer;
  border-radius: 3px;
}

.option-row:hover {
  background: var(--c-border);
}
</style>
