'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Home, Zap, ArrowLeft, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type StartNodeType = 'user_input' | 'trigger'

interface StartNodeSelectorProps {
  onSelect: (type: StartNodeType) => void
  onCancel: () => void
}

const startNodeOptions = [
  {
    type: 'user_input' as const,
    icon: Home,
    color: 'bg-primary',
    titleKey: 'startNodes.userInput.title',
    descriptionKey: 'startNodes.userInput.description',
  },
  {
    type: 'trigger' as const,
    icon: Zap,
    color: 'bg-amber-500',
    titleKey: 'startNodes.trigger.title',
    descriptionKey: 'startNodes.trigger.description',
  },
]

export function StartNodeSelector({ onSelect, onCancel }: StartNodeSelectorProps) {
  const t = useTranslations('workflow')

  return (
    <div className="w-full max-w-md">
      <div className="mb-6">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t('startNodes.back')}
        </Button>
      </div>
      
      <div className="rounded-2xl border border-border bg-card p-6 shadow-lg">
        <div className="text-center mb-6">
          <h2 className="text-xl font-semibold">{t('startNodes.selectTitle')}</h2>
          <p className="text-sm text-muted-foreground mt-2">
            {t('startNodes.selectDescription')}
          </p>
        </div>

        <div className="flex flex-col gap-4">
          {startNodeOptions.map((option) => {
            const Icon = option.icon
            return (
              <button
                key={option.type}
                onClick={() => onSelect(option.type)}
                className={cn(
                  'group flex flex-col gap-3 p-4 rounded-xl border-2 border-border',
                  'hover:border-primary hover:bg-primary/5 transition-all text-left',
                  'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2'
                )}
              >
                {/* 预览节点药丸形设计 */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-3 px-3 py-2.5 rounded-full border bg-background shadow-sm flex-1">
                    <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white', option.color)}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <span className="flex-1 text-sm font-medium">
                      {t(option.titleKey)}
                    </span>
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-background text-primary">
                      <Plus className="h-3 w-3" />
                    </div>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed px-1">
                  {t(option.descriptionKey)}
                </p>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
