'use client'

import * as React from 'react'
import { AuthGuard } from '@/components/auth-guard'
import { useColslandTransition } from '@/components/layout/colsland-transition'

function ColslandContent() {
  const { registerPage } = useColslandTransition()
  React.useEffect(() => {
    registerPage(true)
    return () => registerPage(false)
  }, [registerPage])
  return <main className="min-h-screen bg-background" />
}

export default function ColslandPage() {
  return <AuthGuard><ColslandContent /></AuthGuard>
}
