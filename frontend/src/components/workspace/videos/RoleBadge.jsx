export function RoleBadge({ role }) {
  if (!role) return null
  const isCreator = role === 'creator'
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${
      isCreator
        ? 'bg-primary/30 text-primary'
        : 'bg-accent/30 text-accent'
    }`}>
      {isCreator ? 'Creator' : 'Competitor'}
    </span>
  )
}
