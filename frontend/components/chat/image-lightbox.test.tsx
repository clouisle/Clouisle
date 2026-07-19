import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
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
  getComputedStyle: window.getComputedStyle,
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: clearTimeout,
})

const dom = { window }
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))

let ImageLightbox: typeof import('./image-lightbox').ImageLightbox

beforeAll(async () => {
  ;({ ImageLightbox } = await import('./image-lightbox'))
})

const roots: Root[] = []

function render(props: React.ComponentProps<typeof ImageLightbox>) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(<ImageLightbox {...props} />))
  return container
}

function keydown(key: string) {
  act(() => window.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key })))
}

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  document.body.style.overflow = ''
})

describe('ImageLightbox', () => {
  test('keeps closed lightboxes out of the portal and restores scrolling', () => {
    const container = render({ src: '/image.png', isOpen: false, onClose: mock(() => {}) })

    expect(container.textContent).toBe('')
    expect(document.body.style.overflow).toBe('')
  })

  test('locks scrolling and handles keyboard zoom, rotation, and closing', () => {
    const onClose = mock(() => {})
    render({ src: '/image.png', isOpen: true, onClose })

    expect(document.body.style.overflow).toBe('hidden')
    expect(document.body.querySelector('img')?.getAttribute('src')).toBe('/image.png')

    for (let index = 0; index < 20; index++) keydown('=')
    expect(document.body.textContent).toContain('400%')
    for (let index = 0; index < 20; index++) keydown('-')
    expect(document.body.textContent).toContain('50%')

    keydown('r')
    expect(document.body.querySelector('img')?.getAttribute('style')).toContain('rotate(90deg)')

    keydown('Escape')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('zooms on image clicks but closes only when the backdrop is clicked', () => {
    const onClose = mock(() => {})
    render({ src: '/image.png', alt: 'Prompt', isOpen: true, onClose })

    const image = document.body.querySelector('img')!
    act(() => image.parentElement!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(document.body.textContent).toContain('125%')
    expect(onClose).not.toHaveBeenCalled()

    const backdrop = document.body.querySelector('.fixed')!
    act(() => backdrop.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
