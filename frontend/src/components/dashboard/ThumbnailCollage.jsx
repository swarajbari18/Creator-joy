import { thumbnailUrl, thumbnailFallbackUrl } from '../../utils/mediaUrls'
import { ImageIcon } from 'lucide-react'

export function ThumbnailCollage({ videos }) {
  const cells = videos.slice(0, 4)
  const placeholders = Array(Math.max(0, 4 - cells.length)).fill(null)

  return (
    <div className="grid grid-cols-2 gap-1 w-full aspect-video rounded-xl overflow-hidden">
      {cells.map(v => (
        <img
          key={v.id}
          src={thumbnailUrl(v.project_id, v.id)}
          alt={v.title ?? ''}
          className="w-full h-full object-cover bg-border"
          onError={e => { e.target.src = thumbnailFallbackUrl(v.project_id, v.id) }}
        />
      ))}
      {placeholders.map((_, i) => (
        <div key={i} className="w-full h-full bg-border flex items-center justify-center">
          <ImageIcon size={20} className="text-muted/40" />
        </div>
      ))}
    </div>
  )
}
