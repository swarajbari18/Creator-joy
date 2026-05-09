export function UserMessage({ content }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-primary text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
        {content}
      </div>
    </div>
  )
}
