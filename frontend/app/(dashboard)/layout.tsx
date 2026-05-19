'use client'

import * as React from 'react'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { useSettings } from '@/hooks/use-settings'
import { AuthGuard } from '@/components/auth-guard'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { sidebarVariant, layoutVariant, direction, mounted } = useSettings()

  // 在 mounted 前使用默认值，避免水合不匹配
  const effectiveSidebarVariant = mounted ? sidebarVariant : 'inset'
  const effectiveLayoutVariant = mounted ? layoutVariant : 'default'
  const effectiveDirection = mounted ? direction : 'ltr'

  // Layout 控制侧边栏状态:
  // - default: 侧边栏完全展开
  // - compact: 侧边栏收缩只显示图标
  // - full: 侧边栏完全隐藏
  const sidebarOpen = effectiveLayoutVariant === 'default'
  const collapsible = effectiveLayoutVariant === 'full' ? 'offExamples' : effectiveLayoutVariant === 'compact' ? 'icon' : 'offExamples'
  
  // Direction 控制侧边栏位置
  const sidebarSide = effectiveDirection === 'rtl' ? 'right' : 'left'

  // 使用受控模式，通过 open 属性来控制侧边栏状态
  const [open, setOpen] = React.useState(sidebarOpen)
  
  // 当 layoutVariant 改变时更新 open 状态
  React.useEffect(() => {
    setOpen(sidebarOpen)
  }, [sidebarOpen])

  return (
    <AuthGuard>
      <SidebarProvider open={open} onOpenChange={setOpen}>
        <AppSidebar
          variant={effectiveSidebarVariant}
          collapsible={collapsible}
          side={sidebarSide}
        />
        <SidebarInset>
          {children}
        </SidebarInset>
      </SidebarProvider>
    </AuthGuard>
  )
}
