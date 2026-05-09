const BASE = '/api'

export async function listVideos(projectId) {
  const res = await fetch(`${BASE}/projects/${projectId}/videos`)
  if (!res.ok) throw new Error('Failed to list videos')
  return res.json()
}

export async function ingestUrl(projectId, url, role) {
  const res = await fetch(`${BASE}/projects/${projectId}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls: [url], roles: [role] }),
  })
  if (!res.ok) throw new Error('Failed to ingest video')
  const results = await res.json()
  return results[0]
}

export async function getVideoPipelineStatus(projectId, videoId) {
  const res = await fetch(`${BASE}/projects/${projectId}/videos/${videoId}/pipeline-status`)
  if (!res.ok) throw new Error('Failed to get pipeline status')
  return res.json()
}

export async function transcribeVideo(projectId, videoId) {
  const res = await fetch(`${BASE}/projects/${projectId}/videos/${videoId}/transcribe`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Transcription failed')
  return res.json()
}

export async function indexVideo(projectId, videoId) {
  const res = await fetch(`${BASE}/projects/${projectId}/videos/${videoId}/index`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Indexing failed')
  return res.json()
}
