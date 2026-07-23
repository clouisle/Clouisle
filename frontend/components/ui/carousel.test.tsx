import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let context: Record<string, unknown> | null = null
const scrollPrev = mock(() => {})
const scrollNext = mock(() => {})
const on = mock(() => {})
const off = mock(() => {})
const cleanups: Array<() => void> = []
const api = {
  canScrollPrev: () => true,
  canScrollNext: () => false,
  scrollPrev,
  scrollNext,
  on,
  off,
}

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  createContext: () => ({ Provider: function Provider() {} }),
  useContext: () => context,
  useState: (value: unknown) => [value, mock(() => {})],
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | (() => void)) => {
    const cleanup = effect()
    if (cleanup) cleanups.push(cleanup)
  },
}))
mock.module('embla-carousel-react', () => ({ default: () => [mock(() => {}), api] }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/components/ui/button', () => ({ Button: function Button() {} }))
mock.module('lucide-react', () => ({
  ChevronLeftIcon: function ChevronLeftIcon() {},
  ChevronRightIcon: function ChevronRightIcon() {},
}))

const { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious, useCarousel } =
  await import('./carousel')

test('configures a carousel and maps keyboard navigation to its API', () => {
  const setApi = mock(() => {})
  const tree = Carousel({
    orientation: 'vertical',
    opts: { loop: true },
    setApi,
    className: 'gallery',
  }) as {
    props: Record<string, unknown>
  }
  const event = { key: 'ArrowLeft', preventDefault: mock(() => {}) }
  const ignored = { key: 'Enter', preventDefault: mock(() => {}) }

  const carousel = tree.props.children as { props: Record<string, unknown> }
  carousel.props.onKeyDownCapture(event)
  carousel.props.onKeyDownCapture({ key: 'ArrowRight', preventDefault: mock(() => {}) })
  carousel.props.onKeyDownCapture(ignored)

  expect((tree.type as { name?: string }).name).toBe('Provider')
  expect(tree.props.value.orientation).toBe('vertical')
  expect(tree.props.value.opts).toEqual({ loop: true })
  expect(carousel.props.className).toBe('relative gallery')
  expect(setApi).toHaveBeenCalledWith(api)
  expect(on).toHaveBeenCalledWith('reInit', expect.any(Function))
  expect(on).toHaveBeenCalledWith('select', expect.any(Function))
  expect(scrollPrev).toHaveBeenCalledTimes(1)
  expect(scrollNext).toHaveBeenCalledTimes(1)
  expect(event.preventDefault).toHaveBeenCalledTimes(1)
  expect(ignored.preventDefault).not.toHaveBeenCalled()
  cleanups.forEach((cleanup) => cleanup())
  expect(off).toHaveBeenCalledWith('select', expect.any(Function))
})

test('uses carousel context for orientation, controls, and failures', () => {
  context = {
    carouselRef: mock(() => {}),
    api,
    orientation: 'vertical',
    scrollPrev,
    scrollNext,
    canScrollPrev: true,
    canScrollNext: false,
  }
  const content = CarouselContent({ className: 'slides' }) as { props: Record<string, unknown> }
  const item = CarouselItem({ className: 'slide' }) as { props: Record<string, unknown> }
  const previous = CarouselPrevious({ className: 'back' }) as { props: Record<string, unknown> }
  const next = CarouselNext({ className: 'forward' }) as { props: Record<string, unknown> }

  expect(content.props.children.props.className).toContain('-mt-4 flex-col')
  expect(content.props.children.props.className).toContain('slides')
  expect(item.props.className).toContain('pt-4')
  expect(item.props.className).toContain('slide')
  expect(previous.props.disabled).toBe(false)
  expect(previous.props.className).toContain('rotate-90')
  expect(next.props.disabled).toBe(true)
  expect(next.props.className).toContain('rotate-90')
  previous.props.onClick()
  next.props.onClick()
  expect(scrollPrev).toHaveBeenCalledTimes(2)
  expect(scrollNext).toHaveBeenCalledTimes(2)

  context = null
  expect(() => useCarousel()).toThrow('useCarousel must be used within a <Carousel />')
})
