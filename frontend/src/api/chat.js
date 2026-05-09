const BASE = '/api'

export async function listSessions(projectId) {
  const res = await fetch(`${BASE}/projects/${projectId}/chat/sessions`)
  if (!res.ok) return []
  return res.json()
}

export async function getHistory(projectId, sessionId) {
  const res = await fetch(`${BASE}/projects/${projectId}/chat/sessions/${sessionId}/history`)
  if (!res.ok) return []
  const data = await res.json()
  return data.history ?? []
}

export async function streamChat(projectId, sessionId, message, onEvent) {
  const res = await fetch(`${BASE}/projects/${projectId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!res.ok) {
    onEvent({ type: 'error', message: 'Chat request failed' })
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const parts = buffer.split('\n\n')
    buffer = parts.pop()

    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6))
          onEvent(event)
        } catch {
          // skip malformed chunk
        }
      }
    }
  }
}
