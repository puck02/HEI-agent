import { reactive, watch } from 'vue'

const STORAGE_KEY = 'hei-chat-state'

const defaultMessages = [
  { role: 'assistant', content: '你好！我是 Kitty 健康管家 🎀 有什么可以帮你的吗？' },
]

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed.messages) && parsed.messages.length > 0) {
        return parsed
      }
    }
  } catch {}
  return { messages: [...defaultMessages], inputText: '' }
}

const state = reactive(loadState())

watch(
  () => ({ messages: [...state.messages], inputText: state.inputText }),
  (val) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
    } catch {}
  },
  { deep: true }
)

export function useChatStore() {
  return {
    state,
    addMessage(msg) {
      state.messages.push(msg)
    },
    clearMessages() {
      state.messages = [...defaultMessages]
      state.inputText = ''
    },
    clearMessagesSilent() {
      state.messages = []
      state.inputText = ''
    },
    setInputText(text) {
      state.inputText = text
    },
  }
}
