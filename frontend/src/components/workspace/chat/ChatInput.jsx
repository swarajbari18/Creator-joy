import { useState } from 'react'
import { ArrowUp } from 'lucide-react'

export function ChatInput({ onSend, disabled }) {
  const [text, setText] = useState('')

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  return (
    <div className="flex items-end gap-2 p-4 border-t border-border bg-bg">
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Ask about your videos…"
        disabled={disabled}
        rows={1}
        className="flex-1 bg-surface border border-border rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-muted/50 focus:outline-none focus:border-primary resize-none transition-colors disabled:opacity-50"
        style={{ maxHeight: 120, overflowY: 'auto' }}
      />
      <button
        onClick={submit}
        disabled={!text.trim() || disabled}
        className="w-9 h-9 rounded-xl bg-primary hover:bg-primary-hover disabled:opacity-40 flex items-center justify-center transition-colors flex-shrink-0"
      >
        <ArrowUp size={16} className="text-white" />
      </button>
    </div>
  )
}
