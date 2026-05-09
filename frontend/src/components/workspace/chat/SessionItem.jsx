import clsx from 'clsx'
import { formatRelativeDate } from '../../../utils/formatDate'

export function SessionItem({ session, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left px-3 py-2 rounded-lg transition-colors border-l-2',
        active
          ? 'border-primary bg-primary/10 text-white'
          : 'border-transparent text-muted hover:text-white hover:bg-surface'
      )}
    >
      <p className="text-xs font-medium truncate leading-tight">
        {session.label || session.first_message || 'New Chat'}
      </p>
      <p className="text-[10px] text-muted/60 mt-0.5">
        {formatRelativeDate(session.last_active ?? session.created_at)}
      </p>
    </button>
  )
}
