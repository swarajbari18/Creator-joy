import { useState, useEffect } from 'react'
import { useProjects } from '../../hooks/useProjects'
import { listVideos } from '../../api/videos'
import { ProjectCard } from './ProjectCard'
import { NewProjectModal } from './NewProjectModal'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Plus, FolderOpen } from 'lucide-react'

export function ProjectsDashboard({ onSelectProject }) {
  const { projects, loading, createProject } = useProjects()
  const [showModal, setShowModal] = useState(false)
  const [videosByProject, setVideosByProject] = useState({})

  useEffect(() => {
    projects.forEach(p => {
      listVideos(p.id).then(vids => {
        setVideosByProject(prev => ({ ...prev, [p.id]: vids }))
      }).catch(() => {})
    })
  }, [projects])

  async function handleCreate(name) {
    const project = await createProject(name)
    onSelectProject(project)
  }

  return (
    <div className="min-h-screen pt-14 bg-bg">
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-heading font-bold text-2xl text-white">Your Projects</h1>
            <p className="text-muted text-sm mt-1">Each project is a workspace for a set of videos</p>
          </div>
          <Button onClick={() => setShowModal(true)} size="md">
            <Plus size={16} /> New Project
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24 text-muted">
            <Spinner size={24} className="text-primary mr-3" /> Loading projects…
          </div>
        ) : projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-surface border border-border flex items-center justify-center mb-4">
              <FolderOpen size={28} className="text-muted" />
            </div>
            <h2 className="font-heading font-bold text-white text-lg mb-2">No projects yet</h2>
            <p className="text-muted text-sm mb-6">Create a project to start analyzing your videos</p>
            <Button onClick={() => setShowModal(true)}>
              <Plus size={16} /> Create your first project
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                videos={videosByProject[p.id] ?? []}
                onClick={() => onSelectProject(p)}
              />
            ))}
          </div>
        )}
      </div>

      <NewProjectModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onCreate={handleCreate}
      />
    </div>
  )
}
