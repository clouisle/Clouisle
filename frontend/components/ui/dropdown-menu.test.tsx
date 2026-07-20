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

mock.module('@base-ui/react/menu', () => ({
  Menu: {
    Root: primitive('menu-root'),
    Portal: primitive('menu-portal'),
    Trigger: primitive('menu-trigger'),
    Positioner: primitive('menu-positioner'),
    Popup: primitive('menu-popup'),
    Group: primitive('menu-group'),
    GroupLabel: primitive('menu-label'),
    Item: primitive('menu-item'),
    SubmenuRoot: primitive('menu-sub-root'),
    SubmenuTrigger: primitive('menu-sub-trigger'),
    CheckboxItem: primitive('menu-checkbox-item'),
    CheckboxItemIndicator: primitive('menu-checkbox-indicator'),
    RadioGroup: primitive('menu-radio-group'),
    RadioItem: primitive('menu-radio-item'),
    RadioItemIndicator: primitive('menu-radio-indicator'),
    Separator: primitive('menu-separator'),
  },
}))

const {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} = await import('./dropdown-menu')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('DropdownMenu', () => {
  test('forwards root, portal, trigger, and positioned content props', () => {
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger className="custom-trigger">Open</DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent align="end" alignOffset={2} side="top" sideOffset={6} className="custom-content">
              Body
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenu>,
      )
    })

    expect(renderer.root.findByType('menu-root').props.modal).toBe(false)
    expect(renderer.root.findByType('menu-trigger').props.className).toContain('custom-trigger')
    const positioner = renderer.root.findByType('menu-positioner')
    expect(positioner.props).toMatchObject({ align: 'end', alignOffset: 2, side: 'top', sideOffset: 6 })
    expect(renderer.root.findByType('menu-popup').props.className).toContain('custom-content')
  })

  test('renders grouped item variants, checks, radio items, shortcuts, and submenus', () => {
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <DropdownMenu>
          <DropdownMenuContent>
            <DropdownMenuGroup>
              <DropdownMenuLabel inset className="custom-label">Main</DropdownMenuLabel>
              <DropdownMenuItem inset variant="destructive" className="custom-item">
                Delete
                <DropdownMenuShortcut className="custom-shortcut">⌘D</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuCheckboxItem checked className="custom-checkbox">Enabled</DropdownMenuCheckboxItem>
              <DropdownMenuRadioGroup value="one">
                <DropdownMenuRadioItem value="one" className="custom-radio">One</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator className="custom-separator" />
              <DropdownMenuSub>
                <DropdownMenuSubTrigger inset className="custom-sub-trigger">More</DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="custom-sub-content">Nested</DropdownMenuSubContent>
              </DropdownMenuSub>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>,
      )
    })

    const label = renderer.root.findByType('menu-label')
    expect(label.props['data-inset']).toBe(true)
    expect(label.props.className).toContain('custom-label')

    const item = renderer.root.findByType('menu-item')
    expect(item.props['data-variant']).toBe('destructive')
    expect(item.props.className).toContain('custom-item')
    expect(renderer.root.findByProps({ 'data-slot': 'dropdown-menu-shortcut' }).props.className).toContain('custom-shortcut')

    expect(renderer.root.findByType('menu-checkbox-item').props.checked).toBe(true)
    expect(renderer.root.findByType('menu-radio-group').props.value).toBe('one')
    expect(renderer.root.findByType('menu-radio-item').props.className).toContain('custom-radio')
    expect(renderer.root.findByType('menu-separator').props.className).toContain('custom-separator')
    expect(renderer.root.findByType('menu-sub-trigger').props.className).toContain('custom-sub-trigger')
    expect(renderer.root.findAllByType('menu-popup').at(-1)?.props.className).toContain('custom-sub-content')
  })
})
