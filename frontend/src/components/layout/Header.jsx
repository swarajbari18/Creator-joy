import { Video } from 'lucide-react'

export function Header({ onLogoClick }) {
  return (
    <header className="fixed top-0 left-0 right-0 z-40 h-14 flex items-center px-6 bg-bg/90 backdrop-blur border-b border-border">
      <button
        onClick={onLogoClick}
        className="flex items-center gap-2 hover:opacity-80 transition-opacity"
      >
        <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
          <Video size={14} className="text-white" />
        </div>
        <span className="font-heading font-bold text-white text-base">CreatorJoy</span>
      </button>
    </header>
  )
}
