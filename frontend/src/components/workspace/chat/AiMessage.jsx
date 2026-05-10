import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function AiMessage({ content, streaming = false }) {
  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] bg-surface border border-border rounded-2xl rounded-tl-sm px-4 py-2.5 prose-chat ${streaming ? 'cursor-blink' : ''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content || (streaming ? '' : '…')}
        </ReactMarkdown>
      </div>
    </div>
  )
}
