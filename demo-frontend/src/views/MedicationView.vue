<script setup>
import { ref, onMounted } from 'vue'
import { fetchMedications, addMedication } from '../api/index.js'

const medications = ref([])
const loading = ref(false)

const loadMeds = async () => {
  loading.value = true
  try {
    const data = await fetchMedications()
    medications.value = data.medications || []
  } catch (e) {
    console.error('Failed to load medications:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadMeds)

const showAdd = ref(false)
const editingId = ref(null)
const showDeleteConfirm = ref(false)
const deleteTargetId = ref(null)
const newMed = ref({ name: '', dosage: '', frequency: '', time: '', note: '' })
const editMed = ref({ name: '', dosage: '', frequency: '', time: '', note: '' })

const addMed = async () => {
  if (!newMed.value.name) return
  try {
    const result = await addMedication(newMed.value)
    if (result.ok) {
      medications.value.push({
        id: result.id,
        ...newMed.value,
        active: true,
      })
    }
  } catch (e) {
    console.error('Failed to add medication:', e)
  }
  newMed.value = { name: '', dosage: '', frequency: '', time: '', note: '' }
  showAdd.value = false
}

const startEdit = (med) => {
  editingId.value = med.id
  editMed.value = {
    name: med.name,
    dosage: med.dosage,
    frequency: med.frequency,
    time: med.time,
    note: med.note,
  }
}

const saveEdit = () => {
  const med = medications.value.find(m => m.id === editingId.value)
  if (med) {
    Object.assign(med, editMed.value)
  }
  editingId.value = null
}

const cancelEdit = () => {
  editingId.value = null
}

const confirmDelete = (id) => {
  deleteTargetId.value = id
  showDeleteConfirm.value = true
}

const doDelete = () => {
  medications.value = medications.value.filter(m => m.id !== deleteTargetId.value)
  showDeleteConfirm.value = false
  deleteTargetId.value = null
}

const cancelDelete = () => {
  showDeleteConfirm.value = false
  deleteTargetId.value = null
}

const toggleMed = (med) => {
  med.active = !med.active
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-base font-bold text-gray-800">我的药物</h2>
      <button
        @click="showAdd = !showAdd"
        class="text-xs px-3 py-1.5 rounded-full bg-kitty-400 text-white hover:bg-kitty-500 transition"
      >
        + 添加药物
      </button>
    </div>

    <!-- 添加药物表单 -->
    <div v-if="showAdd" class="bg-white rounded-2xl p-4 shadow-sm mb-4 border border-kitty-100">
      <h3 class="text-sm font-bold text-gray-700 mb-3">添加新药物</h3>
      <div class="space-y-2">
        <input v-model="newMed.name" placeholder="药物名称" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
        <div class="grid grid-cols-2 gap-2">
          <input v-model="newMed.dosage" placeholder="剂量" class="px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
          <input v-model="newMed.frequency" placeholder="频率" class="px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
        </div>
        <input v-model="newMed.time" placeholder="服用时间" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
        <input v-model="newMed.note" placeholder="备注" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
        <div class="flex gap-2">
          <button @click="addMed" class="flex-1 py-2 rounded-xl bg-kitty-400 text-white text-sm font-medium hover:bg-kitty-500 transition">
            保存
          </button>
          <button @click="showAdd = false" class="flex-1 py-2 rounded-xl bg-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-300 transition">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteConfirm" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl p-5 w-full max-w-sm shadow-xl">
        <div class="text-center mb-4">
          <div class="text-3xl mb-2">⚠️</div>
          <h3 class="text-base font-bold text-gray-800">确认删除</h3>
          <p class="text-sm text-gray-500 mt-1">确定要删除这个药物吗？此操作不可撤销。</p>
        </div>
        <div class="flex gap-2">
          <button @click="cancelDelete" class="flex-1 py-2.5 rounded-xl bg-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-300 transition">
            取消
          </button>
          <button @click="doDelete" class="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition">
            确认删除
          </button>
        </div>
      </div>
    </div>

    <!-- 药物列表 -->
    <div class="space-y-3">
      <div
        v-for="med in medications"
        :key="med.id"
        class="bg-white rounded-2xl p-4 shadow-sm border-l-4 transition"
        :class="med.active ? 'border-kitty-400' : 'border-gray-200 opacity-60'"
      >
        <!-- 编辑模式 -->
        <div v-if="editingId === med.id" class="space-y-2">
          <input v-model="editMed.name" placeholder="药物名称" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
          <div class="grid grid-cols-2 gap-2">
            <input v-model="editMed.dosage" placeholder="剂量" class="px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
            <input v-model="editMed.frequency" placeholder="频率" class="px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
          </div>
          <input v-model="editMed.time" placeholder="服用时间" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
          <input v-model="editMed.note" placeholder="备注" class="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-kitty-300" />
          <div class="flex gap-2 pt-1">
            <button @click="saveEdit" class="flex-1 py-2 rounded-xl bg-kitty-400 text-white text-sm font-medium hover:bg-kitty-500 transition">
              保存
            </button>
            <button @click="cancelEdit" class="flex-1 py-2 rounded-xl bg-gray-200 text-gray-600 text-sm font-medium hover:bg-gray-300 transition">
              取消
            </button>
          </div>
        </div>

        <!-- 显示模式 -->
        <div v-else>
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="text-base">💊</span>
                <h3 class="text-sm font-bold text-gray-800">{{ med.name }}</h3>
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="med.active ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'"
                >
                  {{ med.active ? '服用中' : '已停用' }}
                </span>
              </div>
              <div class="mt-2 space-y-1 text-xs text-gray-500">
                <p>
                  <span class="text-gray-400">剂量:</span> {{ med.dosage }}
                  <span class="mx-1 text-gray-300">·</span>
                  <span class="text-gray-400">频率:</span> {{ med.frequency }}
                </p>
                <p><span class="text-gray-400">时间:</span> {{ med.time }}</p>
                <p v-if="med.note" class="text-gray-400 italic">{{ med.note }}</p>
              </div>
            </div>
            <button
              @click="toggleMed(med)"
              class="w-10 h-6 rounded-full transition-colors relative flex-shrink-0"
              :class="med.active ? 'bg-kitty-400' : 'bg-gray-300'"
            >
              <span
                class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform"
                :class="med.active ? 'left-[18px]' : 'left-0.5'"
              />
            </button>
          </div>
          <!-- 操作按钮 -->
          <div class="flex gap-2 mt-3 pt-3 border-t border-gray-100">
            <button
              @click="startEdit(med)"
              class="flex-1 py-1.5 rounded-lg text-xs font-medium text-kitty-500 bg-kitty-50 hover:bg-kitty-100 transition"
            >
              ✏️ 编辑
            </button>
            <button
              @click="confirmDelete(med.id)"
              class="flex-1 py-1.5 rounded-lg text-xs font-medium text-red-500 bg-red-50 hover:bg-red-100 transition"
            >
              🗑️ 删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="medications.length === 0" class="text-center py-12">
      <div class="text-4xl mb-3">💊</div>
      <p class="text-sm text-gray-400">还没有添加药物</p>
      <p class="text-xs text-gray-300 mt-1">点击上方"添加药物"开始</p>
    </div>
  </div>
</template>
