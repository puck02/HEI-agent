import { reactive } from 'vue'
import * as api from '../api'

const state = reactive({
  sessions: [],
  currentSessionId: null,
  loading: false,
  sidebarVisible: false,
})

export function useSessionStore() {
  return {
    state,

    async fetchSessions() {
      state.loading = true
      try {
        const data = await api.listSessions()
        state.sessions = data.sessions || []
      } catch (e) {
        console.error('Failed to fetch sessions:', e)
      } finally {
        state.loading = false
      }
    },

    async createSession(title) {
      try {
        const session = await api.createSession(title)
        state.sessions.unshift({
          session_id: session.session_id,
          title: session.title,
          created_at: session.created_at,
          updated_at: session.updated_at,
          message_count: 0,
        })
        state.currentSessionId = session.session_id
        return session
      } catch (e) {
        console.error('Failed to create session:', e)
        return null
      }
    },

    async deleteSession(sessionId) {
      try {
        await api.deleteSession(sessionId)
        state.sessions = state.sessions.filter(s => s.session_id !== sessionId)
        if (state.currentSessionId === sessionId) {
          state.currentSessionId = null
        }
      } catch (e) {
        console.error('Failed to delete session:', e)
      }
    },

    async loadSession(sessionId) {
      try {
        const session = await api.getSession(sessionId)
        state.currentSessionId = sessionId
        return session
      } catch (e) {
        console.error('Failed to load session:', e)
        return null
      }
    },

    setCurrentSession(sessionId) {
      state.currentSessionId = sessionId
    },

    clearCurrentSession() {
      state.currentSessionId = null
    },

    updateSessionTitle(sessionId, title) {
      const session = state.sessions.find(s => s.session_id === sessionId)
      if (session) {
        session.title = title
      }
    },

    incrementMessageCount(sessionId) {
      const session = state.sessions.find(s => s.session_id === sessionId)
      if (session) {
        session.message_count++
      }
    },

    toggleSidebar() {
      state.sidebarVisible = !state.sidebarVisible
    },

    closeSidebar() {
      state.sidebarVisible = false
    },
  }
}
