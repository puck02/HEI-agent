<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '../stores/chat'

const router = useRouter()
const store = useChatStore()
const selectedSessionIndex = ref(0)
const selectedTurnIndex = ref(0)

const turns = computed(() => store.state.traceTurns || [])

const sessions = computed(() => {
  const groups = new Map()
  for (const turn of turns.value) {
    const sessionId = turn.session_id || 'unknown_session'
    if (!groups.has(sessionId)) {
      groups.set(sessionId, {
        session_id: sessionId,
        turns: [],
        total_latency: 0,
        tool_count: 0,
        error_count: 0,
        last_updated: turn.created_at || new Date().toISOString(),
      })
    }
    const session = groups.get(sessionId)
    session.turns.push(turn)
    session.total_latency += Number(turn.latency_ms || 0)
    session.tool_count += (turn.tool_calls_made || []).length
    session.error_count += (turn.trace || []).filter(event => event.status === 'error').length
    if ((turn.created_at || '') > (session.last_updated || '')) session.last_updated = turn.created_at
  }
  return Array.from(groups.values()).sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
})

const selectedSession = computed(() => sessions.value[selectedSessionIndex.value] || sessions.value[0] || null)
const sessionTurns = computed(() => selectedSession.value?.turns || [])
const selectedTurn = computed(() => sessionTurns.value[selectedTurnIndex.value] || sessionTurns.value[0] || null)
const trace = computed(() => selectedTurn.value?.trace || [])

const totalLatency = computed(() => selectedTurn.value?.latency_ms || trace.value.reduce((sum, item) => sum + (item.duration_ms || 0), 0))
const toolEvents = computed(() => trace.value.filter(item => item.type === 'tool_call' || item.type === 'confirmation'))
const llmEvents = computed(() => trace.value.filter(item => item.type === 'llm_call'))
const errorEvents = computed(() => trace.value.filter(item => item.status === 'error'))
const lastUpdated = computed(() => selectedTurn.value?.created_at ? new Date(selectedTurn.value.created_at).toLocaleString() : 'No trace yet')
const sessionLatency = computed(() => selectedSession.value?.total_latency || 0)
const sessionToolCount = computed(() => selectedSession.value?.tool_count || 0)
const sessionErrorCount = computed(() => selectedSession.value?.error_count || 0)

watch(sessions, () => {
  if (selectedSessionIndex.value >= sessions.value.length) selectedSessionIndex.value = 0
  if (selectedTurnIndex.value >= sessionTurns.value.length) selectedTurnIndex.value = 0
})

function selectSession(index) {
  selectedSessionIndex.value = index
  selectedTurnIndex.value = 0
}

function selectTurn(index) {
  selectedTurnIndex.value = index
}

function statusClass(status) {
  if (status === 'error') return 'bg-red-500/10 text-red-300 ring-red-500/20'
  if (status === 'pending') return 'bg-amber-500/10 text-amber-200 ring-amber-500/20'
  return 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/20'
}

function typeAccent(type) {
  if (type === 'tool_call') return 'from-cyan-400 to-blue-500'
  if (type === 'llm_call') return 'from-violet-400 to-indigo-500'
  if (type === 'confirmation') return 'from-amber-300 to-orange-500'
  if (type === 'routing') return 'from-fuchsia-400 to-pink-500'
  return 'from-slate-400 to-slate-600'
}

function prettyJson(value) {
  if (!value) return '—'
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

function short(text, limit = 90) {
  if (!text) return '—'
  return text.length > limit ? text.slice(0, limit) + '…' : text
}

function selectedTools(event) {
  return event?.metadata?.selected_tools || []
}

function hasSelectedTools(event) {
  return selectedTools(event).length > 0
}

function turnStatus(turn) {
  if ((turn.trace || []).some(event => event.status === 'error')) return 'error'
  if ((turn.trace || []).some(event => event.status === 'pending')) return 'pending'
  return 'ok'
}

function formatTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <div class="min-h-screen bg-[#07080a] text-[#f7f8f8] font-sans overflow-hidden">
    <div class="fixed inset-0 pointer-events-none">
      <div class="absolute -top-40 left-[35%] h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl"></div>
      <div class="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-cyan-500/10 blur-3xl"></div>
      <div class="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(113,112,255,0.08),transparent_35%),linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)] bg-[size:auto,44px_44px,44px_44px]"></div>
    </div>

    <div class="relative z-10 mx-auto flex min-h-screen max-w-[1500px] flex-col px-5 py-5 lg:px-8">
      <header class="mb-5 flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.035] px-5 py-4 shadow-2xl shadow-black/20 backdrop-blur-xl md:flex-row md:items-center md:justify-between">
        <div>
          <div class="mb-1 flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-indigo-300/80">
            <span class="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_18px_rgba(52,211,153,0.8)]"></span>
            Agent Observability
          </div>
          <h1 class="text-2xl font-semibold tracking-[-0.04em] text-white md:text-3xl">HEI Trace Monitor</h1>
          <p class="mt-1 text-sm text-slate-500">Session → Turns → Trace Events，把一次会话拆成可解释的多轮调用链</p>
        </div>
        <div class="flex items-center gap-3">
          <button @click="router.push('/chat')" class="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-300 transition hover:bg-white/[0.08] hover:text-white">
            返回 Demo
          </button>
          <button @click="store.clearTraces()" class="rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 transition hover:bg-red-500/20">
            清空 Trace
          </button>
        </div>
      </header>

      <section class="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div class="rounded-2xl border border-white/10 bg-white/[0.035] p-4 backdrop-blur-xl">
          <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Sessions</p>
          <p class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ sessions.length }}</p>
        </div>
        <div class="rounded-2xl border border-white/10 bg-white/[0.035] p-4 backdrop-blur-xl">
          <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Turns in Session</p>
          <p class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ sessionTurns.length }}</p>
        </div>
        <div class="rounded-2xl border border-white/10 bg-white/[0.035] p-4 backdrop-blur-xl">
          <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Session Latency</p>
          <p class="mt-2 text-3xl font-semibold tracking-[-0.04em]">{{ sessionLatency }}<span class="ml-1 text-sm text-slate-500">ms</span></p>
        </div>
        <div class="rounded-2xl border border-white/10 bg-white/[0.035] p-4 backdrop-blur-xl">
          <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Session Errors</p>
          <p class="mt-2 text-3xl font-semibold tracking-[-0.04em]" :class="sessionErrorCount ? 'text-red-300' : 'text-emerald-300'">{{ sessionErrorCount }}</p>
        </div>
      </section>

      <main class="grid min-h-0 flex-1 grid-cols-1 gap-5 xl:grid-cols-[300px_360px_1fr]">
        <aside class="min-h-0 rounded-3xl border border-white/10 bg-[#0f1011]/90 p-4 shadow-2xl shadow-black/30 backdrop-blur-xl">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-white">Sessions</p>
              <p class="text-xs text-slate-500">先选择一次完整会话</p>
            </div>
            <span class="rounded-full border border-white/10 px-2 py-1 text-xs text-slate-400">{{ sessions.length }}</span>
          </div>

          <div class="space-y-2 overflow-y-auto pr-1 max-h-[calc(100vh-280px)]">
            <button
              v-for="(session, index) in sessions"
              :key="session.session_id"
              @click="selectSession(index)"
              class="w-full rounded-2xl border p-3 text-left transition"
              :class="selectedSessionIndex === index ? 'border-indigo-400/50 bg-indigo-500/12 shadow-[0_0_30px_rgba(99,102,241,0.18)]' : 'border-white/8 bg-white/[0.025] hover:bg-white/[0.055]'"
            >
              <div class="mb-2 flex items-center justify-between gap-2">
                <span class="truncate rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[10px] text-slate-300">{{ session.session_id }}</span>
                <span class="text-[10px] text-slate-500">{{ session.turns.length }} turns</span>
              </div>
              <p class="text-sm font-medium text-slate-100">{{ short(session.turns[0]?.message, 42) }}</p>
              <div class="mt-3 grid grid-cols-3 gap-2 text-center text-[10px] text-slate-400">
                <div class="rounded-lg bg-black/25 px-2 py-1"><span class="block text-slate-100">{{ session.total_latency }}</span>ms</div>
                <div class="rounded-lg bg-black/25 px-2 py-1"><span class="block text-cyan-100">{{ session.tool_count }}</span>tools</div>
                <div class="rounded-lg bg-black/25 px-2 py-1"><span class="block" :class="session.error_count ? 'text-red-200' : 'text-emerald-200'">{{ session.error_count }}</span>errors</div>
              </div>
              <p class="mt-2 text-[10px] text-slate-600">updated {{ formatTime(session.last_updated) }}</p>
            </button>
          </div>
        </aside>

        <aside class="min-h-0 rounded-3xl border border-white/10 bg-[#0f1011]/90 p-4 shadow-2xl shadow-black/30 backdrop-blur-xl">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-white">Conversation turns</p>
              <p class="text-xs text-slate-500">当前会话里的每轮对话</p>
            </div>
            <span class="rounded-full border border-white/10 px-2 py-1 text-xs text-slate-400">{{ sessionTurns.length }}</span>
          </div>

          <div class="space-y-3 overflow-y-auto pr-1 max-h-[calc(100vh-280px)]">
            <button
              v-for="(turn, index) in sessionTurns"
              :key="turn.trace_id || index"
              @click="selectTurn(index)"
              class="w-full rounded-2xl border p-3 text-left transition"
              :class="selectedTurnIndex === index ? 'border-cyan-300/45 bg-cyan-400/[0.08] shadow-[0_0_30px_rgba(34,211,238,0.12)]' : 'border-white/8 bg-white/[0.025] hover:bg-white/[0.055]'"
            >
              <div class="mb-2 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <span class="grid h-6 w-6 place-items-center rounded-full bg-white/[0.07] font-mono text-[10px] text-slate-300">#{{ sessionTurns.length - index }}</span>
                  <span class="rounded-full px-2 py-0.5 text-[10px] ring-1" :class="statusClass(turnStatus(turn))">{{ turnStatus(turn) }}</span>
                </div>
                <span class="font-mono text-[10px] text-slate-500">{{ turn.latency_ms || 0 }}ms</span>
              </div>
              <p class="text-sm leading-5 text-slate-100">{{ short(turn.message, 72) }}</p>
              <p class="mt-2 text-xs leading-5 text-slate-500">{{ short(turn.answer, 86) }}</p>
              <div class="mt-3 flex flex-wrap gap-1">
                <span v-for="tool in (turn.tool_calls_made || [])" :key="tool" class="rounded-full bg-cyan-400/10 px-2 py-0.5 text-[10px] text-cyan-200">{{ tool }}</span>
                <span v-if="!(turn.tool_calls_made || []).length" class="rounded-full bg-slate-500/10 px-2 py-0.5 text-[10px] text-slate-400">no tools</span>
              </div>
              <div class="mt-2 truncate rounded-md bg-black/20 px-2 py-1 font-mono text-[10px] text-slate-500">{{ turn.trace_id || 'trace_pending' }}</div>
            </button>
          </div>
        </aside>

        <section class="min-h-0 rounded-3xl border border-white/10 bg-[#0f1011]/90 shadow-2xl shadow-black/30 backdrop-blur-xl overflow-hidden">
          <div class="border-b border-white/10 bg-white/[0.025] p-5">
            <div class="flex flex-col gap-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
              <div>
                <p class="text-xs uppercase tracking-[0.22em] text-cyan-300/70">Selected Turn Trace</p>
                <h2 class="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">{{ selectedTurn?.message || '暂无真实调用，先在对话页发送一条消息' }}</h2>
                <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{{ short(selectedTurn?.answer, 220) }}</p>
                <div class="mt-4 flex flex-wrap gap-2 text-xs">
                  <span class="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-slate-300">latency {{ totalLatency || 0 }}ms</span>
                  <span class="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-cyan-200">tools {{ toolEvents.length }}</span>
                  <span class="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-indigo-200">llm {{ llmEvents.length }}</span>
                  <span class="rounded-full border border-white/10 bg-black/20 px-3 py-1" :class="errorEvents.length ? 'text-red-200' : 'text-emerald-200'">errors {{ errorEvents.length }}</span>
                </div>
              </div>
              <div class="rounded-2xl border border-white/10 bg-black/30 p-3 font-mono text-xs text-slate-400">
                <div>session: <span class="text-slate-200">{{ selectedTurn?.session_id || '—' }}</span></div>
                <div>trace: <span class="text-slate-200">{{ selectedTurn?.trace_id || '—' }}</span></div>
                <div>updated: <span class="text-slate-200">{{ lastUpdated }}</span></div>
                <div>iterations: <span class="text-slate-200">{{ selectedTurn?.iterations ?? '—' }}</span></div>
              </div>
            </div>
          </div>

          <div class="grid min-h-0 grid-cols-1 2xl:grid-cols-[1fr_340px]">
            <div class="max-h-[calc(100vh-380px)] overflow-y-auto p-5">
              <div class="relative ml-3 space-y-4 border-l border-white/10 pl-6">
                <div
                  v-for="(event, index) in trace"
                  :key="`${event.ts}-${index}`"
                  class="relative rounded-2xl border border-white/10 bg-white/[0.035] p-4 transition hover:bg-white/[0.055]"
                >
                  <div :class="`absolute -left-[34px] top-5 h-4 w-4 rounded-full bg-gradient-to-br ${typeAccent(event.type)} ring-4 ring-[#0f1011]`"></div>
                  <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div class="flex items-center gap-2">
                      <span class="font-mono text-xs text-slate-500">#{{ index + 1 }}</span>
                      <h3 class="text-sm font-semibold text-white">{{ event.name }}</h3>
                      <span class="rounded-full px-2 py-0.5 text-[10px] ring-1" :class="statusClass(event.status)">{{ event.status }}</span>
                    </div>
                    <div class="font-mono text-xs text-slate-500">{{ event.duration_ms != null ? `${event.duration_ms}ms` : 'instant' }}</div>
                  </div>
                  <div class="mb-3 flex flex-wrap gap-2 text-xs">
                    <span class="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-slate-300">{{ event.type }}</span>
                    <span class="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-slate-300">{{ event.phase }}</span>
                  </div>
                  <p v-if="event.output_preview" class="mb-3 rounded-xl border border-white/8 bg-black/20 p-3 text-sm leading-6 text-slate-300">{{ event.output_preview }}</p>
                  <div v-if="hasSelectedTools(event)" class="mb-3 rounded-xl border border-cyan-400/20 bg-cyan-400/[0.06] p-3">
                    <div class="mb-2 flex items-center justify-between gap-2">
                      <p class="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">Selected tools</p>
                      <span class="rounded-full bg-cyan-300/10 px-2 py-0.5 text-[10px] text-cyan-100">{{ selectedTools(event).length }} call(s)</span>
                    </div>
                    <div class="space-y-2">
                      <div
                        v-for="tool in selectedTools(event)"
                        :key="`${event.ts}-${tool.name}`"
                        class="rounded-lg border border-cyan-300/10 bg-black/25 p-2"
                      >
                        <div class="mb-1 flex items-center gap-2">
                          <span class="h-1.5 w-1.5 rounded-full bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,0.9)]"></span>
                          <span class="font-mono text-xs font-semibold text-cyan-100">{{ tool.name }}</span>
                        </div>
                        <pre class="max-h-28 overflow-auto whitespace-pre-wrap rounded-md bg-black/30 p-2 text-[11px] leading-5 text-cyan-50/80">{{ prettyJson(tool.arguments) }}</pre>
                      </div>
                    </div>
                  </div>
                  <details v-if="event.input || event.metadata" class="group rounded-xl border border-white/8 bg-black/25">
                    <summary class="cursor-pointer list-none px-3 py-2 text-xs text-slate-400 transition group-open:text-indigo-200">查看参数与 metadata</summary>
                    <pre class="overflow-x-auto border-t border-white/8 p-3 text-xs leading-5 text-slate-300">{{ prettyJson({ input: event.input, metadata: event.metadata }) }}</pre>
                  </details>
                </div>
              </div>
            </div>

            <aside class="border-t border-white/10 bg-black/20 p-5 2xl:border-l 2xl:border-t-0">
              <p class="mb-3 text-sm font-medium text-white">Waterfall</p>
              <div class="space-y-3">
                <div v-for="(event, index) in trace.filter(e => e.duration_ms != null)" :key="`bar-${index}`">
                  <div class="mb-1 flex justify-between gap-3 text-xs text-slate-500">
                    <span class="truncate">{{ event.name }}</span>
                    <span>{{ event.duration_ms }}ms</span>
                  </div>
                  <div class="h-2 overflow-hidden rounded-full bg-white/5">
                    <div class="h-full rounded-full bg-gradient-to-r from-indigo-400 to-cyan-300" :style="{ width: `${Math.min(100, ((event.duration_ms || 0) / Math.max(totalLatency, 1)) * 100)}%` }"></div>
                  </div>
                </div>
              </div>

              <div class="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p class="mb-2 text-sm font-medium text-white">Trace Reading Order</p>
                <ol class="space-y-2 text-xs leading-5 text-slate-400">
                  <li>1. 先在左侧确认是哪一个 session。</li>
                  <li>2. 再在中间选择该 session 的具体轮次。</li>
                  <li>3. 右侧只展示当前轮次的 LLM/tool/answer 链路。</li>
                  <li>4. 有工具调用时，看 selected_tools → tool_call 是否一致。</li>
                </ol>
              </div>

              <div class="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p class="mb-2 text-sm font-medium text-white">Debug Tips</p>
                <ul class="space-y-2 text-xs leading-5 text-slate-400">
                  <li>• tool_selection 慢：优先看模型响应耗时。</li>
                  <li>• tool_call 慢：检查 RAG/Qdrant 或 SQLite。</li>
                  <li>• synthesis 慢：说明最终回答生成阶段耗时高。</li>
                  <li>• pending：写工具已进入确认流程，尚未真正执行。</li>
                </ul>
              </div>
            </aside>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>
