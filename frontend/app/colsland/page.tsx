'use client'

import { AuthGuard } from '@/components/auth-guard'

// 占位页面：协屿入口将重新设计，旧实现已迁至 /colsland/project。
export default function ColslandPage() {
  return (
    <AuthGuard>
      <main className="min-h-screen bg-background" />
    </AuthGuard>
  )
}
