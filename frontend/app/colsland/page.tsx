'use client'

import * as React from 'react'
import { AuthGuard } from '@/components/auth-guard'
import { useColslandTransition } from '@/components/layout/colsland-transition'
import { BlockEditor } from './_components/block-editor'
import { ProjectSelector } from './_components/project-selector'
import { ProjectAssets } from './_components/project-assets'

function ColslandContent() {
  const { registerPage } = useColslandTransition()
  React.useEffect(() => {
    registerPage(true)
    return () => registerPage(false)
  }, [registerPage])
  return <main className="min-h-screen bg-background"><div className="space-y-4 px-4 pt-4 sm:px-6 lg:fixed lg:left-6 lg:top-6 lg:w-64 lg:px-0 lg:pt-0"><ProjectSelector /><ProjectAssets /></div><div className="lg:pl-72"><BlockEditor /></div></main>
}

export default function ColslandPage() {
  return <AuthGuard><ColslandContent /></AuthGuard>
}
