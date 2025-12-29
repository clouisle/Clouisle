'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import {
  Settings,
  ChevronDown,
  MessageSquare,
  Save,
  Loader2,
} from 'lucide-react'
import type { Agent } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface AgentToolbarProps {
  agent: Agent
  onPublish: () => void
  onSave: () => void
  isSaving: boolean
  onSettingsClick: () => void
}

export function AgentToolbar({
  agent,
  onPublish,
  onSave,
  isSaving,
  onSettingsClick,
}: AgentToolbarProps) {
  const t = useTranslations('agents.orchestration')

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/60">
      <div className="flex items-center gap-2">
        <h2 className="font-semibold text-sm">{t('title')}</h2>
        {agent.model && (
          <Badge variant="secondary" className="text-xs font-normal gap-1">
            <MessageSquare className="h-3 w-3" />
            {agent.model.name}
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Chat Button - Navigate to public chat page */}
        <Link href={`/chat/${agent.id}`} target="_blank">
          <Button variant="outline" size="sm" className="cursor-pointer">
            <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
            {t('toolbar.chat')}
          </Button>
        </Link>

        {/* Settings Button */}
        <Button variant="outline" size="sm" onClick={onSettingsClick} className="cursor-pointer">
          <Settings className="mr-1.5 h-3.5 w-3.5" />
          {t('toolbar.settings')}
        </Button>

        {/* Save Button */}
        <Button variant="outline" size="sm" onClick={onSave} disabled={isSaving} className="cursor-pointer">
          {isSaving ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" />
          )}
          {isSaving ? t('toolbar.saving') : t('toolbar.save')}
        </Button>

        {/* Publish Button */}
        <DropdownMenu>
          <DropdownMenuTrigger className="cursor-pointer inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 h-8 px-3">
            {agent.status === 'published' ? t('toolbar.published') : t('toolbar.publish')}
            <ChevronDown className="h-3.5 w-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onPublish}>
              {agent.status === 'published' ? t('toolbar.confirmUnpublish') : t('toolbar.confirmPublish')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}
