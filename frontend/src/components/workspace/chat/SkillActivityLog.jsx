import { Check, AlertCircle } from 'lucide-react'
import { Spinner } from '../../ui/Spinner'

export function SkillActivityLog({ skillLog }) {
  if (!skillLog || skillLog.length === 0) return null

  return (
    <div className="flex flex-col gap-1 py-1 pl-1">
      {skillLog.map((entry, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          {entry.status === 'complete' ? (
            <Check size={11} className="text-success flex-shrink-0" />
          ) : entry.status === 'error' ? (
            <AlertCircle size={11} className="text-red-400 flex-shrink-0" />
          ) : (
            <Spinner size={11} className="text-primary flex-shrink-0" />
          )}
          <span className={
            entry.status === 'complete' ? 'text-success/80' :
            entry.status === 'error' ? 'text-red-400' :
            'text-muted'
          }>
            {entry.status === 'active'
              ? `Using ${entry.skill}…`
              : entry.status === 'complete'
              ? `${entry.skill} complete`
              : `${entry.skill} failed`}
          </span>
        </div>
      ))}
    </div>
  )
}
