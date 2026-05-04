<script setup>
import { onMounted } from 'vue'
import { useSessionStore } from '../stores/session'

const props = defineProps({
  visible: Boolean,
})

const emit = defineEmits(['close', 'select-session', 'new-session'])

const sessionStore = useSessionStore()

onMounted(() => {
  sessionStore.fetchSessions()
})

const handleNewSession = () => {
  emit('new-session')
}

const handleSelectSession = (sessionId) => {
  emit('select-session', sessionId)
}

const handleDeleteSession = async (e, sessionId) => {
  e.stopPropagation()
  await sessionStore.deleteSession(sessionId)
}

const formatDate = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay}天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <Transition name="sidebar">
    <div v-if="visible" class="fixed inset-0 z-50 flex">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>

      <!-- Sidebar panel -->
      <div class="relative w-72 max-w-[80vw] bg-white h-full flex flex-col shadow-xl">
        <!-- Header -->
        <div class="bg-gradient-to-r from-kitty-400 to-kitty-500 text-white px-4 py-4 flex items-center justify-between">
          <h2 class="text-base font-bold">对话列表</h2>
          <button
            @click="$emit('close')"
            class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- New session button -->
        <div class="p-3 border-b border-kitty-100">
          <button
            @click="handleNewSession"
            class="w-full flex items-center gap-2 px-4 py-2.5 rounded-xl border-2 border-dashed border-kitty-200 text-kitty-500 hover:bg-kitty-50 hover:border-kitty-300 transition text-sm font-medium"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            新建对话
          </button>
        </div>

        <!-- Session list -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="sessionStore.state.loading" class="p-4 text-center text-kitty-400 text-sm">
            加载中...
          </div>
          <div v-else-if="sessionStore.state.sessions.length === 0" class="p-4 text-center text-kitty-300 text-sm">
            暂无对话记录
          </div>
          <div v-else class="py-1">
            <div
              v-for="session in sessionStore.state.sessions"
              :key="session.session_id"
              @click="handleSelectSession(session.session_id)"
              class="group flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-kitty-50 transition relative"
              :class="{ 'bg-kitty-50 border-l-3 border-kitty-400': session.session_id === sessionStore.state.currentSessionId }"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-800 truncate">
                  {{ session.title }}
                </p>
                <p class="text-xs text-gray-400 mt-0.5">
                  {{ session.message_count }} 条消息 · {{ formatDate(session.updated_at) }}
                </p>
              </div>
              <button
                @click="handleDeleteSession($event, session.session_id)"
                class="opacity-0 group-hover:opacity-100 w-7 h-7 flex items-center justify-center rounded-full hover:bg-red-50 text-gray-300 hover:text-red-400 transition shrink-0"
                title="删除对话"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="p-3 border-t border-kitty-100 text-center">
          <p class="text-xs text-kitty-300">Kitty 健康管家 🎀</p>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.sidebar-enter-active,
.sidebar-leave-active {
  transition: opacity 0.2s ease;
}
.sidebar-enter-active > div:last-child,
.sidebar-leave-active > div:last-child {
  transition: transform 0.25s ease;
}
.sidebar-enter-from,
.sidebar-leave-to {
  opacity: 0;
}
.sidebar-enter-from > div:last-child {
  transform: translateX(-100%);
}
.sidebar-leave-to > div:last-child {
  transform: translateX(-100%);
}
</style>
