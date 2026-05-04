import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', name: 'Chat', component: () => import('../views/ChatView.vue') },
  { path: '/report', name: 'Report', component: () => import('../views/ReportView.vue') },
  { path: '/insights', name: 'Insights', component: () => import('../views/InsightsView.vue') },
  { path: '/medication', name: 'Medication', component: () => import('../views/MedicationView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
