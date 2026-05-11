'use client'

import * as React from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

export function useUrlSearchState() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [search, setSearch] = React.useState(() => searchParams.get('search') || '')

  React.useEffect(() => {
    setSearch(searchParams.get('search') || '')
  }, [searchParams])

  React.useEffect(() => {
    const nextParams = new URLSearchParams(searchParams.toString())
    const trimmedSearch = search.trim()

    if (trimmedSearch) {
      nextParams.set('search', trimmedSearch)
    } else {
      nextParams.delete('search')
    }

    const nextQuery = nextParams.toString()
    const currentQuery = searchParams.toString()
    if (nextQuery === currentQuery) return

    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false })
  }, [pathname, router, search, searchParams])

  return [search, setSearch] as const
}
