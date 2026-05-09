import { Plus, MessageSquare } from 'lucide-react'
import { SessionItem } from './SessionItem'

export function ChatSection({ sessions, activeSessionId, onSelectSession, onNewSession }) {
  return (
    <div className="flex flex-col h-64 flex-shrink-0 border-t border-border">
      <div className="flex items-center justify-between px-4 py-3 flex-shrink-0">
        <span className="text-xs font-semibold text-muted uppercase tracking-wider">Chats</span>
        <button
          onClick={onNewSession}
          className="w-6 h-6 rounded-md bg-surface hover:bg-border flex items-center justify-center transition-colors"
          title="New Chat"
        >
          <Plus size={13} className="text-muted hover:text-white transition-colors" />
        </button>
      </div>

      <div className="overflow-y-auto flex-1 px-2 pb-2 space-y-0.5 min-h-0">
        {sessions.length === 0 ? (
          <div className="text-center py-4 text-muted text-xs">
            <MessageSquare size={16} className="mx-auto mb-1 opacity-40" />
            No chats yet
          </div>
        ) : (
          sessions.map(s => (
            <SessionItem
              key={s.id}
              session={s}
              active={s.id === activeSessionId}
              onClick={() => onSelectSession(s.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}
