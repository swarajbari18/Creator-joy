import { useEffect, useRef } from 'react'
import { UserMessage } from './UserMessage'
import { AiMessage } from './AiMessage'
import { CollapsibleSkillLog } from './CollapsibleSkillLog'

export function MessageThread({ messages, streaming, currentStreamText, skillLog }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentStreamText])

  const isEmpty = messages.length === 0 && !streaming

  if (isEmpty) {
    return (
      <div className="flex-1 flex items-center justify-center text-center px-6">
        <div>
          <p className="text-white font-heading font-semibold text-lg">Ask anything about your videos</p>
          <p className="text-muted text-sm mt-2">Try: "What's my hook like?" or "Compare my video to the competitor's"</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map(msg => (
        <div key={msg.id}>
          {msg.role === 'user' ? (
            <UserMessage content={msg.content} />
          ) : (
            <>
              {msg.skillEvents && msg.skillEvents.length > 0 && (
                <CollapsibleSkillLog skillLog={msg.skillEvents} />
              )}
              <AiMessage content={msg.content} />
            </>
          )}
        </div>
      ))}

      {streaming && (
        <div>
          {skillLog.length > 0 && <CollapsibleSkillLog skillLog={skillLog} streaming={true} />}
          {currentStreamText && <AiMessage content={currentStreamText} streaming />}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
