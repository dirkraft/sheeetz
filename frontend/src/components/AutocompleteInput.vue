<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  fetchSuggestions: (query: string) => Promise<string[]>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const suggestions = ref<string[]>([])
const showDropdown = ref(false)
const activeIndex = ref(-1)
const inputRef = ref<HTMLInputElement | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput(e: Event) {
  const value = (e.target as HTMLInputElement).value
  emit('update:modelValue', value)
  activeIndex.value = -1
  debouncedFetch(value)
}

function debouncedFetch(query: string) {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!query.trim()) {
    suggestions.value = []
    showDropdown.value = false
    return
  }
  debounceTimer = setTimeout(async () => {
    try {
      const results = await props.fetchSuggestions(query)
      suggestions.value = results
      showDropdown.value = results.length > 0
    } catch {
      suggestions.value = []
      showDropdown.value = false
    }
  }, 200)
}

function selectSuggestion(value: string) {
  emit('update:modelValue', value)
  suggestions.value = []
  showDropdown.value = false
  activeIndex.value = -1
}

function onKeydown(e: KeyboardEvent) {
  if (!showDropdown.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, suggestions.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === 'Enter' && activeIndex.value >= 0) {
    e.preventDefault()
    selectSuggestion(suggestions.value[activeIndex.value])
  } else if (e.key === 'Escape') {
    showDropdown.value = false
    activeIndex.value = -1
  }
}

function onBlur() {
  // Delay to allow click on suggestion to fire first
  setTimeout(() => {
    showDropdown.value = false
    activeIndex.value = -1
  }, 150)
}

function onFocus() {
  if (suggestions.value.length > 0 && props.modelValue.trim()) {
    showDropdown.value = true
  }
}

onUnmounted(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <div class="autocomplete-wrapper">
    <input
      ref="inputRef"
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
      @focus="onFocus"
    />
    <ul v-if="showDropdown" class="autocomplete-dropdown">
      <li
        v-for="(item, index) in suggestions"
        :key="item"
        :class="{ active: index === activeIndex }"
        @mousedown.prevent="selectSuggestion(item)"
      >
        {{ item }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.autocomplete-wrapper {
  position: relative;
}

.autocomplete-wrapper input {
  width: 100%;
  padding: 0.35rem 0.5rem;
  background: #3a3a3a;
  border: 1px solid #666;
  border-radius: 4px;
  color: #eee;
  font-size: 0.85rem;
  box-sizing: border-box;
}

.autocomplete-wrapper input:focus {
  outline: none;
  border-color: #4285f4;
}

.autocomplete-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  background: #3a3a3a;
  border: 1px solid #666;
  border-top: none;
  border-radius: 0 0 4px 4px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
}

.autocomplete-dropdown li {
  padding: 0.35rem 0.5rem;
  color: #eee;
  font-size: 0.85rem;
  cursor: pointer;
}

.autocomplete-dropdown li:hover,
.autocomplete-dropdown li.active {
  background: #4285f4;
}
</style>
