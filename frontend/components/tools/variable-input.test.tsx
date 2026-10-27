import { afterEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { VariableInput } from './variable-input'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(
  props: Partial<React.ComponentProps<typeof VariableInput>> = {}
): ReactTestRenderer {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(
      <VariableInput value="" onChange={mock(() => {})} variables={[]} {...props} />
    )
  })
  renderers.push(renderer)
  return renderer
}

/**
 * Drive the native input the way the DOM does: currentTarget/target are the
 * element, while Base UI's Field.Control wrapper reads currentTarget.value.
 */
function typeInto(
  renderer: ReactTestRenderer,
  value: string,
  cursor = value.length
) {
  const element = document.querySelector('input')!
  const browserWindow = globalThis.window as Window & typeof globalThis
  const input = renderer.root.findByType('input')

  element.value = value
  element.setSelectionRange(cursor, cursor)

  act(() => {
    input.props.onChange({
      currentTarget: element,
      target: element,
      nativeEvent: new browserWindow.Event('input'),
      preventDefault: () => {},
    })
  })
}

function optionLabels(): string[] {
  return Array.from(document.querySelectorAll('[role="option"]')).map(
    (option) => option.textContent ?? ''
  )
}

describe('VariableInput', () => {
  test('filters parameter and connection field names after {{', () => {
    const renderer = render({
      value: 'https://api.example.com/{{con',
      variables: ['id', 'connection_key', 'consumer', ''],
    })

    typeInto(renderer, 'https://api.example.com/{{con')

    expect(optionLabels()).toEqual(['{{connection_key}}', '{{consumer}}'])
  })

  test('inserts a connection field reference into the configured field', () => {
    const onChange = mock(() => {})
    const renderer = render({
      value: '{{api_',
      onChange,
      variables: ['api_base', 'id'],
    })

    typeInto(renderer, '{{api_')

    const option = Array.from(
      document.querySelectorAll<HTMLElement>('[role="option"]')
    ).find((item) => item.textContent === '{{api_base}}')
    expect(option).toBeDefined()

    const browserWindow = globalThis.window as Window & typeof globalThis
    act(() => {
      option!.dispatchEvent(
        new browserWindow.MouseEvent('mousedown', {
          bubbles: true,
          cancelable: true,
        })
      )
    })

    expect(onChange).toHaveBeenCalledWith('{{api_base}}')
  })

  test('does not suggest inside a completed reference', () => {
    const renderer = render({ value: '{{id}}', variables: ['id', 'name'] })

    typeInto(renderer, '{{id}}', 6)

    expect(optionLabels()).toEqual([])
  })

  test('supports multiline body templates', () => {
    const renderer = render({ multiline: true, value: '', variables: ['id'] })

    expect(renderer.root.findAllByType('textarea')).toHaveLength(1)
    expect(renderer.root.findAllByType('input')).toHaveLength(0)
  })
})
