<script setup>
import NavBar from './components/NavBar.vue'
import TabBar from './components/TabBar.vue'
import SessionSidebar from './components/SessionSidebar.vue'
import { useSessionStore } from './stores/session'
import { useChatStore } from './stores/chat'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

const handleNewSession = () => {
  chatStore.clearMessages()
  sessionStore.clearCurrentSession()
  sessionStore.closeSidebar()
}

const handleSelectSession = async (sessionId) => {
  const session = await sessionStore.loadSession(sessionId)
  if (!session) return

  const messages = session.messages || []
  chatStore.clearMessagesSilent()
  if (messages.length === 0) {
    chatStore.addMessage({ role: 'assistant', content: '你好！我是 Kitty 健康管家 🎀 有什么可以帮你的吗？' })
  } else {
    for (const msg of messages) {
      chatStore.addMessage({ role: msg.role, content: msg.content })
    }
  }
  sessionStore.closeSidebar()
}
</script>

<template>
  <div class="flex flex-col h-screen max-w-lg mx-auto bg-kitty-50 shadow-xl overflow-hidden relative">
    <!-- Subtle background image -->
    <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: url('/images/background01.png'); background-size: cover; background-position: center;"></div>

    <!-- Session sidebar (global) -->
    <SessionSidebar
      :visible="sessionStore.state.sidebarVisible"
      @close="sessionStore.closeSidebar()"
      @new-session="handleNewSession"
      @select-session="handleSelectSession"
    />

    <NavBar
      @toggle-sessions="sessionStore.toggleSidebar()"
      @new-session="handleNewSession"
    />
    <main class="flex-1 overflow-hidden relative z-10">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <TabBar />
  </div>
</template>
