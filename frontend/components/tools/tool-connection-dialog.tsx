'use client'

import { useTranslations } from 'next-intl'

import { ToolConnectionManager } from '@/components/tools/connection-picker'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Tool, ToolDetail } from '@/lib/api'

export interface ToolConnectionDialogProps {
  tool?: Tool | ToolDetail | null
  teamId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onChanged?: () => void
}

/**
 * Team-scoped connection manager for one tool.
 *
 * The legacy plaintext ToolConfig dialog was removed; identities are managed
 * through encrypted connections. A tool without a resolved stable definition
 * policy cannot be configured and says so explicitly instead of pretending the
 * tool needs no identity.
 */
export function ToolConnectionDialog({
  tool,
  teamId,
  open,
  onOpenChange,
  onChanged,
}: ToolConnectionDialogProps) {
  const t = useTranslations('platform.tools')

  if (!tool) return null

  const identity = tool.identity_policy
  const hasService = Boolean(tool.id) || tool.type === 'builtin'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {tool.icon ? <span className="text-xl">{tool.icon}</span> : null}
            {t('configDialog.title', { name: tool.display_name })}
          </DialogTitle>
          <DialogDescription>
            {t('connectionDialog.description')}
          </DialogDescription>
        </DialogHeader>

        {!identity ? (
          <p className="py-4 text-sm text-muted-foreground">
            {t('connectionDialog.definitionUnavailable')}
          </p>
        ) : identity === 'none' && tool.requires_config ? (
          <p className="py-4 text-sm text-muted-foreground">
            {t('connectionDialog.definitionUnavailable')}
          </p>
        ) : identity === 'none' ? (
          <p className="py-4 text-sm text-muted-foreground">
            {t('connectionDialog.notRequired')}
          </p>
        ) : !teamId ? (
          <p className="py-4 text-sm text-destructive">
            {t('connectionDialog.teamRequired')}
          </p>
        ) : !hasService ? (
          <p className="py-4 text-sm text-muted-foreground">
            {t('connectionDialog.definitionUnavailable')}
          </p>
        ) : (
          <ToolConnectionManager
            tool={tool.id ? tool : null}
            builtinToolKey={tool.id ? undefined : tool.name}
            teamId={teamId}
            identity={identity}
            onChanged={() => onChanged?.()}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
