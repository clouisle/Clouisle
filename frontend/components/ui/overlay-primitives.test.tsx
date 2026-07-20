import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create } from 'react-test-renderer'

function primitive(name: string) {
  function Primitive({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(name, props, children)
  }

  Primitive.displayName = name
  return Primitive
}

mock.module('@base-ui/react/popover', () => ({
  Popover: {
    Root: primitive('popover-root'),
    Trigger: primitive('popover-trigger'),
    Portal: primitive('popover-portal'),
    Positioner: primitive('popover-positioner'),
    Popup: primitive('popover-popup'),
    Arrow: primitive('popover-arrow'),
    Close: primitive('popover-close'),
  },
}))

mock.module('@base-ui/react/dialog', () => ({
  Dialog: {
    Root: primitive('sheet-root'),
    Trigger: primitive('sheet-trigger'),
    Close: primitive('sheet-close'),
    Portal: primitive('sheet-portal'),
    Backdrop: primitive('sheet-backdrop'),
    Popup: primitive('sheet-popup'),
    Title: primitive('sheet-title'),
    Description: primitive('sheet-description'),
  },
}))

const { Popover, PopoverContent, PopoverTrigger } = await import('./popover')
const { Sheet, SheetContent, SheetTrigger } = await import('./sheet')

describe('overlay UI primitives', () => {
  test('forwards popover trigger events and default positioning', () => {
    const onClick = mock()
    let renderer: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <Popover>
          <PopoverTrigger className="extra-trigger" onClick={onClick}>Open</PopoverTrigger>
          <PopoverContent>Details</PopoverContent>
        </Popover>
      )
    })

    const trigger = renderer!.root.findByType('popover-trigger')
    expect(trigger.props.className).toContain('cursor-pointer')
    expect(trigger.props.className).toContain('extra-trigger')
    act(() => trigger.props.onClick())
    expect(onClick).toHaveBeenCalledTimes(1)

    const positioner = renderer!.root.findByType('popover-positioner')
    expect(positioner.props).toMatchObject({ align: 'center', side: 'bottom', sideOffset: 4 })
    expect(renderer!.root.findByType('popover-popup').children).toEqual(['Details'])
  })

  test('uses the requested sheet side and can omit its built-in close control', () => {
    let renderer: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <Sheet>
          <SheetTrigger className="open-sheet">Open</SheetTrigger>
          <SheetContent side="left" showCloseButton={false}>Panel</SheetContent>
        </Sheet>
      )
    })

    const trigger = renderer!.root.findByType('sheet-trigger')
    expect(trigger.props.className).toContain('cursor-pointer')
    expect(trigger.props.className).toContain('open-sheet')

    const content = renderer!.root.findByType('sheet-popup')
    expect(content.props['data-side']).toBe('left')
    expect(content.children).toEqual(['Panel'])
    expect(renderer!.root.findAllByType('sheet-close')).toHaveLength(0)
  })
})
