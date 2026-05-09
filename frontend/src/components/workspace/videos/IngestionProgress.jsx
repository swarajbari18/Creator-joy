import { Check, Circle, AlertCircle, RotateCcw } from 'lucide-react'
import { Spinner } from '../../ui/Spinner'

const STAGES = ['downloading', 'transcribing', 'indexing']
const LABELS = { downloading: 'Downloading', transcribing: 'Transcribing', indexing: 'Indexing' }

export function IngestionProgress({ url, stage, error, onRetry }) {
  return (
    <div className="w-full">
      <div className="w-full aspect-video rounded-xl bg-border animate-pulse" />
      <div className="mt-2 px-1 truncate text-xs text-muted">{new URL(url).hostname}</div>

      {error ? (
        <div className="mt-2">
          <div className="flex items-center gap-1.5 text-red-400 text-xs">
            <AlertCircle size={12} /> {error}
          </div>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-1.5 flex items-center gap-1 text-xs text-primary hover:opacity-70 transition-opacity"
            >
              <RotateCcw size={10} /> Retry
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-2">
          {STAGES.map(s => {
            const idx = STAGES.indexOf(s)
            const currentIdx = STAGES.indexOf(stage)
            const done = idx < currentIdx || stage === 'done'
            const active = s === stage
            return (
              <div key={s} className="flex items-center gap-1 text-xs">
                {done ? (
                  <Check size={10} className="text-success" />
                ) : active ? (
                  <Spinner size={10} className="text-primary" />
                ) : (
                  <Circle size={10} className="text-border" />
                )}
                <span className={done ? 'text-success' : active ? 'text-primary' : 'text-border'}>
                  {LABELS[s]}
                </span>
                {idx < 2 && <span className="text-border">·</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
