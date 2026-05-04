<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const sessionStore = useSessionStore()

const showSettings = ref(false)
const isChatRoute = computed(() => route.path === '/chat')

const currentSessionTitle = computed(() => {
  if (!sessionStore.state.currentSessionId) return null
  const session = sessionStore.state.sessions.find(
    s => s.session_id === sessionStore.state.currentSessionId
  )
  return session?.title || null
})

const emit = defineEmits(['toggle-sessions', 'new-session'])
</script>

<template>
  <header class="bg-gradient-to-r from-kitty-400 to-kitty-500 text-white px-4 py-3 flex items-center justify-between shadow-kitty relative overflow-hidden">
    <!-- Subtle background pattern -->
    <div class="absolute inset-0 opacity-[0.06]" style="background-image: url('/images/background01.png'); background-size: 300px; background-repeat: repeat;"></div>

    <div class="flex items-center gap-2 relative z-10">
      <!-- Session list toggle (chat route only) -->
      <button
        v-if="isChatRoute"
        @click="$emit('toggle-sessions')"
        class="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/20 transition"
        title="对话列表"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      </button>

      <!-- Kitty avatar -->
      <div class="w-9 h-9 rounded-full bg-white/30 flex items-center justify-center overflow-hidden ring-2 ring-white/40">
        <img src="/images/default_avatar_kitty.png" alt="Kitty" class="w-9 h-9 object-cover rounded-full" />
      </div>
      <div>
        <h1 class="text-base font-bold leading-tight">
          {{ isChatRoute && currentSessionTitle ? currentSessionTitle : 'Kitty 健康管家' }}
        </h1>
        <p class="text-[10px] opacity-70">HEI Health Advisor</p>
      </div>
    </div>

    <div class="flex items-center gap-1 relative z-10">
      <!-- New session button (chat route only) -->
      <button
        v-if="isChatRoute"
        @click="$emit('new-session')"
        class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition"
        title="新建对话"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
      </button>

      <!-- Bow decoration -->
      <img src="/images/bow.png" alt="" class="w-6 h-6 object-contain opacity-80" />
      <button
        @click="showSettings = !showSettings"
        class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
    </div>
  </header>
</template>
