'use client'

import * as React from 'react'

export interface UseInfiniteScrollOptions {
  /** Whether another page can still be requested. */
  hasMore: boolean
  /** Whether a page is currently in flight (initial load or load more). */
  loading: boolean
  /** Requests the next page. Must be a no-op while `loading` or `!hasMore`. */
  onLoadMore: () => void
  /** How far below the viewport the sentinel pre-fetches. */
  rootMargin?: string
}

/**
 * Observes an always-mounted sentinel and calls `onLoadMore` when it enters the
 * viewport. The sentinel may live inside a nested scroll container: the
 * browser's default viewport root already accounts for ancestor clipping.
 *
 * The observer is reconnected on every render, so its initial entry always
 * reflects the sentinel's current geometry. After a page settles (`loading`
 * returns to false), the next request waits for that fresh entry instead of
 * reusing a cached "was intersecting" flag — an append that pushes the sentinel
 * out of view therefore stops further loading rather than draining the list.
 *
 * Request deduplication: a single intersecting entry triggers at most one
 * request. When the caller signals `hasMore = false` (end of list or an error),
 * no request is made, so failures never auto-retry in a loop.
 */
export function useInfiniteScroll({
  hasMore,
  loading,
  onLoadMore,
  rootMargin = '200px',
}: UseInfiniteScrollOptions): React.RefObject<HTMLDivElement | null> {
  const sentinelRef = React.useRef<HTMLDivElement | null>(null)
  const hasMoreRef = React.useRef(hasMore)
  const loadingRef = React.useRef(loading)
  const onLoadMoreRef = React.useRef(onLoadMore)
  const requestedRef = React.useRef(false)

  React.useEffect(() => {
    hasMoreRef.current = hasMore
    loadingRef.current = loading
    onLoadMoreRef.current = onLoadMore
  })

  const requestMore = React.useCallback(() => {
    if (loadingRef.current || !hasMoreRef.current || requestedRef.current) return
    requestedRef.current = true
    onLoadMoreRef.current()
  }, [])

  React.useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[entries.length - 1]
        if (!entry) return
        if (entry.isIntersecting) {
          requestMore()
        } else {
          requestedRef.current = false
        }
      },
      { root: null, rootMargin },
    )
    observer.observe(sentinel)

    return () => observer.disconnect()
  })

  React.useEffect(() => {
    if (loading) return
    requestedRef.current = false
  }, [hasMore, loading])

  return sentinelRef
}
