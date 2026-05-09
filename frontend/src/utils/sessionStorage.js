const key = projectId => `creatorjoy:sessions:${projectId}`

export function getSessions(projectId) {
  try {
    const raw = localStorage.getItem(key(projectId))
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function saveSession(projectId, session) {
  const sessions = getSessions(projectId)
  const idx = sessions.findIndex(s => s.id === session.id)
  if (idx >= 0) {
    sessions[idx] = { ...sessions[idx], ...session }
  } else {
    sessions.unshift(session)
  }
  localStorage.setItem(key(projectId), JSON.stringify(sessions))
}

export function removeSession(projectId, sessionId) {
  const sessions = getSessions(projectId).filter(s => s.id !== sessionId)
  localStorage.setItem(key(projectId), JSON.stringify(sessions))
}
