import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) =>
  typeof type === 'function' && type.name === 'ComboboxClear' ? type(props) : { type, props }
const primitive = Object.fromEntries(
  [
    'Root',
    'Value',
    'Trigger',
    'Clear',
    'Input',
    'Portal',
    'Positioner',
    'Popup',
    'List',
    'Item',
    'ItemIndicator',
    'Group',
    'GroupLabel',
    'Collection',
    'Empty',
    'Separator',
    'Chips',
    'Chip',
    'ChipRemove',
  ].map((name) => [name, function Primitive() {}]),
)

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({ useRef: (value: unknown) => ({ current: value }) }))
mock.module('@base-ui/react', () => ({ Combobox: primitive }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/components/ui/button', () => ({ Button: function Button() {} }))
mock.module('@/components/ui/input-group', () => ({
  InputGroup: function InputGroup() {},
  InputGroupAddon: function InputGroupAddon() {},
  InputGroupButton: function InputGroupButton() {},
  InputGroupInput: function InputGroupInput() {},
}))
mock.module('lucide-react', () => ({
  ChevronDownIcon: function ChevronDownIcon() {},
  XIcon: function XIcon() {},
  CheckIcon: function CheckIcon() {},
}))

const {
  Combobox,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxChip,
  ComboboxCollection,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxLabel,
  ComboboxList,
  ComboboxSeparator,
  ComboboxTrigger,
  ComboboxValue,
  useComboboxAnchor,
} = await import('./combobox')

test('renders combobox controls and collection slots', () => {
  const trigger = ComboboxTrigger({ children: 'Choose', className: 'select' }) as {
    props: Record<string, unknown>
  }
  const value = ComboboxValue({ children: 'Selected' }) as { props: Record<string, unknown> }
  const list = ComboboxList({ className: 'results' }) as { props: Record<string, unknown> }
  const item = ComboboxItem({ children: 'Option', className: 'option' }) as {
    props: Record<string, unknown>
  }
  const group = ComboboxGroup({ className: 'group' }) as { props: Record<string, unknown> }
  const label = ComboboxLabel({ className: 'label' }) as { props: Record<string, unknown> }
  const collection = ComboboxCollection({ children: 'items' }) as { props: Record<string, unknown> }
  const empty = ComboboxEmpty({ className: 'empty' }) as { props: Record<string, unknown> }
  const separator = ComboboxSeparator({ className: 'divide' }) as { props: Record<string, unknown> }

  expect(Combobox).toBe(primitive.Root)
  expect(trigger.props['data-slot']).toBe('combobox-trigger')
  expect(trigger.props.className).toContain('select')
  expect(value.props['data-slot']).toBe('combobox-value')
  expect(list.props.className).toContain('results')
  expect(item.props['data-slot']).toBe('combobox-item')
  expect(item.props.className).toContain('option')
  expect(group.props.className).toBe('group')
  expect(label.props.className).toContain('label')
  expect(collection.props['data-slot']).toBe('combobox-collection')
  expect(empty.props.className).toContain('empty')
  expect(separator.props.className).toContain('divide')
})

test('composes inputs, popups, and chips with optional controls', () => {
  const input = ComboboxInput({ children: 'extra' }) as { props: Record<string, unknown> }
  const [baseInput, addon] = input.props.children as Array<{ props: Record<string, unknown> }>
  const [trigger] = addon.props.children as Array<{ props: Record<string, unknown> }>
  const configuredInput = ComboboxInput({
    disabled: true,
    showTrigger: false,
    showClear: true,
  }) as {
    props: Record<string, unknown>
  }
  const [, configuredAddon] = configuredInput.props.children as Array<{
    props: Record<string, unknown>
  }>
  const content = ComboboxContent({
    className: 'menu',
    anchor: {},
    side: 'top',
    sideOffset: 4,
  }) as {
    props: Record<string, unknown>
  }
  const positioner = content.props.children as { props: Record<string, unknown> }
  const popup = positioner.props.children as { props: Record<string, unknown> }
  const chips = ComboboxChips({ className: 'tags' }) as { props: Record<string, unknown> }
  const chip = ComboboxChip({ children: 'Tag' }) as { props: Record<string, unknown> }
  const chipWithoutRemove = ComboboxChip({ showRemove: false }) as {
    props: Record<string, unknown>
  }
  const chipsInput = ComboboxChipsInput({ className: 'search' }) as {
    props: Record<string, unknown>
  }
  const anchor = useComboboxAnchor()

  expect(input.props.className).toContain('w-auto')
  expect((baseInput.props.render as { props: Record<string, unknown> }).props.disabled).toBe(false)
  expect((trigger.type as Function).name).toBe('InputGroupButton')
  expect((configuredAddon.props.children as unknown[])[0]).toBe(false)
  expect(JSON.stringify(configuredAddon.props.children)).toContain('combobox-clear')
  expect(JSON.stringify(configuredAddon.props.children)).toContain('icon-xs')
  expect(positioner.props.side).toBe('top')
  expect(positioner.props.sideOffset).toBe(4)
  expect(popup.props['data-chips']).toBe(true)
  expect(popup.props.className).toContain('menu')
  expect(chips.props.className).toContain('tags')
  expect(chip.props.children as unknown[]).toHaveLength(2)
  expect(chipWithoutRemove.props.children).toEqual([undefined, false])
  expect(chipsInput.props.className).toContain('search')
  expect(anchor.current).toBeNull()
})
