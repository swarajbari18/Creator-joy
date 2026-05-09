import { useState, useEffect, useCallback } from 'react'
import { listSessions } from '../api/chat'
import { getSessions, saveSession } from '../utils/sessionStorage'

export function useSessions(projectId) {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)

  const load = useCallback(async () => {
    if (!projectId) return
    const backend = await listSessions(projectId)
    const local = getSessions(projectId)

    const merged = new Map()
    local.forEach(s => merged.set(s.id, { ...s, first_message: null, last_active: s.created_at }))
    backend.forEach(s => merged.set(s.session_id, {
      id: s.session_id,
      label: s.first_message ? s.first_message.slice(0, 45) : 'New Chat',
      created_at: s.last_active,
      project_id: projectId,
      first_message: s.first_message,
      last_active: s.last_active,
    }))

    const sorted = Array.from(merged.values()).sort(
      (a, b) => new Date(b.last_active) - new Date(a.last_active)
    )
    setSessions(sorted)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const createSession = useCallback(() => {
    const id = crypto.randomUUID()
    const session = { id, label: 'New Chat', created_at: new Date().toISOString(), project_id: projectId, last_active: new Date().toISOString() }
    saveSession(projectId, session)
    setSessions(prev => [session, ...prev])
    setActiveSessionId(id)
    return id
  }, [projectId])

  const activateSession = useCallback((id) => {
    setActiveSessionId(id)
  }, [])

  return { sessions, activeSessionId, createSession, activateSession, reloadSessions: load }
}
