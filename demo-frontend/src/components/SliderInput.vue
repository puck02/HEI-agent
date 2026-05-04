<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  modelValue: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 10 },
})

const emit = defineEmits(['update:modelValue'])

const sliderValue = ref(props.modelValue)

watch(() => props.modelValue, (v) => { sliderValue.value = v })

const onInput = (e) => {
  const v = Number(e.target.value)
  sliderValue.value = v
  emit('update:modelValue', v)
}

const displayLabel = computed(() => {
  const v = sliderValue.value
  if (v === 0) return '无'
  if (v <= 2) return '轻微'
  if (v <= 4) return '较轻'
  if (v <= 6) return '中等'
  if (v <= 8) return '较重'
  return '严重'
})

const barColor = computed(() => {
  const v = sliderValue.value
  if (v <= 2) return '#7ECDA0'
  if (v <= 4) return '#FFCF70'
  if (v <= 6) return '#FFB3C6'
  if (v <= 8) return '#FF6B8A'
  return '#E4002B'
})

const fillPercent = computed(() => {
  return ((sliderValue.value - props.min) / (props.max - props.min)) * 100
})
</script>

<template>
  <div class="mb-4">
    <div v-if="label" class="flex justify-between items-center mb-2">
      <span class="text-sm text-gray-700 font-medium">{{ label }}</span>
    </div>
    <div class="flex items-center gap-3">
      <span class="text-xs text-gray-400 w-4 text-right">{{ min }}</span>
      <div class="flex-1 relative">
        <input
          type="range"
          :min="min"
          :max="max"
          :value="sliderValue"
          @input="onInput"
          class="kitty-slider w-full"
        />
        <div class="kitty-slider-track">
          <div class="kitty-slider-fill" :style="{ width: fillPercent + '%', backgroundColor: barColor }" />
        </div>
      </div>
      <span class="text-xs text-gray-400 w-4">{{ max }}</span>
    </div>
    <div class="flex justify-center mt-2">
      <span
        class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold text-white"
        :style="{ backgroundColor: barColor }"
      >
        {{ sliderValue }} - {{ displayLabel }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.kitty-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  border-radius: 4px;
  background: transparent;
  outline: none;
  position: relative;
  z-index: 2;
  cursor: pointer;
}

.kitty-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #FF6B8A;
  border: 3px solid white;
  box-shadow: 0 2px 8px rgba(255, 107, 138, 0.4);
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.kitty-slider::-webkit-slider-thumb:hover {
  transform: scale(1.15);
  box-shadow: 0 2px 12px rgba(255, 107, 138, 0.6);
}

.kitty-slider::-webkit-slider-thumb:active {
  transform: scale(1.05);
}

.kitty-slider::-moz-range-thumb {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #FF6B8A;
  border: 3px solid white;
  box-shadow: 0 2px 8px rgba(255, 107, 138, 0.4);
  cursor: pointer;
}

.kitty-slider-track {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 8px;
  border-radius: 4px;
  background: #FFE8EE;
  transform: translateY(-50%);
  z-index: 1;
  pointer-events: none;
}

.kitty-slider-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.1s ease;
}
</style>
