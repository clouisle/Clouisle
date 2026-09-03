import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import React, { createContext, useContext } from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const CollapsibleContext = createContext<{ open: boolean; toggle: () => void }>({
  open: false,
  toggle: () => {},
})

mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, open = false, onOpenChange, ...props }: React.ComponentProps<'div'> & {
    open?: boolean
    onOpenChange?: (open: boolean) => void
  }) => (
    <CollapsibleContext.Provider value={{ open, toggle: () => onOpenChange?.(!open) }}>
      <div data-state={open ? 'open' : 'closed'} {...props}>{children}</div>
    </CollapsibleContext.Provider>
  ),
  CollapsibleTrigger: ({ children, ...props }: React.ComponentProps<'button'>) => {
    const { open, toggle } = useContext(CollapsibleContext)
    return <button aria-expanded={open} onClick={toggle} {...props}>{children}</button>
  },
  CollapsibleContent: ({ children, ...props }: React.ComponentProps<'div'>) => {
    const { open } = useContext(CollapsibleContext)
    return open ? <div {...props}>{children}</div> : null
  },
}))

mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.ComponentProps<'span'> & { variant?: string }) => {
    delete props.variant
    return <span {...props}>{children}</span>
  },
}))

mock.module('@/components/ui/hover-card', () => ({
  HoverCard: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  HoverCardContent: (props: React.ComponentProps<'div'>) => <div {...props} />,
  HoverCardTrigger: ({ children, render }: { children?: React.ReactNode; render: React.ReactElement }) =>
    React.cloneElement(render, {}, children),
}))

mock.module('@/components/ui/carousel', () => ({
  Carousel: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CarouselContent: (props: React.ComponentProps<'div'>) => <div {...props} />,
  CarouselItem: (props: React.ComponentProps<'div'>) => <div {...props} />,
}))

let Task: typeof import('./task').Task
let TaskContent: typeof import('./task').TaskContent
let TaskList: typeof import('./task').TaskList
let TaskTrigger: typeof import('./task').TaskTrigger
let InlineCitation: typeof import('./inline-citation').InlineCitation
let InlineCitationCardTrigger: typeof import('./inline-citation').InlineCitationCardTrigger
let InlineCitationCarouselNext: typeof import('./inline-citation').InlineCitationCarouselNext
let InlineCitationCarouselPrev: typeof import('./inline-citation').InlineCitationCarouselPrev
let InlineCitationQuote: typeof import('./inline-citation').InlineCitationQuote
let InlineCitationSource: typeof import('./inline-citation').InlineCitationSource
let InlineCitationText: typeof import('./inline-citation').InlineCitationText

beforeAll(async () => {
  ({ Task, TaskContent, TaskList, TaskTrigger } = await import('./task'))
  ;({
    InlineCitation,
    InlineCitationCardTrigger,
    InlineCitationCarouselNext,
    InlineCitationCarouselPrev,
    InlineCitationQuote,
    InlineCitationSource,
    InlineCitationText,
  } = await import('./inline-citation'))
})

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

function render(element: React.ReactNode) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  renderers.push(renderer!)
  return renderer!
}

const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
})

describe('task AI element', () => {
  test('renders a non-interactive summary when no details exist', () => {
    const renderer = render(
      <Task state="pending"><TaskTrigger title="Waiting" description="Queued" /></Task>,
    )

    expect(renderer.root.findAllByType('button')).toHaveLength(0)
    expect(text(renderer)).toContain('Waiting')
    expect(text(renderer)).toContain('Queued')
    expect(text(renderer)).not.toContain('rotate-')
  })

  test('opens details from its accessible trigger and reflects state variants', () => {
    const renderer = render(
      <TaskList aria-label="Agent tasks">
        <Task state="running">
          <TaskTrigger title="Search" description="In progress" />
          <TaskContent>Searching the handbook</TaskContent>
        </Task>
      </TaskList>,
    )
    const trigger = renderer.root.findByType('button')

    expect(trigger.props['aria-expanded']).toBe(false)
    expect(text(renderer)).toContain('animate-spin')
    expect(text(renderer)).not.toContain('Searching the handbook')

    act(() => trigger.props.onClick())

    expect(renderer.root.findByType('button').props['aria-expanded']).toBe(true)
    expect(text(renderer)).toContain('Searching the handbook')
    expect(text(renderer)).toContain('rotate-180')

    for (const state of ['completed', 'error'] as const) {
      const variant = render(<Task state={state}><TaskTrigger title={state} /></Task>)
      expect(text(variant)).toContain(state === 'completed' ? 'text-green-600' : 'text-destructive')
    }
  })
})

describe('inline citation AI element', () => {
  test('shows source identity, counts additional sources, and handles an empty source list', () => {
    const citation = render(
      <InlineCitation>
        <InlineCitationText>Supported claim</InlineCitationText>
        <InlineCitationCardTrigger sources={['https://docs.example.com/guide', 'https://status.example.com']} />
      </InlineCitation>,
    )
    const unknown = render(<InlineCitationCardTrigger sources={[]} />)

    expect(text(citation)).toContain('Supported claim')
    expect(text(citation)).toContain('docs.example.com')
    expect(text(citation)).toContain('+1')
    expect(text(unknown)).toContain('unknown')
  })

  test('renders optional source fields, quoted evidence, and labeled navigation controls', () => {
    const renderer = render(
      <InlineCitationSource title="Deployment guide" url="https://example.com/deploy" description="Production checklist">
        <InlineCitationQuote>Verify before rollout.</InlineCitationQuote>
      </InlineCitationSource>,
    )
    const empty = render(<InlineCitationSource data-testid="empty" />)
    const navigation = render(<><InlineCitationCarouselPrev /><InlineCitationCarouselNext /></>)

    expect(text(renderer)).toContain('Deployment guide')
    expect(text(renderer)).toContain('https://example.com/deploy')
    expect(text(renderer)).toContain('Production checklist')
    expect(renderer.root.findByType('blockquote').children).toEqual(['Verify before rollout.'])
    expect(empty.root.findByProps({ 'data-testid': 'empty' }).findAllByType('p')).toHaveLength(0)
    expect(navigation.root.findAllByType('button').map(button => button.props['aria-label'])).toEqual([
      'Previous',
      'Next',
    ])
  })
})
