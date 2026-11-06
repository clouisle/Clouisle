'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'

export default function NotificationsPage() {
  const router = useRouter()

  React.useEffect(() => {
    router.replace('/app')
  }, [router])

  return null
}
