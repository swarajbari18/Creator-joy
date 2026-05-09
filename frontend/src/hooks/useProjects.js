import { useState, useEffect, useCallback } from 'react'
import { listProjects, createProject as apiCreate } from '../api/projects'

export function useProjects() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listProjects()
      setProjects(data.slice().reverse())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const createProject = useCallback(async (name) => {
    const project = await apiCreate(name)
    await load()
    return project
  }, [load])

  return { projects, loading, error, createProject, reload: load }
}
