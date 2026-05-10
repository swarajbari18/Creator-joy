import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Check, AlertCircle } from 'lucide-react'
import { SkillActivityLog } from './SkillActivityLog'
import { Spinner } from '../../ui/Spinner'

export function CollapsibleSkillLog({ skillLog, streaming = false }) {
  const [isOpen, setIsOpen] = useState(streaming)
  if (!skillLog || skillLog.length === 0) return null

  // Auto-open when streaming starts, auto-close when it finishes
  useEffect(() => {
    setIsOpen(streaming)
  }, [streaming])

  const activeEntry = skillLog.find(s => s.status === 'active')
  const hasError = skillLog.some(s => s.status === 'error')
  const completedCount = skillLog.filter(s => s.status === 'complete').length
  const totalCount = skillLog.length

  return (
    <div className="mb-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-xs py-1.5 transition-colors hover:opacity-80"
      >
        <div className="flex items-center justify-center w-4 h-4">
          {activeEntry ? (
            <Spinner size={12} className="text-primary" />
          ) : hasError ? (
            <AlertCircle size={12} className="text-red-400" />
          ) : (
            <Check size={12} className="text-success" />
          )}
        </div>
        
        <span className="font-bold text-primary uppercase tracking-widest text-[11px]">
          Thoughts
        </span>

        <span className="text-[10px] text-muted/40 ml-1">
          ({completedCount}/{totalCount})
        </span>
        
        <div className="ml-auto opacity-30">
          {isOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        </div>
      </button>
      
      {isOpen && (
        <div className="mt-1 ml-2 pl-4 border-l border-border/20">
          <SkillActivityLog skillLog={skillLog} />
        </div>
      )}
    </div>
  )
}
