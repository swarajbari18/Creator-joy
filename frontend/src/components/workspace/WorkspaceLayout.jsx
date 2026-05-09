import { useVideos } from '../../hooks/useVideos'
import { useSessions } from '../../hooks/useSessions'
import { Sidebar } from './Sidebar'
import { ChatArea } from './chat/ChatArea'

export function WorkspaceLayout({ project }) {
  const { videos, pendingIngestions, addVideo, retryIngestion, retranscribeVideo } = useVideos(project.id)
  const { sessions, activeSessionId, createSession, activateSession } = useSessions(project.id)

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <Sidebar
        projectId={project.id}
        videos={videos}
        pendingIngestions={pendingIngestions}
        onAddVideo={addVideo}
        onRetryIngestion={retryIngestion}
        onRetryVideo={retranscribeVideo}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={activateSession}
        onNewSession={createSession}
      />
      <main className="flex-1 flex flex-col min-h-0 overflow-hidden bg-bg">
        <ChatArea project={project} activeSessionId={activeSessionId} />
      </main>
    </div>
  )
}
