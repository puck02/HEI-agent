import { reactive, watch } from 'vue'

const STORAGE_KEY = 'hei-chat-state'

const defaultMessages = [
  { role: 'assistant', content: '你好！我是 Kitty 健康管家 🎀 有什么可以帮你的吗？' },
]

const sampleTrace = [
  {
    ts: new Date(Date.now() - 5200).toISOString(),
    type: 'agent',
    phase: 'start',
    name: 'ChatAgent.chat',
    status: 'ok',
    input: { user_id: 'demo_user', session_id: 'demo_session', message: '高血压患者饮食需要注意什么？' },
    metadata: { trace_id: 'sample_trace' },
  },
  {
    ts: new Date(Date.now() - 4200).toISOString(),
    type: 'llm_call',
    phase: 'react_iteration_1',
    name: 'tool_selection',
    status: 'ok',
    duration_ms: 1180,
    metadata: { tool_choice: 'auto', tools_available: 12 },
  },
  {
    ts: new Date(Date.now() - 2800).toISOString(),
    type: 'tool_call',
    phase: 'react_iteration_1',
    name: 'search_health',
    status: 'ok',
    duration_ms: 346,
    input: { query: '高血压 低盐饮食 钠摄入 控制建议' },
    output_preview: '命中健康知识库：高血压患者应控制钠盐摄入，增加蔬果和全谷物，限制高脂高糖饮食。',
    metadata: { read_or_write: 'read', parallel_batch_size: 1 },
  },
  {
    ts: new Date(Date.now() - 900).toISOString(),
    type: 'llm_call',
    phase: 'synthesis',
    name: 'final_answer',
    status: 'ok',
    duration_ms: 2720,
    output_preview: '综合检索结果，为用户生成高血压饮食建议。',
  },
]

function defaultTraceTurn() {
  return {
    trace_id: 'sample_trace',
    session_id: 'demo_session',
    message: '高血压患者饮食需要注意什么？',
    answer: '建议控制钠盐摄入、增加蔬菜水果和全谷物、少吃高脂高糖食物。',
    latency_ms: 5300,
    iterations: 1,
    tool_calls_made: ['read:search_health'],
    trace: sampleTrace,
    created_at: new Date().toISOString(),
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const normalized = {
        messages: Array.isArray(parsed.messages) && parsed.messages.length > 0 ? parsed.messages : [...defaultMessages],
        inputText: parsed.inputText || '',
        traceTurns: Array.isArray(parsed.traceTurns) ? parsed.traceTurns : [defaultTraceTurn()],
      }
      if (normalized.traceTurns.length === 0) normalized.traceTurns = [defaultTraceTurn()]
      return normalized
    }
  } catch {}
  return { messages: [...defaultMessages], inputText: '', traceTurns: [defaultTraceTurn()] }
}

const state = reactive(loadState())

watch(
  () => ({ messages: [...state.messages], inputText: state.inputText, traceTurns: [...state.traceTurns] }),
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
    addTraceTurn(turn) {
      if (!turn || !Array.isArray(turn.trace)) return
      state.traceTurns.unshift({ ...turn, created_at: turn.created_at || new Date().toISOString() })
      state.traceTurns = state.traceTurns.slice(0, 20)
    },
    clearMessages() {
      state.messages = [...defaultMessages]
      state.inputText = ''
    },
    clearMessagesSilent() {
      state.messages = []
      state.inputText = ''
    },
    clearTraces() {
      state.traceTurns = [defaultTraceTurn()]
    },
    setInputText(text) {
      state.inputText = text
    },
  }
}
