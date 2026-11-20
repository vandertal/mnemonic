import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface Option<T extends string> {
  value: T
  label: ReactNode
  ariaLabel?: string
}

/** A small radio-style switch (theme, language). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T
  onChange: (v: T) => void
  options: Option<T>[]
  label: string
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn('inline-flex rounded-md border bg-muted p-0.5', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          aria-label={o.ariaLabel}
          onClick={() => onChange(o.value)}
          className={cn(
            'flex h-7 cursor-pointer items-center justify-center gap-1.5 rounded-sm px-2.5 text-xs font-medium text-muted-foreground transition-colors',
            value === o.value && 'bg-card text-foreground shadow-sm',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
