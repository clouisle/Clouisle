'use client'

import * as React from 'react'
import { AuthGuard } from '@/components/auth-guard'
import { useXieyuTransition } from '@/components/layout/xieyu-transition'

function XieyuContent() {
  const { registerPage } = useXieyuTransition()
  React.useEffect(() => {
    registerPage(true)
    return () => registerPage(false)
  }, [registerPage])
  return <main className="min-h-screen bg-background" />
}

export default function XieyuPage() {
  return <AuthGuard><XieyuContent /></AuthGuard>
}
