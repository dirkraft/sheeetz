import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Library from './views/Library.vue'
import Sheets from './views/Sheets.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/library', component: Library },
  { path: '/sheets', component: Sheets },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
