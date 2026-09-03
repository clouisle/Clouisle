import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create } from '@/test-utils/rtl-renderer'

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

const {
  Popover,
  PopoverArrow,
  PopoverClose,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} = await import('./popover')
const {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} = await import('./sheet')

describe('overlay UI primitives', () => {
  test('forwards popover trigger events and default positioning', () => {
    const onClick = mock()
    let renderer: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <Popover>
          <PopoverTrigger className="extra-trigger" onClick={onClick}>Open</PopoverTrigger>
          <PopoverPortal>
            <PopoverContent className="extra-content">
              Details
              <PopoverArrow className="extra-arrow" />
              <PopoverClose>Dismiss</PopoverClose>
            </PopoverContent>
          </PopoverPortal>
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
    expect(renderer!.root.findByType('popover-popup').props.className).toContain('extra-content')
    expect(renderer!.root.findByType('popover-arrow').props.className).toContain('extra-arrow')
    expect(renderer!.root.findByType('popover-close').children).toEqual(['Dismiss'])
    expect(renderer!.root.findAllByType('popover-portal')).toHaveLength(2)
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

  test('renders default sheet close control and structural sections', () => {
    let renderer: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <Sheet>
          <SheetContent className="custom-content">
            <SheetHeader className="custom-header">
              <SheetTitle className="custom-title">Title</SheetTitle>
              <SheetDescription className="custom-description">Description</SheetDescription>
            </SheetHeader>
            <SheetFooter className="custom-footer">
              <SheetClose>Dismiss</SheetClose>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      )
    })

    const content = renderer!.root.findByType('sheet-popup')
    expect(content.props['data-side']).toBe('right')
    expect(content.props.className).toContain('custom-content')
    expect(renderer!.root.findByType('sheet-backdrop').props['data-slot']).toBe('sheet-overlay')
    expect(renderer!.root.findByType('sheet-title').props.className).toContain('custom-title')
    expect(renderer!.root.findByType('sheet-description').props.className).toContain('custom-description')
    expect(renderer!.root.findByProps({ 'data-slot': 'sheet-header' }).props.className).toContain('custom-header')
    expect(renderer!.root.findByProps({ 'data-slot': 'sheet-footer' }).props.className).toContain('custom-footer')
    expect(renderer!.root.findAllByType('sheet-close')).toHaveLength(2)
  })
})
