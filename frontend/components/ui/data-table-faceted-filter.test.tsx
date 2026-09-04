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

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('lucide-react', () => ({
  PlusCircle: primitive('plus-circle'),
  Check: primitive('check-icon'),
  Search: primitive('search-icon'),
}))

mock.module('@/components/ui/badge', () => ({ Badge: primitive('badge') }))
mock.module('@/components/ui/input', () => ({ Input: primitive('input') }))
mock.module('@/components/ui/separator', () => ({ Separator: primitive('separator') }))
mock.module('@/components/ui/popover', () => ({
  Popover: primitive('popover'),
  PopoverContent: primitive('popover-content'),
  PopoverTrigger: primitive('popover-trigger'),
}))

const { DataTableFacetedFilter } = await import('./data-table-faceted-filter')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('DataTableFacetedFilter', () => {
  test('renders selected badges and toggles options', () => {
    const onSelectionChange = mock(() => {})
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <DataTableFacetedFilter
          title="Status"
          options={[
            { value: 'active', label: 'Active', count: 2, icon: <span>icon</span> },
            { value: 'paused', label: 'Paused' },
            { value: 'archived', label: 'Archived' },
          ]}
          selectedValues={new Set(['active', 'paused'])}
          onSelectionChange={onSelectionChange}
        />,
      )
    })

    expect(renderer.root.findByType('popover').props.open).toBe(false)
    expect(renderer.root.findAllByType('badge').map((badge) => badge.children.join(''))).toEqual(['Active', 'Paused'])
    expect(renderer.root.findAllByType('button')).toHaveLength(4)

    act(() => renderer.root.findAllByType('button')[0].props.onClick())
    expect(onSelectionChange.mock.calls[0][0]).toEqual(new Set(['paused']))

    act(() => renderer.root.findAllByType('button')[2].props.onClick())
    expect(onSelectionChange.mock.calls[1][0]).toEqual(new Set(['active', 'paused', 'archived']))

    act(() => renderer.root.findAllByType('button')[3].props.onClick())
    expect(onSelectionChange.mock.calls[2][0]).toEqual(new Set())
  })

  test('filters locally, delegates remote search, and summarizes large selections', () => {
    const onSelectionChange = mock(() => {})
    const onSearchChange = mock(() => {})
    let local!: ReturnType<typeof create>
    let remote!: ReturnType<typeof create>

    act(() => {
      local = create(
        <DataTableFacetedFilter
          title="Role"
          searchable
          options={[{ value: 'admin', label: 'Admin' }, { value: 'member', label: 'Member' }]}
          selectedValues={new Set(['admin', 'member', 'owner'])}
          onSelectionChange={onSelectionChange}
        />,
      )
    })

    expect(local.root.findByType('badge').children.join('')).toBe('3 selected')
    act(() => local.root.findByType('input').props.onChange({ target: { value: 'adm' } }))
    const filteredButtons = local.root.findAllByType('button')
    expect(filteredButtons).toHaveLength(2)
    expect(filteredButtons[0].findByType('span').children).toEqual(['Admin'])

    act(() => local.root.findByType('input').props.onChange({ target: { value: 'none' } }))
    expect(local.root.findAll((node) => typeof node.props.className === 'string' && node.props.className.includes('text-muted-foreground')).at(-1)?.children).toEqual(['noResults'])

    act(() => {
      remote = create(
        <DataTableFacetedFilter
          title="User"
          searchable
          onSearchChange={onSearchChange}
          options={[{ value: 'alice', label: 'Alice' }]}
          selectedValues={new Set()}
          onSelectionChange={onSelectionChange}
        />,
      )
    })

    act(() => remote.root.findByType('input').props.onChange({ target: { value: 'ali' } }))
    expect(onSearchChange).toHaveBeenCalledWith('ali')
    expect(remote.root.findByType('button').findByType('span').children).toEqual(['Alice'])
  })
})
