<script setup>
import { ref, nextTick, onMounted } from 'vue'
import ChatBubble from '../components/ChatBubble.vue'
import { sendMessage } from '../api'
import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'

const store = useChatStore()
const sessionStore = useSessionStore()
const loading = ref(false)
const chatBox = ref(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

onMounted(() => scrollToBottom())

const ensureSession = async () => {
  if (sessionStore.state.currentSessionId) {
    return sessionStore.state.currentSessionId
  }
  const session = await sessionStore.createSession('新对话')
  return session?.session_id || null
}

const handleSend = async () => {
  const text = store.state.inputText.trim()
  if (!text || loading.value) return

  const sessionId = await ensureSession()
  if (!sessionId) return

  store.addMessage({ role: 'user', content: text })
  store.setInputText('')
  scrollToBottom()
  loading.value = true

  // Auto-title from first user message
  const session = sessionStore.state.sessions.find(s => s.session_id === sessionId)
  if (session && session.title === '新对话') {
    const newTitle = text.length > 20 ? text.slice(0, 20) + '...' : text
    sessionStore.updateSessionTitle(sessionId, newTitle)
  }

  try {
    const data = await sendMessage(text, sessionId)
    store.addMessage({
      role: 'assistant',
      content: data.response,
      intent: data.tool_calls_made?.join(', ') || data.intent,
      latency: data.latency_ms,
      references: data.references || [],
      traceId: data.trace_id,
    })
    store.addTraceTurn({
      trace_id: data.trace_id,
      session_id: data.session_id || sessionId,
      message: text,
      answer: data.response,
      latency_ms: data.latency_ms,
      iterations: data.iterations,
      tool_calls_made: data.tool_calls_made || [],
      needs_confirmation: data.needs_confirmation,
      pending_tool: data.pending_tool,
      trace: data.trace || [],
    })
    sessionStore.incrementMessageCount(sessionId)
  } catch {
    store.addMessage({
      role: 'assistant',
      content: '抱歉，暂时无法连接到服务，请稍后再试。',
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const quickQuestions = [
  '最近睡眠不好怎么办？',
  '帮我制定运动计划',
  '感冒了吃什么药好？',
]
</script>

<template>
  <div class="flex flex-col h-full bg-kitty-50 relative">
    <!-- Subtle background image -->
    <div class="absolute inset-0 opacity-[0.08] pointer-events-none" style="background-image: url('/images/background05.png'); background-size: cover; background-position: center;"></div>

    <div ref="chatBox" class="flex-1 overflow-y-auto p-4 space-y-1 relative z-10">
      <ChatBubble
        v-for="(msg, i) in store.state.messages"
        :key="i"
        :role="msg.role"
        :content="msg.content"
        :intent="msg.intent"
        :latency="msg.latency"
        :references="msg.references"
      />
      <div v-if="loading" class="flex items-center gap-2 text-kitty-400 text-sm pl-10">
        <span class="animate-bounce">🎀</span> 思考中...
      </div>
    </div>

    <div v-if="store.state.messages.length <= 1" class="px-4 pb-2 flex flex-wrap gap-2">
      <button
        v-for="q in quickQuestions"
        :key="q"
        @click="store.setInputText(q)"
        class="text-xs px-3 py-1.5 rounded-full border border-kitty-200 text-kitty-600 bg-white hover:bg-kitty-50 transition shadow-kitty-sm"
      >
        {{ q }}
      </button>
    </div>

    <div class="p-3 border-t border-kitty-100 bg-white flex gap-2">
      <input
        :value="store.state.inputText"
        @input="store.setInputText($event.target.value)"
        @keyup.enter="handleSend"
        placeholder="输入你的健康问题..."
        class="flex-1 px-4 py-2 rounded-full border border-kitty-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300 bg-kitty-50"
      />
      <button
        @click="handleSend"
        :disabled="loading || !store.state.inputText.trim()"
        class="w-10 h-10 rounded-full bg-gradient-to-br from-kitty-400 to-kitty-500 text-white flex items-center justify-center disabled:opacity-40 hover:shadow-kitty transition shadow-kitty-sm"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  </div>
</template>
