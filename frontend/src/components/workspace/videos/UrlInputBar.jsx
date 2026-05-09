import { useState } from 'react'
import { ArrowRight } from 'lucide-react'

export function UrlInputBar({ onSubmit }) {
  const [url, setUrl] = useState('')
  const [role, setRole] = useState('creator')

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) return
    onSubmit(trimmed, role)
    setUrl('')
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 mt-2 px-1">
      <input
        autoFocus
        value={url}
        onChange={e => setUrl(e.target.value)}
        placeholder="Paste video URL…"
        className="w-full bg-bg border border-border rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-muted/50 focus:outline-none focus:border-primary transition-colors"
      />
      <div className="flex items-center gap-2">
        <div className="flex rounded-lg border border-border overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setRole('creator')}
            className={`px-2.5 py-1 transition-colors ${role === 'creator' ? 'bg-primary text-white' : 'text-muted hover:text-white'}`}
          >
            Creator
          </button>
          <button
            type="button"
            onClick={() => setRole('competitor')}
            className={`px-2.5 py-1 transition-colors ${role === 'competitor' ? 'bg-accent text-white' : 'text-muted hover:text-white'}`}
          >
            Competitor
          </button>
        </div>
        <button
          type="submit"
          disabled={!url.trim()}
          className="ml-auto w-7 h-7 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-40 flex items-center justify-center transition-colors"
        >
          <ArrowRight size={13} className="text-white" />
        </button>
      </div>
    </form>
  )
}
