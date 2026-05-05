<script setup>
import { ref, computed } from 'vue'
import SliderInput from '../components/SliderInput.vue'
import { sendMessage } from '../api'
import { marked } from 'marked'

// Configure marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const questions = [
  {
    key: 'overall',
    label: '今天整体状态怎么样？',
    type: 'single',
    icon: '🎀',
    options: ['很好', '还可以', '有些不适', '明显不舒服'],
  },
  {
    key: 'focus',
    label: '今天想让 Kitty 特别关注哪里？',
    type: 'multi',
    icon: '🔍',
    options: ['头部', '颈肩', '腹部', '关节', '情绪', '睡眠', '皮肤', '其他'],
  },
  {
    key: 'sleep_hours',
    label: '昨晚睡眠时长',
    type: 'single',
    icon: '🌙',
    options: ['<6h', '6-7h', '7-8h', '>8h', '断续'],
  },
  {
    key: 'nap',
    label: '今天白天有小睡吗？',
    type: 'single',
    icon: '💤',
    options: ['无', '<30min', '30-60min', '>60min'],
  },
  {
    key: 'activity',
    label: '今天活动量如何？',
    type: 'single',
    icon: '🚶',
    options: ['<3k步', '3-6k步', '6-10k步', '>10k步'],
  },
  {
    key: 'headache',
    label: '头部不适强度',
    type: 'slider',
    icon: '🤕',
    min: 0,
    max: 10,
  },
  {
    key: 'neck_back',
    label: '颈肩背腰不适强度',
    type: 'slider',
    icon: '💪',
    min: 0,
    max: 10,
  },
  {
    key: 'stomach',
    label: '腹部/胃肠不适强度',
    type: 'slider',
    icon: '🫄',
    min: 0,
    max: 10,
  },
  {
    key: 'stress',
    label: '情绪压力/烦躁强度',
    type: 'slider',
    icon: '😤',
    min: 0,
    max: 10,
  },
  {
    key: 'stimulus',
    label: '今天有明显外界刺激吗？',
    type: 'single',
    icon: '⚡',
    options: ['有', '没有', '不确定'],
  },
  {
    key: 'medication',
    label: '用药执行情况',
    type: 'single',
    icon: '💊',
    options: ['按时', '有遗漏', '无需用药', '有调整'],
  },
  {
    key: 'extra',
    label: '补充信息',
    type: 'text',
    icon: '📝',
    placeholder: '有什么想告诉 Kitty 的吗？',
  },
]

const answers = ref({
  overall: '',
  focus: [],
  sleep_hours: '',
  nap: '',
  activity: '',
  headache: 0,
  neck_back: 0,
  stomach: 0,
  stress: 0,
  stimulus: '',
  medication: '',
  extra: '',
})

const advice = ref('')
const renderedAdvice = computed(() => {
  if (!advice.value) return ''
  return marked.parse(advice.value)
})
const loading = ref(false)
const submitted = ref(false)
const currentStep = ref(0)

const totalSteps = questions.length

// 当前题目（用 computed 保证响应式）
const currentQuestion = computed(() => questions[currentStep.value])

const toggleMulti = (key, val) => {
  const arr = answers.value[key]
  const idx = arr.indexOf(val)
  if (idx >= 0) {
    arr.splice(idx, 1)
  } else {
    arr.push(val)
  }
}

const canProceed = computed(() => {
  const q = currentQuestion.value
  if (!q) return false
  const val = answers.value[q.key]
  if (q.type === 'text') return true
  if (q.type === 'multi') return val.length > 0
  if (q.type === 'slider') return true
  return val !== ''
})

const nextStep = () => {
  if (currentStep.value < totalSteps - 1) {
    currentStep.value++
  }
}

const prevStep = () => {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

const handleSubmit = async () => {
  loading.value = true
  const parts = []
  for (const q of questions) {
    const val = answers.value[q.key]
    if (q.type === 'multi') {
      if (val.length > 0) parts.push(`${q.label}: ${val.join('、')}`)
    } else if (q.type === 'slider') {
      parts.push(`${q.label}: ${val}/10`)
    } else if (q.type === 'text') {
      if (val) parts.push(`${q.label}: ${val}`)
    } else {
      if (val) parts.push(`${q.label}: ${val}`)
    }
  }
  const summary = parts.join('；')
  try {
    const data = await sendMessage(`今日健康日报：${summary}，请给我一些改善建议。`)
    advice.value = data.response
  } catch {
    advice.value = '感谢提交日报！建议保持规律作息，适当运动，注意饮食均衡。'
  } finally {
    loading.value = false
    submitted.value = true
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto bg-kitty-50">
    <!-- Header -->
    <div class="bg-gradient-to-r from-kitty-400 to-kitty-300 px-4 py-3 text-white">
      <div class="flex items-center gap-2">
        <span class="text-lg">📋</span>
        <h2 class="text-base font-bold">每日健康日报</h2>
      </div>
      <p class="text-xs opacity-80 mt-0.5">完成日报，让 Kitty 更了解你</p>
    </div>

    <!-- Progress bar -->
    <div class="px-4 pt-3 pb-1">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs text-kitty-500 font-medium">
          {{ submitted ? '已完成' : `${currentStep + 1} / ${totalSteps}` }}
        </span>
        <span class="text-xs text-gray-400">
          {{ submitted ? '100%' : `${Math.round(((currentStep + 1) / totalSteps) * 100)}%` }}
        </span>
      </div>
      <div class="h-2 bg-kitty-100 rounded-full overflow-hidden">
        <div
          class="h-full bg-gradient-to-r from-kitty-400 to-kitty-300 rounded-full transition-all duration-300"
          :style="{ width: submitted ? '100%' : `${((currentStep + 1) / totalSteps) * 100}%` }"
        />
      </div>
    </div>

    <!-- Not submitted: show questions -->
    <div v-if="!submitted" class="p-4">
      <div class="bg-white rounded-2xl p-5 shadow-kitty-sm">
        <!-- Current question -->
        <div v-if="currentQuestion">
          <div class="flex items-center gap-2 mb-4">
            <span class="text-xl">{{ currentQuestion.icon }}</span>
            <h3 class="text-base font-bold text-gray-800">{{ currentQuestion.label }}</h3>
          </div>

          <!-- Single choice -->
          <div v-if="currentQuestion.type === 'single'" class="grid grid-cols-2 gap-2">
            <button
              v-for="opt in currentQuestion.options"
              :key="opt"
              @click="answers[currentQuestion.key] = opt"
              class="py-2.5 px-3 rounded-xl text-sm font-medium transition-all border-2"
              :class="answers[currentQuestion.key] === opt
                ? 'bg-kitty-400 text-white border-kitty-400 shadow-kitty-sm'
                : 'bg-kitty-50 text-gray-600 border-kitty-100 hover:border-kitty-300'"
            >
              {{ opt }}
            </button>
          </div>

          <!-- Multi choice -->
          <div v-else-if="currentQuestion.type === 'multi'" class="flex flex-wrap gap-2">
            <button
              v-for="opt in currentQuestion.options"
              :key="opt"
              @click="toggleMulti(currentQuestion.key, opt)"
              class="py-2 px-4 rounded-full text-sm font-medium transition-all border-2"
              :class="answers[currentQuestion.key].includes(opt)
                ? 'bg-kitty-400 text-white border-kitty-400 shadow-kitty-sm'
                : 'bg-kitty-50 text-gray-600 border-kitty-100 hover:border-kitty-300'"
            >
              {{ opt }}
            </button>
          </div>

          <!-- Slider -->
          <div v-else-if="currentQuestion.type === 'slider'" class="mt-2">
            <SliderInput
              :label="''"
              v-model="answers[currentQuestion.key]"
              :min="currentQuestion.min"
              :max="currentQuestion.max"
            />
          </div>

          <!-- Text input -->
          <div v-else-if="currentQuestion.type === 'text'">
            <textarea
              v-model="answers[currentQuestion.key]"
              :placeholder="currentQuestion.placeholder"
              rows="3"
              class="w-full px-4 py-3 rounded-xl border border-kitty-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300 bg-kitty-50 resize-none"
            />
          </div>
        </div>

        <!-- Navigation buttons -->
        <div class="flex items-center justify-between mt-6 pt-4 border-t border-kitty-100">
          <button
            @click="prevStep"
            :disabled="currentStep === 0"
            class="px-4 py-2 rounded-full text-sm font-medium text-kitty-500 border border-kitty-200 hover:bg-kitty-50 transition disabled:opacity-30 disabled:cursor-not-allowed"
          >
            上一题
          </button>
          <button
            v-if="currentStep < totalSteps - 1"
            @click="nextStep"
            :disabled="!canProceed"
            class="px-6 py-2 rounded-full text-sm font-medium text-white bg-gradient-to-r from-kitty-400 to-kitty-500 hover:shadow-kitty transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            下一题
          </button>
          <button
            v-else
            @click="handleSubmit"
            :disabled="loading || !canProceed"
            class="px-6 py-2 rounded-full text-sm font-medium text-white bg-gradient-to-r from-kitty-400 to-kitty-500 hover:shadow-kitty transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {{ loading ? '分析中...' : '提交日报' }}
          </button>
        </div>
      </div>

      <!-- Step dots -->
      <div class="flex justify-center gap-1.5 mt-4">
        <button
          v-for="(_, idx) in questions"
          :key="idx"
          @click="currentStep = idx"
          class="w-2 h-2 rounded-full transition-all"
          :class="idx === currentStep ? 'bg-kitty-400 w-5' : idx < currentStep ? 'bg-kitty-300' : 'bg-kitty-100'"
        />
      </div>
    </div>

    <!-- Submitted: show result -->
    <div v-else class="p-4 space-y-4">
      <div class="bg-white rounded-2xl p-5 shadow-kitty-sm text-center">
        <div class="text-4xl mb-2">🎀</div>
        <h3 class="text-lg font-bold text-kitty-500 mb-1">日报已提交！</h3>
        <p class="text-sm text-gray-400">Kitty 已收到你的健康信息</p>
      </div>

      <div class="bg-white rounded-2xl p-5 shadow-kitty-sm">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-lg">🐱</span>
          <h3 class="text-sm font-bold text-gray-700">Kitty 的建议</h3>
        </div>
        <div class="text-sm text-gray-600 leading-relaxed md-content" v-html="renderedAdvice"></div>
      </div>
    </div>
  </div>
</template>
