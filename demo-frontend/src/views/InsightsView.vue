<script setup>
import TrendChart from '../components/TrendChart.vue'

const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const sleepData = [7, 6, 8, 5, 7, 9, 8]
const exerciseData = [3, 5, 2, 6, 4, 7, 5]
const moodData = [7, 6, 8, 5, 7, 8, 9]

const summary = {
  sleep: { avg: '7.1h', trend: '↑' },
  exercise: { avg: '4.6次', trend: '→' },
  mood: { avg: '7.1分', trend: '↑' },
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4 space-y-4">
    <div class="grid grid-cols-3 gap-3">
      <div v-for="(item, key) in summary" :key="key" class="bg-white rounded-2xl p-3 shadow-sm text-center">
        <div class="text-lg">{{ key === 'sleep' ? '😴' : key === 'exercise' ? '🏃' : '😊' }}</div>
        <div class="text-xs text-gray-400 mt-1">{{ key === 'sleep' ? '睡眠' : key === 'exercise' ? '运动' : '情绪' }}</div>
        <div class="text-sm font-bold text-kitty-500 mt-0.5">{{ item.avg }}</div>
        <div class="text-xs text-green-500">{{ item.trend }}</div>
      </div>
    </div>

    <TrendChart
      title="7 天健康趋势"
      :labels="days"
      :datasets="[
        { label: '睡眠', data: sleepData, borderColor: '#ff5c85', backgroundColor: 'rgba(255,92,133,0.1)', fill: true },
        { label: '运动', data: exerciseData, borderColor: '#5c9eff', backgroundColor: 'rgba(92,158,255,0.1)', fill: true },
        { label: '情绪', data: moodData, borderColor: '#5ce65c', backgroundColor: 'rgba(92,230,92,0.1)', fill: true },
      ]"
    />

    <div class="bg-white rounded-2xl p-4 shadow-sm">
      <h3 class="text-sm font-bold text-gray-700 mb-2">📋 本周摘要</h3>
      <ul class="space-y-2 text-sm text-gray-600">
        <li class="flex items-start gap-2">
          <span class="text-kitty-400">•</span>
          睡眠质量整体良好，周六达到最佳状态
        </li>
        <li class="flex items-start gap-2">
          <span class="text-kitty-400">•</span>
          运动频率需加强，建议每周至少 4 次
        </li>
        <li class="flex items-start gap-2">
          <span class="text-kitty-400">•</span>
          情绪呈上升趋势，保持积极心态
        </li>
      </ul>
    </div>
  </div>
</template>
