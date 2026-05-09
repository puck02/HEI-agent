<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = [
  { path: '/chat', label: '对话' },
  { path: '/report', label: '日报' },
  { path: '/insights', label: '洞察' },
  { path: '/medication', label: '用药' },
  { path: '/monitor', label: '监控' },
]

const currentPath = computed(() => route.path)
</script>

<template>
  <nav class="relative z-30 flex border-t border-kitty-100 bg-white shadow-inner overflow-visible">
    <button
      v-for="tab in tabs"
      :key="tab.path"
      @click="router.push(tab.path)"
      class="flex-1 flex flex-col items-center py-2 transition-colors relative"
      :class="currentPath === tab.path ? 'text-kitty-500' : 'text-gray-400'"
    >
      <!-- Active indicator: bow decoration -->
      <img
        v-if="currentPath === tab.path"
        src="/images/bow.png"
        alt=""
        class="absolute -top-2 w-5 h-5 object-contain"
      />

      <!-- Chat icon -->
      <svg v-if="tab.path === '/chat'" class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
      </svg>

      <!-- Report icon -->
      <svg v-else-if="tab.path === '/report'" class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
      </svg>

      <!-- Insights icon -->
      <svg v-else-if="tab.path === '/insights'" class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
      </svg>

      <!-- Medication icon -->
      <svg v-else-if="tab.path === '/medication'" class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3l-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3l-3 3"/>
      </svg>

      <!-- Monitor icon -->
      <svg v-else-if="tab.path === '/monitor'" class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 3v18h18"/>
        <path stroke-linecap="round" stroke-linejoin="round" d="M7 15l3-3 3 2 5-7"/>
        <circle cx="18" cy="7" r="1.5" fill="currentColor" stroke="none"/>
      </svg>

      <span class="text-[10px] mt-0.5 font-medium">{{ tab.label }}</span>
    </button>
  </nav>
</template>
