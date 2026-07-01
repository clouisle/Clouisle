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
  PanelLeftClose,
  PanelLeft,
  Code,
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface AgentToolbarProps {
  agent: Agent
  onPublish: () => void
  onSave: () => void
  isSaving: boolean
  onSettingsClick: () => void
  onEmbedClick: () => void
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
  canUpdate?: boolean
  canPublish?: boolean
}

export function AgentToolbar({
  agent,
  onPublish,
  onSave,
  isSaving,
  onSettingsClick,
  onEmbedClick,
  sidebarCollapsed,
  onToggleSidebar,
  canUpdate = false,
  canPublish = false,
}: AgentToolbarProps) {
  const t = useTranslations('agents.orchestration')

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/60">
      <div className="flex items-center gap-2">
        {/* Toggle Sidebar Button */}
        <Tooltip>
          <TooltipTrigger
            render={(props) => (
              <Button
                {...props}
                variant="ghost"
                size="icon"
                className="h-8 w-8 cursor-pointer"
                onClick={onToggleSidebar}
              >
                {sidebarCollapsed ? (
                  <PanelLeft className="h-4 w-4" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" />
                )}
              </Button>
            )}
          />
          <TooltipContent side="bottom">
            {sidebarCollapsed ? t('toolbar.showSidebar') : t('toolbar.hideSidebar')}
          </TooltipContent>
        </Tooltip>
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
          <Button data-testid="agent-chat-button" variant="outline" size="sm" className="cursor-pointer">
            <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
            {t('toolbar.chat')}
          </Button>
        </Link>

        {canUpdate && (
          <>
            {/* Embed Button */}
            <Button data-testid="agent-embed-button" variant="outline" size="sm" onClick={onEmbedClick} className="cursor-pointer">
              <Code className="mr-1.5 h-3.5 w-3.5" />
              {t('toolbar.embed')}
            </Button>

            {/* Settings Button */}
            <Button data-testid="agent-settings-button" variant="outline" size="sm" onClick={onSettingsClick} className="cursor-pointer">
              <Settings className="mr-1.5 h-3.5 w-3.5" />
              {t('toolbar.settings')}
            </Button>

            {/* Save Button */}
            <Button data-testid="agent-save-button" variant="outline" size="sm" onClick={onSave} disabled={isSaving} className="cursor-pointer">
              {isSaving ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-3.5 w-3.5" />
              )}
              {isSaving ? t('toolbar.saving') : t('toolbar.save')}
            </Button>
          </>
        )}

        {canPublish && (
          <DropdownMenu>
            <DropdownMenuTrigger data-testid="agent-publish-button" className="cursor-pointer inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 h-8 px-3">
              {agent.status === 'published' ? t('toolbar.published') : t('toolbar.publish')}
              <ChevronDown className="h-3.5 w-3.5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem data-testid="agent-publish-confirm" onClick={onPublish}>
                {agent.status === 'published' ? t('toolbar.confirmUnpublish') : t('toolbar.confirmPublish')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  )
}
