import { describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create } from 'react-test-renderer'

function primitive(name: string) {
  function Primitive({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(name, props, children)
  }

  Primitive.displayName = name
  return Primitive
}

mock.module('@base-ui/react/dialog', () => ({
  Dialog: {
    Root: primitive('dialog-root'),
    Trigger: primitive('dialog-trigger'),
    Portal: primitive('dialog-portal'),
    Close({ render, children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
      if (React.isValidElement(render)) {
        return React.cloneElement(render, props, children)
      }

      return React.createElement('dialog-close', props, children)
    },
    Backdrop: primitive('dialog-backdrop'),
    Popup: primitive('dialog-popup'),
    Title: primitive('dialog-title'),
    Description: primitive('dialog-description'),
  },
}))

const {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
} = await import('./dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.requestAnimationFrame = (callback: FrameRequestCallback) => setTimeout(callback, 0)
globalThis.cancelAnimationFrame = (id: number) => clearTimeout(id)
Object.assign(globalThis, { window: globalThis })

describe('Dialog', () => {
  test('renders an accessible trigger and labelled content slots', () => {
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(
        <Dialog>
          <DialogTrigger aria-label="Open settings">Open settings</DialogTrigger>
          <DialogPortal>
            <DialogOverlay className="custom-overlay" />
            <DialogContent className="custom-content" overlayClassName="nested-overlay">
              <DialogHeader className="custom-header">
                <DialogTitle className="custom-title">Settings</DialogTitle>
                <DialogDescription className="custom-description">Manage application preferences.</DialogDescription>
              </DialogHeader>
              <DialogFooter className="custom-footer" showCloseButton>
                <DialogClose>Cancel</DialogClose>
              </DialogFooter>
            </DialogContent>
          </DialogPortal>
        </Dialog>,
      )
    })

    const trigger = renderer.root.findByProps({ 'data-slot': 'dialog-trigger' })
    expect(trigger.props['aria-label']).toBe('Open settings')
    expect(trigger.props.className).toContain('cursor-pointer')
    expect(renderer.root.findAllByType('dialog-portal')).toHaveLength(2)
    expect(renderer.root.findAllByProps({ 'data-slot': 'dialog-overlay' }).some((node) => node.props.className.includes('custom-overlay'))).toBe(true)
    expect(renderer.root.findAllByProps({ 'data-slot': 'dialog-overlay' }).some((node) => node.props.className.includes('nested-overlay'))).toBe(true)
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-content' }).props.className).toContain('custom-content')
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-header' }).props.className).toContain('custom-header')
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-title' }).props.className).toContain('custom-title')
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-description' }).props.className).toContain('custom-description')
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-footer' }).props.className).toContain('custom-footer')
    expect(renderer.root.findAllByProps({ 'data-slot': 'dialog-close' }).length).toBeGreaterThan(0)
    expect(renderer.root.findByType('dialog-title').children).toEqual(['Settings'])
    expect(renderer.root.findByType('dialog-description').children).toEqual(['Manage application preferences.'])

    act(() => renderer.unmount())
  })

  test('can hide overlay and built-in close button', () => {
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(
        <DialogContent hideOverlay showCloseButton={false}>
          Plain content
        </DialogContent>,
      )
    })

    expect(renderer.root.findAllByProps({ 'data-slot': 'dialog-overlay' })).toHaveLength(0)
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-content' }).props.children).toEqual(['Plain content', false])
    expect(renderer.root.findAllByProps({ 'data-slot': 'dialog-close' })).toHaveLength(0)

    act(() => renderer.unmount())
  })
})
