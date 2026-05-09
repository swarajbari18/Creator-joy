export function AiMessage({ content, streaming = false }) {
  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] bg-surface border border-border rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed text-white whitespace-pre-wrap ${streaming ? 'cursor-blink' : ''}`}>
        {content || (streaming ? '' : '…')}
      </div>
    </div>
  )
}
