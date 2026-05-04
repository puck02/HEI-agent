<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

// Configure marked for safety
marked.setOptions({
  breaks: true,        // Single line breaks → <br>
  gfm: true,           // GitHub Flavored Markdown
})

const props = defineProps({
  role: { type: String, required: true },
  content: { type: String, required: true },
  intent: { type: String, default: '' },
  latency: { type: Number, default: 0 },
  references: { type: Array, default: () => [] },
})

const renderedContent = computed(() => {
  if (!props.content) return ''
  // Only render markdown for assistant messages
  if (props.role === 'assistant') {
    return marked.parse(props.content)
  }
  // User messages: escape HTML, turn newlines to <br>
  return props.content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
})

const collectionLabel = (col) => {
  const map = {
    health_knowledge: '健康知识',
    medication_info: '用药信息',
    tcm_wellness: '中医养生',
  }
  return map[col] || col
}

const formatScore = (score) => {
  if (score == null) return ''
  return (score * 100).toFixed(0) + '%'
}
</script>

<template>
  <div class="flex gap-2 mb-3" :class="role === 'user' ? 'flex-row-reverse' : 'flex-row'">
    <!-- Avatar -->
    <div v-if="role === 'assistant'" class="flex-shrink-0 relative">
      <div class="w-9 h-9 rounded-full bg-white flex items-center justify-center shadow-kitty-sm overflow-hidden ring-2 ring-kitty-200">
        <img src="/images/default_avatar_kitty.png" alt="Kitty" class="w-9 h-9 object-cover rounded-full" />
      </div>
      <img src="/images/bow.png" alt="" class="absolute -top-1.5 -right-1.5 w-4 h-4 object-contain" />
    </div>

    <!-- Message bubble -->
    <div class="max-w-[80%]">
      <div
        class="px-4 py-3 rounded-2xl text-sm leading-relaxed md-content"
        :class="role === 'user'
          ? 'bg-gradient-to-br from-kitty-400 to-kitty-500 text-white rounded-tr-md shadow-kitty-sm user-md'
          : 'bg-white text-gray-800 rounded-tl-md shadow-kitty-sm border border-kitty-50 assistant-md'"
        v-html="renderedContent"
      ></div>

      <!-- References section -->
      <div
        v-if="role === 'assistant' && references && references.length > 0"
        class="mt-2 flex flex-wrap gap-1.5"
      >
        <span class="text-[10px] text-kitty-400 mr-0.5 self-center">📚</span>
        <span
          v-for="(ref, idx) in references"
          :key="idx"
          class="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-kitty-50 border border-kitty-100 text-kitty-600 cursor-default hover:bg-kitty-100 transition-colors"
          :title="'来源: ' + ref.source + '\n集合: ' + collectionLabel(ref.collection) + '\n相关度: ' + formatScore(ref.score)"
        >
          <span class="text-kitty-400">◆</span>
          <span class="max-w-[120px] truncate">{{ ref.source }}</span>
          <span class="text-[9px] text-kitty-300 bg-white px-1 rounded-full">{{ collectionLabel(ref.collection) }}</span>
        </span>
      </div>

      <!-- Meta line -->
      <div v-if="role === 'assistant'" class="flex gap-2 mt-1 px-1">
        <span
          v-if="intent"
          class="text-[10px] px-1.5 py-0.5 rounded-full bg-kitty-100 text-kitty-600 font-medium"
        >
          {{ intent }}
        </span>
        <span v-if="latency" class="text-[10px] text-gray-400">
          {{ latency.toFixed(0) }}ms
        </span>
      </div>
    </div>
  </div>
</template>
