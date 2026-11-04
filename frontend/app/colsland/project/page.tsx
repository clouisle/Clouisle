'use client'

import { AuthGuard } from '@/components/auth-guard'
import { BlockEditor } from './_components/block-editor'
import { ProjectCardStack } from './_components/project-card-stack'

function ColslandContent() {
  return <main className="min-h-screen bg-background"><div className="px-4 pt-4 sm:px-6 lg:fixed lg:left-6 lg:top-6 lg:z-20 lg:w-[min(400px,calc(100vw-3rem))] lg:px-0 lg:pt-0"><ProjectCardStack /></div><div className="lg:pl-[26.5rem]"><BlockEditor /></div></main>
}

export default function ColslandPage() {
  return <AuthGuard><ColslandContent /></AuthGuard>
}
