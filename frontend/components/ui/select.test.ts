import { afterEach, describe, expect, test } from 'bun:test'
import { Window } from 'happy-dom'
import { Select as SelectPrimitive } from '@base-ui/react/select'
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'

import {
  Select,
  SelectContent,
  SelectEmpty,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from './select'

const window = new Window()
Object.assign(globalThis, {
  window,
  document: window.document,
  Element: window.Element,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
  navigator: window.navigator,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const e = createElement
const roots: Root[] = []

afterEach(async () => {
  await act(async () => {
    roots.splice(0).forEach((root) => root.unmount())
  })
  document.body.replaceChildren()
})

async function renderSelect(children: React.ReactNode) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)

  await act(async () => {
    root.render(children)
  })
}

describe('Select', () => {
  test('shows the selected item and forwards trigger props', async () => {
    await renderSelect(
      e(Select, { defaultValue: 'banana' },
        e(SelectTrigger, { 'aria-label': 'Fruit', size: 'sm', className: 'custom-trigger' },
          e(SelectValue, { placeholder: 'Choose fruit' })
        ),
        e(SelectContent, null,
          e(SelectItem, { value: 'apple' }, 'Apple'),
          e(SelectItem, { value: 'banana' }, 'Banana')
        )
      )
    )

    const trigger = document.querySelector('[data-slot="select-trigger"]')
    expect(trigger?.textContent).toContain('banana')
    expect(trigger?.getAttribute('aria-label')).toBe('Fruit')
    expect(trigger?.getAttribute('data-size')).toBe('sm')
    expect(trigger?.className).toContain('custom-trigger')
  })

  test('reflects open state and renders configured content props', async () => {
    await renderSelect(
      e(Select, { defaultOpen: true },
        e(SelectTrigger, { 'aria-label': 'Fruit' }, e(SelectValue, { placeholder: 'Choose fruit' })),
        e(SelectContent, { align: 'end', alignOffset: 6, side: 'top', sideOffset: 8, className: 'custom-content' },
          e(SelectGroup, null,
            e(SelectLabel, null, 'Fruit'),
            e(SelectItem, { value: 'apple' }, 'Apple')
          ),
          e(SelectSeparator),
          e(SelectEmpty, null, 'No fruit found')
        )
      )
    )

    const trigger = document.querySelector('[data-slot="select-trigger"]')
    expect(trigger?.getAttribute('aria-expanded')).toBe('true')
    expect(trigger?.getAttribute('data-popup-open')).toBe('')
  })

  test('builds content with groups and forwarded positioning props', () => {
    const content = SelectContent({
      align: 'end',
      alignOffset: 6,
      side: 'top',
      sideOffset: 8,
      className: 'custom-content',
      children: e(SelectGroup, null,
        e(SelectLabel, null, 'Fruit'),
        e(SelectItem, { value: 'apple' }, 'Apple')
      ),
    }) as React.ReactElement

    expect(content.type).toBe(SelectPrimitive.Portal)
    const positioner = content.props.children as React.ReactElement
    expect(positioner.props).toMatchObject({
      align: 'end',
      alignOffset: 6,
      side: 'top',
      sideOffset: 8,
    })
    const popup = positioner.props.children as React.ReactElement
    expect(popup.props.className).toContain('custom-content')
    const list = popup.props.children[1] as React.ReactElement
    const groupChildren = list.props.children.props.children as React.ReactElement[]
    expect(groupChildren[0].props.children).toBe('Fruit')
    expect(groupChildren[1].props.children).toBe('Apple')
  })
})
