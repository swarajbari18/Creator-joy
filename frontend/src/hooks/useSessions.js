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

    // Only keep sessions that exist in the backend (Source of Truth)
    const sorted = backend.map(s => ({
      id: s.session_id,
      label: s.first_message ? s.first_message.slice(0, 45) : 'New Chat',
      created_at: s.last_active,
      project_id: projectId,
      first_message: s.first_message,
      last_active: s.last_active,
    })).sort((a, b) => new Date(b.last_active) - new Date(a.last_active))
    
    // Also add the 'active' session if it's new and not yet in the backend
    if (activeSessionId && !sorted.find(s => s.id === activeSessionId)) {
      const activeLocal = local.find(l => l.id === activeSessionId)
      if (activeLocal) sorted.unshift(activeLocal)
    }

    setSessions(sorted)
  }, [projectId, activeSessionId])

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
