import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create } from 'react-test-renderer'

function primitive(name: string) {
  function Primitive({ children, render, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    if (React.isValidElement(render)) return React.cloneElement(render, props, children)
    return React.createElement(name, props, children)
  }

  Primitive.displayName = name
  return Primitive
}

mock.module('@base-ui/react/select', () => ({
  Select: {
    Root: primitive('select-root'),
    Group: primitive('select-group'),
    Value: primitive('select-value'),
    Trigger: primitive('select-trigger'),
    Icon: primitive('select-icon'),
    Portal: primitive('select-portal'),
    Positioner: primitive('select-positioner'),
    Popup: primitive('select-popup'),
    List: primitive('select-list'),
    GroupLabel: primitive('select-label'),
    Item: primitive('select-item'),
    ItemText: primitive('select-item-text'),
    ItemIndicator: primitive('select-item-indicator'),
    Separator: primitive('select-separator'),
    ScrollUpArrow: primitive('select-scroll-up'),
    ScrollDownArrow: primitive('select-scroll-down'),
  },
}))

const {
  Select,
  SelectContent,
  SelectEmpty,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} = await import('./select')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('Select primitive wrappers', () => {
  test('renders every wrapper and forwards variants and classes', () => {
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <Select value="one">
          <SelectTrigger size="xs" className="custom-trigger">
            <SelectValue className="custom-value">One</SelectValue>
          </SelectTrigger>
          <SelectContent className="custom-content">
            <SelectGroup className="custom-group">
              <SelectLabel className="custom-label">Numbers</SelectLabel>
              <SelectItem value="one" className="custom-item">One</SelectItem>
              <SelectSeparator className="custom-separator" />
              <SelectEmpty className="custom-empty">Empty</SelectEmpty>
            </SelectGroup>
          </SelectContent>
        </Select>,
      )
    })

    expect(renderer.root.findByType('select-root').props.value).toBe('one')
    expect(renderer.root.findByType('select-trigger').props['data-size']).toBe('xs')
    expect(renderer.root.findByType('select-trigger').props.className).toContain('custom-trigger')
    expect(renderer.root.findByType('select-value').props.className).toContain('custom-value')
    expect(renderer.root.findByType('select-positioner').props).toMatchObject({
      side: 'bottom', sideOffset: 4, align: 'center', alignOffset: 0, alignItemWithTrigger: false,
    })
    expect(renderer.root.findByType('select-popup').props.className).toContain('custom-content')
    expect(renderer.root.findByType('select-group').props.className).toContain('custom-group')
    expect(renderer.root.findByType('select-label').props.className).toContain('custom-label')
    expect(renderer.root.findByType('select-item').props.className).toContain('custom-item')
    expect(renderer.root.findByType('select-item-text').children).toEqual(['One'])
    expect(renderer.root.findByType('select-separator').props.className).toContain('custom-separator')
    expect(renderer.root.findByProps({ 'data-slot': 'select-empty' }).props.className).toContain('custom-empty')
    expect(renderer.root.findAllByType('select-scroll-up')).toHaveLength(1)
    expect(renderer.root.findAllByType('select-scroll-down')).toHaveLength(1)
  })

  test('forwards custom scroll button classes', () => {
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <>
          <SelectScrollUpButton className="custom-up" />
          <SelectScrollDownButton className="custom-down" />
        </>,
      )
    })

    expect(renderer.root.findByType('select-scroll-up').props.className).toContain('custom-up')
    expect(renderer.root.findByType('select-scroll-down').props.className).toContain('custom-down')
  })
})
