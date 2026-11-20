import type { InputHTMLAttributes, Ref } from 'react'
import { cn } from '@/lib/utils'

export function Input({ className, ref, ...props }: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-10 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm placeholder:text-muted-foreground aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  )
}
