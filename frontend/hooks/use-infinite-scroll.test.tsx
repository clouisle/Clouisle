import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { useInfiniteScroll } from './use-infinite-scroll'

type ObserverCallback = ConstructorParameters<typeof IntersectionObserver>[0]

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []

  readonly observed: Element[] = []
  disconnected = false

  constructor(private readonly callback: ObserverCallback) {
    FakeIntersectionObserver.instances.push(this)
  }

  observe(element: Element) {
    this.observed.push(element)
  }

  disconnect() {
    this.disconnected = true
  }

  trigger(isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting, target: this.observed[0] } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    )
  }
}

const originalObserver = globalThis.IntersectionObserver

function Probe({
  hasMore,
  loading,
  onLoadMore,
}: {
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
}) {
  const sentinelRef = useInfiniteScroll({ hasMore, loading, onLoadMore })
  return <div ref={sentinelRef} data-testid="sentinel" />
}

function latestObserver() {
  return FakeIntersectionObserver.instances[FakeIntersectionObserver.instances.length - 1]
}

beforeEach(() => {
  FakeIntersectionObserver.instances = []
  Object.assign(globalThis, { IntersectionObserver: FakeIntersectionObserver })
})

afterEach(() => {
  Object.assign(globalThis, { IntersectionObserver: originalObserver })
})

describe('useInfiniteScroll', () => {
  test('requests once per intersection and waits for a fresh intersecting entry after loading settles', () => {
    let calls = 0
    const onLoadMore = () => {
      calls += 1
    }

    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<Probe hasMore loading={false} onLoadMore={onLoadMore} />)
    })

    expect(latestObserver().observed).toHaveLength(1)
    act(() => latestObserver().trigger(true))
    act(() => latestObserver().trigger(true))
    expect(calls).toBe(1)

    act(() => renderer.update(<Probe hasMore loading onLoadMore={onLoadMore} />))
    act(() => latestObserver().trigger(true))
    expect(calls).toBe(1)

    act(() => renderer.update(<Probe hasMore loading={false} onLoadMore={onLoadMore} />))
    expect(calls).toBe(1)

    act(() => latestObserver().trigger(false))
    expect(calls).toBe(1)
    act(() => latestObserver().trigger(true))
    expect(calls).toBe(2)

    act(() => renderer.unmount())
  })

  test('never auto-retries when the caller disables hasMore after an error', () => {
    let calls = 0
    const onLoadMore = () => {
      calls += 1
    }

    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<Probe hasMore loading={false} onLoadMore={onLoadMore} />)
    })

    act(() => renderer.update(<Probe hasMore={false} loading={false} onLoadMore={onLoadMore} />))
    act(() => latestObserver().trigger(true))
    act(() => latestObserver().trigger(true))

    expect(calls).toBe(0)
    act(() => renderer.unmount())
  })

  test('stops observing when unmounted', () => {
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<Probe hasMore loading={false} onLoadMore={() => {}} />)
    })

    const observer = latestObserver()
    act(() => renderer.unmount())

    expect(observer.disconnected).toBe(true)
  })
})
