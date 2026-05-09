import { useChat } from '../../../hooks/useChat'
import { MessageThread } from './MessageThread'
import { ChatInput } from './ChatInput'
import { MessageSquare } from 'lucide-react'

export function ChatArea({ project, activeSessionId }) {
  const { messages, streaming, currentStreamText, skillLog, sendMessage } = useChat(project.id, activeSessionId)

  if (!activeSessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-center px-6">
        <div>
          <MessageSquare size={32} className="mx-auto text-muted mb-3" />
          <p className="text-white font-heading font-semibold">Select or create a chat</p>
          <p className="text-muted text-sm mt-1">Use the Chats panel on the left to get started</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-shrink-0 px-6 py-3 border-b border-border">
        <p className="text-xs text-muted">
          <span className="text-white font-medium">{project.name}</span>
          <span className="mx-1.5">›</span>
          <span>Chat</span>
        </p>
      </div>

      <MessageThread
        messages={messages}
        streaming={streaming}
        currentStreamText={currentStreamText}
        skillLog={skillLog}
      />

      <ChatInput onSend={sendMessage} disabled={streaming} />
    </div>
  )
}
