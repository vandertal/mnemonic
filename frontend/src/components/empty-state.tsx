import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card } from '@/components/ui/card'

export function EmptyState({
  icon: Icon,
  title,
  text,
  action,
}: {
  icon: LucideIcon
  title: string
  text: string
  action?: ReactNode
}) {
  return (
    <Card className="mx-auto mt-12 flex max-w-md flex-col items-center gap-3 border-dashed p-10 text-center shadow-none">
      <div className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
        <Icon className="size-5" />
      </div>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground">{text}</p>
      {action}
    </Card>
  )
}
