import clsx from 'clsx'

export function Badge({ children, color = 'primary', className }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
      color === 'primary' && 'bg-primary/20 text-primary',
      color === 'accent' && 'bg-accent/20 text-accent',
      color === 'success' && 'bg-success/20 text-success',
      color === 'muted' && 'bg-border text-muted',
      className,
    )}>
      {children}
    </span>
  )
}
