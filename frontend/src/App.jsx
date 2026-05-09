import { useState } from 'react'
import { Header } from './components/layout/Header'
import { ProjectsDashboard } from './components/dashboard/ProjectsDashboard'
import { WorkspaceLayout } from './components/workspace/WorkspaceLayout'

export default function App() {
  const [activeView, setActiveView] = useState('dashboard')
  const [activeProject, setActiveProject] = useState(null)

  function handleSelectProject(project) {
    setActiveProject(project)
    setActiveView('workspace')
  }

  function handleBack() {
    setActiveView('dashboard')
    setActiveProject(null)
  }

  return (
    <div className="flex flex-col h-screen bg-bg overflow-hidden">
      <Header onLogoClick={handleBack} />
      <div className="flex-1 pt-14 min-h-0 overflow-hidden">
        {activeView === 'dashboard' || !activeProject ? (
          <ProjectsDashboard onSelectProject={handleSelectProject} />
        ) : (
          <div className="h-full flex flex-col min-h-0 overflow-hidden">
            <WorkspaceLayout project={activeProject} />
          </div>
        )}
      </div>
    </div>
  )
}
