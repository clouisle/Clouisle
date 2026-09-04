import { describe, expect, test } from 'bun:test'
import type { ReactNode } from 'react'

import { create } from './rtl-renderer'

type VirtualType = string | ((props: Record<string, unknown>) => unknown)

function element(type: VirtualType, props?: Record<string, unknown>): ReactNode {
  return { type, props } as unknown as ReactNode
}

describe('virtual renderer compatibility', () => {
  test('renders virtual elements and supports instance queries', () => {
    const Leaf = (props: Record<string, unknown>) => ({
      type: 'leaf',
      props: {
        'data-value': props.value,
        children: [
          null,
          undefined,
          false,
          'text',
          42,
          { type: 'span', props: { children: 'nested' } },
          { type: 'ignored', $$typeof: Symbol.for('react.element') },
          { notAnElement: true },
        ],
      },
    })

    const renderer = create(element(Leaf, { value: 'virtual' }))
    const root = renderer.root
    const leaf = root.findByType('leaf')
    const nested = leaf.findByType('span')

    expect(root.type).toBe(Leaf)
    expect(root.props).toEqual({ value: 'virtual' })
    expect(leaf.children).toHaveLength(3)
    expect(leaf.children[0]).toBe('text')
    expect(leaf.children[1]).toBe('42')
    expect(nested.children).toEqual(['nested'])
    expect(root.find((node) => node.type === 'span')).toBe(nested)
    expect(root.findAll((node) => typeof node.type === 'string')).toHaveLength(2)
    expect(root.findByProps({ 'data-value': 'virtual' })).toBe(leaf)
    expect(root.findAllByProps({})).toHaveLength(3)
    expect(root.findAllByType('missing')).toEqual([])
    expect(renderer.toJSON()).toEqual({
      type: 'leaf',
      props: { 'data-value': 'virtual' },
      children: [
        'text',
        '42',
        { type: 'span', props: {}, children: ['nested'] },
      ],
    })

    expect(() => root.findByType('missing')).toThrow('No matching test instance found')
    expect(() => root.findByProps({ missing: true })).toThrow('No matching test instance found')
  })

  test('handles functional roots, updates, and unmounts', () => {
    const Empty = () => null
    expect(create(element(Empty)).toJSON()).toBeNull()

    const Multiple = () => [
      element('strong'),
      element('em', { children: 'emphasis' }),
    ]
    const renderer = create(element(Multiple))
    expect(renderer.toJSON()).toEqual([
      { type: 'strong', props: {}, children: null },
      { type: 'em', props: {}, children: ['emphasis'] },
    ])

    renderer.update(element('p', { children: 'updated' }))
    expect(renderer.root.type).toBe('p')
    expect(renderer.toJSON()).toEqual({ type: 'p', props: {}, children: ['updated'] })

    renderer.unmount()
    expect(renderer.root.type).toBe('root')
    expect(renderer.root.children).toEqual([])
    expect(renderer.toJSON()).toEqual({ type: 'root', props: {}, children: null })
  })
})
