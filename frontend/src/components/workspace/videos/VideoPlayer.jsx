import { X } from 'lucide-react'
import { videoUrl } from '../../../utils/mediaUrls'

export function VideoPlayer({ projectId, videoId, onClose }) {
  return (
    <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
      <video
        autoPlay
        controls
        src={videoUrl(projectId, videoId)}
        className="w-full h-full object-contain"
      />
      <button
        onClick={onClose}
        className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 flex items-center justify-center text-white hover:bg-black/80 transition-colors"
      >
        <X size={12} />
      </button>
    </div>
  )
}
