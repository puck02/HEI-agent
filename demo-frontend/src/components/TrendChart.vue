<script setup>
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

defineProps({
  labels: { type: Array, required: true },
  datasets: { type: Array, required: true },
  title: { type: String, default: '' },
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16 } },
  },
  scales: {
    y: { min: 0, max: 10, ticks: { stepSize: 2 } },
  },
  elements: {
    line: { tension: 0.4 },
    point: { radius: 4 },
  },
}
</script>

<template>
  <div class="bg-white rounded-2xl p-4 shadow-sm">
    <h3 v-if="title" class="text-sm font-bold text-gray-700 mb-3">{{ title }}</h3>
    <div class="h-48">
      <Line :data="{ labels, datasets }" :options="chartOptions" />
    </div>
  </div>
</template>
