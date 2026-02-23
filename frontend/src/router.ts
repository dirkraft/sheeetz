import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Library from './views/Library.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/library', component: Library },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
