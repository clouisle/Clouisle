import { afterEach, beforeAll, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLButtonElement: window.HTMLButtonElement,
  HTMLAnchorElement: window.HTMLAnchorElement,
  getComputedStyle: window.getComputedStyle,
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: clearTimeout,
})

const dom = { window }
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { seconds?: string }) =>
    key === 'thoughtFor' ? `Thought for ${values?.seconds}` : key,
}))

mock.module('streamdown', () => ({
  Streamdown: ({ children, components }: { children: string; components?: { p?: React.ComponentType<{ children: React.ReactNode }> } }) => {
    const Paragraph = components?.p ?? 'p'
    return <Paragraph>{children}</Paragraph>
  },
}))

let TextContent: typeof import('./text-content').TextContent
let ReasoningContent: typeof import('./reasoning-content').ReasoningContent
let FileContent: typeof import('./file-content').FileContent
let FileListContent: typeof import('./file-content').FileListContent

beforeAll(async () => {
  ;({ TextContent } = await import('./text-content'))
  ;({ ReasoningContent } = await import('./reasoning-content'))
  ;({ FileContent, FileListContent } = await import('./file-content'))
})

const roots: Root[] = []

afterEach(() => {
  for (const root of roots.splice(0)) {
    act(() => root.unmount())
  }
  document.body.replaceChildren()
})

function render(element: React.ReactNode) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

function click(element: Element) {
  act(() => element.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
}

describe('chat message part renderers', () => {
  it('renders normalized citations, invokes their callback, and shows the streaming cursor', () => {
    const onCitationClick = mock(() => {})
    const container = render(
      <TextContent
        part={{ type: 'text', text: 'See [ref:1] and (ref:2).', state: 'streaming' }}
        sources={[
          { type: 'source-document', documentName: 'Guide', content: 'one' },
          { type: 'source-document', documentName: 'FAQ', content: 'two' },
        ]}
        onCitationClick={onCitationClick}
      />
    )

    const badges = container.querySelectorAll('button')
    expect(Array.from(badges, (badge) => badge.textContent)).toEqual(['1', '2'])
    expect(badges[0].getAttribute('title')).toBe('Guide')
    expect(container.querySelector('.animate-blink')).not.toBeNull()

    click(badges[1])
    expect(onCitationClick).toHaveBeenCalledWith(2)
  })

  it('shows streaming reasoning, then lets completed reasoning collapse after displaying duration', () => {
    const container = render(
      <ReasoningContent
        part={{ type: 'reasoning', text: 'Checking sources', state: 'streaming' }}
      />
    )

    expect(container.textContent).toContain('thinking')
    expect(container.textContent).toContain('Checking sources')
    expect(container.querySelector('.animate-spin')).not.toBeNull()

    const completed = render(
      <ReasoningContent
        part={{ type: 'reasoning', text: 'Finished', state: 'done', duration: 65000 }}
        defaultOpen
      />
    )
    const trigger = completed.querySelector('button')!
    expect(completed.textContent).toContain('Thought for 1m 5s')
    expect(completed.textContent).toContain('Finished')

    click(trigger)
    expect(completed.textContent).not.toContain('Finished')
  })

  it('displays file details and download action, while image previews and image-list overlays collapse', () => {
    const container = render(
      <FileContent
        file={{
          type: 'file',
          filename: 'report.json',
          mimeType: 'application/json',
          size: 1536,
          url: 'https://example.com/report.json',
        }}
      />
    )

    expect(container.textContent).toContain('report.json')
    expect(container.textContent).toContain('1.5 KB')
    expect(container.textContent).toContain('application/json')
    const download = container.querySelector('a')!
    expect(download.getAttribute('href')).toBe('https://example.com/report.json')
    expect(download.getAttribute('download')).toBe('report.json')

    const image = render(
      <FileContent file={{ type: 'file', filename: 'photo.png', mimeType: 'image/png', url: 'https://example.com/photo.png' }} />
    )
    const imageTrigger = image.querySelector('button')!
    expect(image.querySelectorAll('img')).toHaveLength(1)
    click(imageTrigger)
    expect(image.querySelectorAll('img')).toHaveLength(2)

    const list = render(
      <FileListContent files={[
        { type: 'file', filename: 'grid.png', mimeType: 'image/png', url: 'https://example.com/grid.png' },
        { type: 'file', filename: 'notes.txt', mimeType: 'text/plain' },
      ]} />
    )
    expect(list.textContent).toContain('notes.txt')
    click(list.querySelector('button')!)
    expect(list.textContent).toContain('grid.png')
  })
})
