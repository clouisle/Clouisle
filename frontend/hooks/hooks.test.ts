import { beforeEach, describe, expect, mock, test } from 'bun:test'

type EffectSlot = {
  cleanup?: () => void
  dependencies?: readonly unknown[]
}

let states: unknown[] = []
let effects: EffectSlot[] = []
let stateIndex = 0
let effectIndex = 0
let pathname = '/items'
let searchParams = new URLSearchParams()
const replace = mock(() => {})

function beginRender() {
  stateIndex = 0
  effectIndex = 0
}

function resetHooks() {
  effects.forEach(effect => effect.cleanup?.())
  states = []
  effects = []
  beginRender()
}

mock.module('react', () => ({
  useState<T>(initialValue: T | (() => T)) {
    const index = stateIndex++
    if (!(index in states)) {
      states[index] = typeof initialValue === 'function'
        ? (initialValue as () => T)()
        : initialValue
    }

    const setState = (value: T | ((current: T) => T)) => {
      states[index] = typeof value === 'function'
        ? (value as (current: T) => T)(states[index] as T)
        : value
    }

    return [states[index] as T, setState] as const
  },
  useEffect(effect: () => void | (() => void), dependencies?: readonly unknown[]) {
    const index = effectIndex++
    const previous = effects[index]
    const changed = !previous?.dependencies
      || !dependencies
      || dependencies.some((dependency, dependencyIndex) => !Object.is(dependency, previous.dependencies?.[dependencyIndex]))

    if (!changed) return

    previous?.cleanup?.()
    const cleanup = effect()
    effects[index] = {
      cleanup: cleanup || undefined,
      dependencies,
    }
  },
}))

mock.module('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}))

const { useDebounce } = await import('./use-debounce')
const { useUrlSearchState } = await import('./use-url-search-state')

beforeEach(() => {
  resetHooks()
  pathname = '/items'
  searchParams = new URLSearchParams()
  replace.mockClear()
})

describe('useDebounce', () => {
  test('keeps the current value until the latest delay expires', () => {
    const callbacks = new Map<number, () => void>()
    const cleared: number[] = []
    let nextTimer = 1
    const originalWindow = globalThis.window
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        setTimeout(callback: () => void) {
          const timer = nextTimer++
          callbacks.set(timer, callback)
          return timer
        },
        clearTimeout(timer: number) {
          cleared.push(timer)
          callbacks.delete(timer)
        },
      },
    })

    beginRender()
    expect(useDebounce('first', 100)).toBe('first')

    beginRender()
    expect(useDebounce('second', 100)).toBe('first')
    expect(cleared).toEqual([1])

    callbacks.get(2)?.()
    beginRender()
    expect(useDebounce('second', 100)).toBe('second')

    resetHooks()
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    })
  })
})

describe('useUrlSearchState', () => {
  test('initializes from the URL without replacing an equivalent query', () => {
    searchParams = new URLSearchParams('page=2&search=existing')

    beginRender()
    const [search] = useUrlSearchState()

    expect(search).toBe('existing')
    expect(replace).not.toHaveBeenCalled()
  })

  test('trims updates and preserves unrelated query parameters', () => {
    searchParams = new URLSearchParams('page=2')

    beginRender()
    const [, setSearch] = useUrlSearchState()
    setSearch('  new value  ')
    beginRender()
    useUrlSearchState()

    expect(replace).toHaveBeenLastCalledWith('/items?page=2&search=new+value', { scroll: false })
  })

  test('removes an empty search parameter without dropping the rest of the query', () => {
    searchParams = new URLSearchParams('page=2&search=existing')

    beginRender()
    const [, setSearch] = useUrlSearchState()
    setSearch('   ')
    beginRender()
    useUrlSearchState()

    expect(replace).toHaveBeenLastCalledWith('/items?page=2', { scroll: false })
  })
})
