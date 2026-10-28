'use client'

import { useTranslations } from 'next-intl'
import { ShieldCheck } from 'lucide-react'

import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { ApprovalPoliciesPanel } from '@/components/tools/approval-policies-panel'

/** Administrator policy management for site, team and entry point layers. */
export default function AdminApprovalPoliciesPage() {
  const t = useTranslations('approvals')

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <ShieldCheck className="h-6 w-6" />
              {t('policy.title')}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{t('policy.description')}</p>
          </div>
          <ApprovalPoliciesPanel />
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
