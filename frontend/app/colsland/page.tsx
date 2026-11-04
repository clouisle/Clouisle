'use client'

import * as React from 'react'
import { AuthGuard } from '@/components/auth-guard'
import { useColslandTransition } from '@/components/layout/colsland-transition'
import { BlockEditor } from './_components/block-editor'
import { ProjectSelector } from './_components/project-selector'

function ColslandContent() {
  const { registerPage } = useColslandTransition()
  React.useEffect(() => {
    registerPage(true)
    return () => registerPage(false)
  }, [registerPage])
  return <main className="min-h-screen bg-background pt-16"><ProjectSelector /><BlockEditor /></main>
}

export default function ColslandPage() {
  return <AuthGuard><ColslandContent /></AuthGuard>
}
