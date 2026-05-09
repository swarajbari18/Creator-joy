import clsx from 'clsx'

export function Button({ children, onClick, variant = 'primary', size = 'md', disabled, className, type = 'button' }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 font-medium rounded-lg transition-colors focus:outline-none',
        size === 'sm' && 'px-3 py-1.5 text-sm',
        size === 'md' && 'px-4 py-2 text-sm',
        size === 'lg' && 'px-5 py-2.5 text-base',
        variant === 'primary' && 'bg-primary text-white hover:bg-primary-hover disabled:opacity-50',
        variant === 'ghost' && 'text-muted hover:text-white hover:bg-surface',
        variant === 'surface' && 'bg-surface text-white hover:bg-border',
        disabled && 'cursor-not-allowed',
        className,
      )}
    >
      {children}
    </button>
  )
}
