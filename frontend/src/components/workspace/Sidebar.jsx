import { VideoSection } from './videos/VideoSection'
import { ChatSection } from './chat/ChatSection'

export function Sidebar({ projectId, videos, pendingIngestions, onAddVideo, onRetryIngestion, sessions, activeSessionId, onSelectSession, onNewSession }) {
  return (
    <aside className="w-72 flex-shrink-0 bg-surface border-r border-border flex flex-col h-full min-h-0">
      <VideoSection
        projectId={projectId}
        videos={videos}
        pendingIngestions={pendingIngestions}
        onAddVideo={onAddVideo}
        onRetryIngestion={onRetryIngestion}
      />
      <ChatSection
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={onSelectSession}
        onNewSession={onNewSession}
      />
    </aside>
  )
}
