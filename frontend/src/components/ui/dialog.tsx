import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ComponentProps } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

export const Dialog = DialogPrimitive.Root
export const DialogTitle = DialogPrimitive.Title
export const DialogDescription = DialogPrimitive.Description

/** Centered modal (default) or a side drawer (`side="left"`, used for the mobile sidebar). */
export function DialogContent({
  className,
  children,
  side,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { side?: 'left' }) {
  const { t } = useTranslation()
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50" />
      <DialogPrimitive.Content
        className={cn(
          'fixed z-50 border bg-card shadow-md',
          side === 'left'
            ? 'inset-y-0 left-0 w-72 max-w-[85vw] rounded-r-lg'
            : 'top-1/2 left-1/2 max-h-[85vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg p-6',
          className,
        )}
        {...props}
      >
        {children}
        {side !== 'left' && (
          <DialogPrimitive.Close
            aria-label={t('source.close')}
            className="absolute top-3 right-3 rounded-md p-1.5 text-muted-foreground hover:bg-muted"
          >
            <X className="size-4" />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}
