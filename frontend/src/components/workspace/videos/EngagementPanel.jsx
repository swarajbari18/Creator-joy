import { ChevronLeft } from 'lucide-react'
import { formatEngagementForDisplay } from '../../../utils/parseEngagement'

function Row({ label, value }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-border/50 last:border-0">
      <span className="text-muted text-xs">{label}</span>
      <span className="text-white text-xs font-medium">{value ?? '—'}</span>
    </div>
  )
}

export function EngagementPanel({ video, onBack }) {
  const m = formatEngagementForDisplay(video.engagement_metrics)

  return (
    <div className="w-full rounded-xl bg-surface/80 border border-border p-3">
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-muted text-xs mb-2 hover:text-white transition-colors"
      >
        <ChevronLeft size={12} /> Back
      </button>
      <p className="text-white text-xs font-semibold truncate mb-2">{video.title ?? 'Untitled'}</p>
      <div className="space-y-0">
        <Row label="Views" value={m.views} />
        <Row label="Likes" value={m.likes} />
        <Row label="Comments" value={m.comments} />
        <Row label="ER (views)" value={m.erViews} />
        <Row label="Like rate" value={m.likeRate} />
        <Row label="Duration" value={m.duration} />
        <Row label="Uploaded" value={m.age} />
        <Row label="Heatmap peak" value={m.heatmapPeak} />
      </div>
    </div>
  )
}
