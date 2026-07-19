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
let VideoLightbox: typeof import('./image-lightbox').VideoLightbox
let useLightbox: typeof import('./image-lightbox').useLightbox

beforeAll(async () => {
  ;({ ImageLightbox, VideoLightbox, useLightbox } = await import('./image-lightbox'))
})

const roots: Root[] = []

function render(element: React.ReactNode) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

function renderImage(props: React.ComponentProps<typeof ImageLightbox>) {
  return render(<ImageLightbox {...props} />)
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
    const container = renderImage({ src: '/image.png', isOpen: false, onClose: mock(() => {}) })

    expect(container.textContent).toBe('')
    expect(document.body.style.overflow).toBe('')
  })

  test('locks scrolling and handles keyboard zoom, rotation, and closing', () => {
    const onClose = mock(() => {})
    renderImage({ src: '/image.png', isOpen: true, onClose })

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
    renderImage({ src: '/image.png', alt: 'Prompt', isOpen: true, onClose })

    const image = document.body.querySelector('img')!
    act(() => image.parentElement!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(document.body.textContent).toContain('125%')
    expect(onClose).not.toHaveBeenCalled()

    const backdrop = document.body.querySelector('.fixed')!
    act(() => backdrop.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('keeps video controls open while closing through Escape, close, or backdrop', () => {
    const onClose = mock(() => {})
    render(<VideoLightbox src="/video.mp4" isOpen onClose={onClose} />)

    expect(document.body.style.overflow).toBe('hidden')
    expect(document.body.querySelector('video')?.getAttribute('src')).toBe('/video.mp4')

    act(() => document.body.querySelector('video')!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(onClose).not.toHaveBeenCalled()

    keydown('Escape')
    act(() => document.body.querySelector('button:last-child')!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    act(() => document.body.querySelector('.fixed')!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })))
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  test('exposes an open and close state controller', () => {
    function Harness() {
      const state = useLightbox()
      return (
        <>
          <button onClick={() => state.openLightbox('/image.png', 'Prompt')}>open</button>
          <button onClick={state.closeLightbox}>close</button>
          <output>{JSON.stringify([state.isOpen, state.imageSrc, state.imageAlt])}</output>
        </>
      )
    }

    const container = render(<Harness />)
    act(() => container.querySelector('button')!.click())
    expect(container.querySelector('output')?.textContent).toBe('[true,"/image.png","Prompt"]')

    act(() => container.querySelectorAll('button')[1].click())
    expect(container.querySelector('output')?.textContent).toBe('[false,"/image.png","Prompt"]')
  })
})
