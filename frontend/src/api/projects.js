const BASE = '/api'

export async function listProjects() {
  const res = await fetch(`${BASE}/projects`)
  if (!res.ok) throw new Error('Failed to list projects')
  return res.json()
}

export async function createProject(name) {
  const res = await fetch(`${BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error('Failed to create project')
  return res.json()
}

export async function getProject(projectId) {
  const res = await fetch(`${BASE}/projects/${projectId}`)
  if (!res.ok) throw new Error('Failed to get project')
  return res.json()
}
