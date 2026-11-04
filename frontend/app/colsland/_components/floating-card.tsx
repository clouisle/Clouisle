'use client'

import * as React from 'react'
import { ChevronDown } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

interface FloatingCardProps {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FloatingCard({ title, icon, children, open, onOpenChange }: FloatingCardProps) {

  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className="relative flex min-h-0 w-full flex-col overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-lg shadow-black/5" style={{ height: open ? '100%' : undefined }}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-2xl p-4 text-left text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {icon}<span className="min-w-0 flex-1 truncate">{title}</span>
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 text-xs leading-relaxed text-muted-foreground">
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
