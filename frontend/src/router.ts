import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Library from './views/Library.vue'
import Sheets from './views/Sheets.vue'
import SheetViewer from './views/SheetViewer.vue'
import Admin from './views/Admin.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/library', component: Library },
  { path: '/sheets', component: Sheets },
  { path: '/sheets/:id', component: SheetViewer },
  { path: '/admin', component: Admin },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
