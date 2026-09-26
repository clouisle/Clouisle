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
  Eye,
  MoreHorizontal,
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
  onPreviewClick: () => void
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
  onPreviewClick,
  sidebarCollapsed,
  onToggleSidebar,
  canUpdate = false,
  canPublish = false,
}: AgentToolbarProps) {
  const t = useTranslations('agents.orchestration')

  return (
    <div className="flex items-center justify-between gap-2 px-2 py-2 sm:px-4 bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/60">
      <div className="flex min-w-0 items-center gap-2">
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
        <h2 className="whitespace-nowrap font-semibold text-sm">{t('title')}</h2>
        {agent.model && (
          <Badge variant="secondary" className="hidden text-xs font-normal gap-1 lg:flex">
            <MessageSquare className="h-3 w-3" />
            {agent.model.name}
          </Badge>
        )}
      </div>

      <div className="flex min-w-0 shrink-0 items-center gap-1">
      <div className="hidden shrink-0 items-center gap-2 md:flex">
        <Link href={`/chat/${agent.id}`} target="_blank" rel="noreferrer">
          <Button data-testid="agent-chat-button" variant="outline" size="sm" className="cursor-pointer">
            <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
            {t('toolbar.chat')}
          </Button>
        </Link>
        {canUpdate && (
          <>
            <Button data-testid="agent-embed-button" variant="outline" size="sm" onClick={onEmbedClick} className="cursor-pointer">
              <Code className="mr-1.5 h-3.5 w-3.5" />
              {t('toolbar.embed')}
            </Button>
            <Button data-testid="agent-settings-button" variant="outline" size="sm" onClick={onSettingsClick} className="cursor-pointer">
              <Settings className="mr-1.5 h-3.5 w-3.5" />
              {t('toolbar.settings')}
            </Button>
            <Button data-testid="agent-save-button" variant="outline" size="sm" onClick={onSave} disabled={isSaving} className="cursor-pointer">
              {isSaving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
              {isSaving ? t('toolbar.saving') : t('toolbar.save')}
            </Button>
          </>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1 md:hidden">
        <Button data-testid="agent-mobile-preview-button" variant="outline" size="icon" aria-label={t('toolbar.preview')} onClick={onPreviewClick} className="h-8 w-8 cursor-pointer">
          <Eye className="h-4 w-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button data-testid="agent-mobile-actions-button" variant="outline" size="icon" aria-label={t('toolbar.moreActions')} className="h-8 w-8 cursor-pointer"><MoreHorizontal className="h-4 w-4" /></Button>} />
          <DropdownMenuContent align="end">
            <DropdownMenuItem data-testid="agent-mobile-chat-link" render={<Link href={`/chat/${agent.id}`} target="_blank" rel="noreferrer" />}>
              <MessageSquare />
              {t('toolbar.chat')}
            </DropdownMenuItem>
            {canUpdate && (
              <>
                <DropdownMenuItem data-testid="agent-mobile-embed-action" onClick={onEmbedClick}>
                  <Code />
                  {t('toolbar.embed')}
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="agent-mobile-settings-action" onClick={onSettingsClick}>
                  <Settings />
                  {t('toolbar.settings')}
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="agent-mobile-save-action" onClick={onSave} disabled={isSaving}>
                  {isSaving ? <Loader2 className="animate-spin" /> : <Save />}
                  {isSaving ? t('toolbar.saving') : t('toolbar.save')}
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
        {canPublish && (
          <DropdownMenu>
            <DropdownMenuTrigger data-testid="agent-publish-button" aria-label={agent.status === 'published' ? t('toolbar.published') : t('toolbar.publish')} className="cursor-pointer inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow-xs hover:bg-primary/90 h-8 px-2 md:px-3">
              <span className="sr-only md:not-sr-only">{agent.status === 'published' ? t('toolbar.published') : t('toolbar.publish')}</span>
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
