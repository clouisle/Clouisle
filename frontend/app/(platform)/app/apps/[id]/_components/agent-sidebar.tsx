'use client'

import * as React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  LayoutGrid,
  Code2,
  FileText,
  Activity,
  ArrowLeft,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Agent } from '@/lib/api'

interface AgentSidebarProps {
  agent: Agent
  collapsed?: boolean
  backHref?: string
  baseUrl?: string
}

export function AgentSidebar({
  agent,
  collapsed = false,
  backHref = '/app/apps',
  baseUrl = `/app/apps/${agent.id}`,
}: AgentSidebarProps) {
  const t = useTranslations('agents.orchestration.sidebar')
  const pathname = usePathname()

  // Check if icon is a URL or emoji
  const isIconUrl = agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))

  const navItems = [
    {
      title: t('orchestration'),
      href: baseUrl,
      icon: LayoutGrid,
      testId: 'agent-nav-orchestration',
    },
    {
      title: t('api'),
      href: `${baseUrl}/api`,
      icon: Code2,
      testId: 'agent-nav-api',
    },
    {
      title: t('logs'),
      href: `${baseUrl}/logs`,
      icon: FileText,
      testId: 'agent-nav-logs',
    },
    {
      title: t('monitor'),
      href: `${baseUrl}/monitor`,
      icon: Activity,
      testId: 'agent-nav-monitor',
    },
  ]

  if (collapsed) {
    return null
  }

  return (
    <aside
      data-testid="agent-sidebar"
      className={cn(
      'border-r flex flex-col h-full transition-all duration-200',
      collapsed ? 'w-0 overflow-hidden' : 'w-52'
    )}>
      {/* Agent Info */}
      <div className="p-4">
        <div className="flex items-center justify-between">
          <Link 
            href={backHref}
            className="flex items-center gap-3 min-w-0 group"
          >
            <div className="shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center relative overflow-hidden">
              {agent.icon ? (
                isIconUrl ? (
                  <Image
                    src={agent.icon}
                    alt={agent.name}
                    fill
                    unoptimized
                    className="object-cover group-hover:opacity-0 transition-opacity"
                  />
                ) : (
                  <span className="flex h-full w-full items-center justify-center leading-none text-xl group-hover:opacity-0 transition-opacity">{agent.icon}</span>
                )
              ) : (
                <Sparkles className="h-5 w-5 text-primary group-hover:opacity-0 transition-opacity" />
              )}
              <ArrowLeft className="h-5 w-5 text-primary absolute opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <div className="min-w-0">
              <h2 className="font-semibold truncate">{agent.name}</h2>
              <span className="text-xs text-muted-foreground uppercase tracking-wider">
                Agent
              </span>
            </div>
          </Link>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  data-testid={item.testId}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.title}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
