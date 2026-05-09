import { useState } from 'react'
import { Plus } from 'lucide-react'
import { VideoCard } from './VideoCard'
import { IngestionProgress } from './IngestionProgress'
import { UrlInputBar } from './UrlInputBar'

export function VideoSection({ projectId, videos, pendingIngestions, onAddVideo, onRetryIngestion, onRetryVideo }) {
  const [showInput, setShowInput] = useState(false)

  function handleSubmit(url, role) {
    setShowInput(false)
    onAddVideo(url, role)
  }

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div className="flex items-center justify-between px-4 py-3 flex-shrink-0">
        <span className="text-xs font-semibold text-muted uppercase tracking-wider">Videos</span>
        <button
          onClick={() => setShowInput(v => !v)}
          className="w-6 h-6 rounded-md bg-surface hover:bg-border flex items-center justify-center transition-colors"
        >
          <Plus size={13} className="text-muted hover:text-white transition-colors" />
        </button>
      </div>

      {showInput && (
        <div className="px-3 pb-3 flex-shrink-0">
          <UrlInputBar onSubmit={handleSubmit} />
        </div>
      )}

      <div className="overflow-y-auto flex-1 min-h-0 px-3 pb-3 space-y-4">
        {pendingIngestions
          .filter(p => !p.videoId || !videos.some(v => v.id === p.videoId))
          .map(p => (
            <IngestionProgress
              key={p.tempId}
              url={p.url}
              stage={p.stage}
              error={p.error}
              onRetry={p.error && onRetryIngestion ? () => onRetryIngestion(p.tempId) : null}
            />
          ))}
        {videos.map(v => (
          <VideoCard
            key={v.id}
            video={v}
            projectId={projectId}
            onRetry={onRetryVideo ? () => onRetryVideo(v.id) : null}
          />
        ))}
        {videos.length === 0 && pendingIngestions.length === 0 && (
          <div className="text-center py-8 text-muted text-xs">
            <p>No videos yet.</p>
            <p className="mt-1">Paste a URL above to add one.</p>
          </div>
        )}
      </div>
    </div>
  )
}
