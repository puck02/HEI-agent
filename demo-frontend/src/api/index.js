import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export async function sendMessage(message, sessionId) {
  const { data } = await api.post('/demo/chat', { message, session_id: sessionId })
  return data
}

export async function healthCheck() {
  const { data } = await axios.get('/health')
  return data
}

// ── Session API ──────────────────────────────────────────

export async function createSession(title) {
  const { data } = await api.post('/v1/sessions', { title })
  return data
}

export async function listSessions() {
  const { data } = await api.get('/v1/sessions')
  return data
}

export async function getSession(sessionId) {
  const { data } = await api.get(`/v1/sessions/${sessionId}`)
  return data
}

export async function updateSession(sessionId, title) {
  const { data } = await api.put(`/v1/sessions/${sessionId}`, { title })
  return data
}

export async function deleteSession(sessionId) {
  const { data } = await api.delete(`/v1/sessions/${sessionId}`)
  return data
}

// ── Daily Report API ─────────────────────────────────────

export async function getTodayReport(userId = 'demo_user') {
  const { data } = await api.get('/demo/daily-report', { params: { user_id: userId } })
  return data
}

export async function saveReport(answers, advice, userId = 'demo_user') {
  const { data } = await api.post('/demo/daily-report', {
    user_id: userId,
    answers,
    advice,
  })
  return data
}
