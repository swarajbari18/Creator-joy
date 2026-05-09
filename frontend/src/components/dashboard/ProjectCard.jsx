import { ThumbnailCollage } from './ThumbnailCollage'
import { formatRelativeDate } from '../../utils/formatDate'
import { MessageSquare, Video } from 'lucide-react'

export function ProjectCard({ project, videos, onClick }) {
  return (
    <button
      onClick={onClick}
      className="group text-left w-full bg-surface border border-border rounded-2xl p-4 hover:border-primary/50 hover:shadow-[0_0_20px_rgba(14,165,233,0.12)] transition-all duration-200 hover:scale-[1.01]"
    >
      <ThumbnailCollage videos={videos} />
      <div className="mt-3">
        <h3 className="font-heading font-bold text-white text-base leading-tight truncate group-hover:text-primary transition-colors">
          {project.name}
        </h3>
        <div className="flex items-center gap-3 mt-2 text-xs text-muted">
          <span className="flex items-center gap-1">
            <Video size={12} /> {videos.length} {videos.length === 1 ? 'video' : 'videos'}
          </span>
          <span className="text-border">·</span>
          <span>{formatRelativeDate(project.updated_at)}</span>
        </div>
      </div>
    </button>
  )
}
