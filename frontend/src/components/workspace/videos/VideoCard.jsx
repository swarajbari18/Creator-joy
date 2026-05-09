import { useState } from 'react'
import { Play, BarChart2 } from 'lucide-react'
import { thumbnailUrl, thumbnailFallbackUrl } from '../../../utils/mediaUrls'
import { RoleBadge } from './RoleBadge'
import { VideoPlayer } from './VideoPlayer'
import { EngagementPanel } from './EngagementPanel'

export function VideoCard({ video, projectId }) {
  const [mode, setMode] = useState('thumbnail') // thumbnail | playing | metrics

  return (
    <div className="w-full">
      {mode === 'playing' ? (
        <VideoPlayer projectId={projectId} videoId={video.id} onClose={() => setMode('thumbnail')} />
      ) : mode === 'metrics' ? (
        <EngagementPanel video={video} onBack={() => setMode('thumbnail')} />
      ) : (
        <div className="group relative w-full aspect-video rounded-xl overflow-hidden bg-border cursor-pointer">
          <img
            src={thumbnailUrl(projectId, video.id)}
            alt={video.title ?? ''}
            className="w-full h-full object-cover"
            onError={e => { e.target.src = thumbnailFallbackUrl(projectId, video.id) }}
          />
          {/* Play button on hover */}
          <button
            onClick={() => setMode('playing')}
            className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30"
          >
            <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
              <Play size={16} className="text-bg ml-0.5" fill="currentColor" />
            </div>
          </button>
          {/* Role badge top-left */}
          <div className="absolute top-2 left-2">
            <RoleBadge role={video.role} />
          </div>
          {/* Engagement icon bottom-right */}
          <button
            onClick={e => { e.stopPropagation(); setMode('metrics') }}
            className="absolute bottom-2 right-2 w-6 h-6 rounded-md bg-black/50 flex items-center justify-center opacity-60 hover:opacity-100 transition-opacity"
          >
            <BarChart2 size={12} className="text-white" />
          </button>
        </div>
      )}

      {mode !== 'metrics' && (
        <p className="mt-1.5 text-xs text-muted truncate px-0.5" title={video.title}>
          {video.title ?? video.source_url}
        </p>
      )}
    </div>
  )
}
