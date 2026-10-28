'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ArrowLeft, ShieldCheck } from 'lucide-react'

import { ApprovalPoliciesPanel } from '@/components/tools/approval-policies-panel'
import { AnyPermissionGuard } from '@/components/auth/permission-guard'
import { Card, CardContent } from '@/components/ui/card'

/**
 * Policy administration surface for site, team and entry point layers.
 *
 * Pending approvals and MCP interactions stay inline in chat; this route only
 * manages the mandatory layers those surfaces enforce.
 */
export default function ApprovalPoliciesPage() {
  const t = useTranslations('approvals')

  return (
    <div className="py-6 px-8 h-full overflow-y-auto">
      <div className="mb-6 space-y-3">
        <Link
          href="/app/capabilities"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('backToCapabilities')}
        </Link>
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <ShieldCheck className="h-7 w-7" />
            {t('policy.title')}
          </h1>
          <p className="mt-1 max-w-3xl text-muted-foreground">{t('policy.description')}</p>
        </div>
      </div>

      <AnyPermissionGuard
        permissions={['tool:update', 'admin:settings:update']}
        fallback={
          <Card>
            <CardContent className="py-10">
              <p className="text-sm text-destructive">{t('policy.accessDenied')}</p>
            </CardContent>
          </Card>
        }
      >
        <ApprovalPoliciesPanel />
      </AnyPermissionGuard>
    </div>
  )
}
