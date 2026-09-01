import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test'

interface ElementNode {
  type: unknown
  props: Record<string, unknown>
  key?: unknown
}

const fakeContainer = {
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 300 }),
}
const fakeList = {
  querySelector: () => ({ scrollIntoView: mock(() => {}) }),
}
const fakeEditor = {
  nodeType: 1,
  tagName: 'DIV',
  childNodes: [] as unknown[],
  innerHTML: '',
  focus: mock(() => {}),
  contains: () => false,
  getAttribute: () => null,
}

let stateSlots: unknown[] = []
let hookIndex = 0
let effects: Array<() => void> = []
let selectionRange: Record<string, unknown> | null = null

function makeElement(type: unknown, props: Record<string, unknown> = {}, key?: unknown): ElementNode {
  const ref = props.ref as { current: unknown } | undefined
  const className = String(props.className || '')

  if (ref && props.contentEditable) {
    ref.current = fakeEditor
  } else if (ref && className.includes('relative')) {
    ref.current = fakeContainer
  } else if (ref && className.includes('max-h-48')) {
    ref.current = fakeList
  } else if (ref) {
    ref.current = { contains: () => false }
  }

  if (typeof type === 'function') {
    return (type as (componentProps: Record<string, unknown>) => ElementNode)({ ...props, key })
  }

  return { type, props, key }
}

mock.module('react', () => ({
  useRef: (initial: unknown) => {
    const index = hookIndex++
    if (!stateSlots[index]) stateSlots[index] = { current: initial }
    return stateSlots[index]
  },
  useState: (initial: unknown) => {
    const index = hookIndex++
    if (!(index in stateSlots)) stateSlots[index] = initial
    const setState = (next: unknown) => {
      stateSlots[index] = typeof next === 'function'
        ? (next as (previous: unknown) => unknown)(stateSlots[index])
        : next
    }
    return [stateSlots[index], setState]
  },
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void) => { effects.push(effect) },
}))

mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: makeElement,
  Fragment: 'Fragment',
}))
mock.module('react/jsx-runtime', () => ({
  jsx: makeElement,
  jsxs: makeElement,
  Fragment: 'Fragment',
}))

mock.module('@/components/ui/button', () => ({
  Button: (props: Record<string, unknown>) => makeElement('button', props),
}))

mock.module('lucide-react', () => ({
  AlertCircle: (props: Record<string, unknown>) => makeElement('svg', props),
  Plus: (props: Record<string, unknown>) => makeElement('svg', props),
  Variable: (props: Record<string, unknown>) => makeElement('svg', props),
}))

mock.module('@/lib/utils', () => ({
  cn: (...classes: Array<string | false | null | undefined>) => classes.filter(Boolean).join(' '),
}))

const { PromptVariableEditor } = await import('./prompt-variable-editor')

const variables = [
  { ref: 'user.name', name: 'User name', label: 'Profile', type: 'string', isSystem: true },
  { ref: 'order.total', name: 'Order total', label: 'Cart', type: 'number' },
  { ref: 'draft', name: 'Draft', groupId: 'drafts', groupLabel: 'Draft fields' },
]

beforeEach(() => {
  stateSlots = []
  hookIndex = 0
  effects = []
  selectionRange = null
  fakeEditor.childNodes = []
  fakeEditor.innerHTML = ''

  Object.assign(globalThis, {
    Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
    document: {
      addEventListener: mock(() => {}),
      removeEventListener: mock(() => {}),
      createRange: () => ({ setStart: mock(() => {}), collapse: mock(() => {}) }),
      execCommand: mock(() => true),
    },
    window: {
      getSelection: () => ({
        rangeCount: selectionRange ? 1 : 0,
        getRangeAt: () => selectionRange,
        removeAllRanges: mock(() => {}),
        addRange: mock(() => {}),
      }),
    },
  })
})

afterEach(() => {
  mock.restore()
})

function renderEditor(props: Record<string, unknown> = {}) {
  hookIndex = 0
  effects = []

  const onChange = props.onChange || mock(() => {})
  const tree = PromptVariableEditor({
    value: '',
    onChange,
    variables,
    placeholder: 'Write prompt',
    ...props,
  })

  effects.forEach((effect) => effect())
  return { tree, onChange }
}

function textNode(text: string) {
  return { nodeType: 3, textContent: text }
}

function inputText(editor: ElementNode, text: string) {
  const node = textNode(text)
  fakeEditor.childNodes = [node]
  selectionRange = {
    startContainer: node,
    startOffset: text.length,
    getBoundingClientRect: () => ({ bottom: 0, left: 0, width: 0 }),
  }
  ;(editor.props.onInput as () => void)()
}

function childrenOf(node: unknown): unknown[] {
  if (!node || typeof node !== 'object') return []
  const children = (node as ElementNode).props?.children
  return Array.isArray(children) ? children : [children]
}

function textContent(node: unknown): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textContent).join('')
  return childrenOf(node).map(textContent).join('')
}

function findAll(node: unknown, predicate: (element: ElementNode) => boolean): ElementNode[] {
  if (!node || typeof node !== 'object') return []
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))

  const element = node as ElementNode
  return [
    ...(predicate(element) ? [element] : []),
    ...childrenOf(element).flatMap((child) => findAll(child, predicate)),
  ]
}

function editorFrom(tree: ElementNode): ElementNode {
  const editor = findAll(tree, (element) => element.props.contentEditable === true)[0]
  expect(editor).toBeTruthy()
  return editor
}

function buttonsWith(tree: ElementNode, text: string): ElementNode[] {
  return findAll(tree, (element) => element.type === 'button' && textContent(element).includes(text))
}

describe('PromptVariableEditor', () => {
  it('renders known variables and deduplicates undefined-variable actions', () => {
    const onUndefinedVariableClick = mock(() => {})
    const { tree } = renderEditor({
      value: 'Hi {{user.name}} {{missing}} {{missing}} {{draft}}',
      showUndefinedWarnings: true,
      undefinedVariablesHintText: 'Missing variables need setup',
      onUndefinedVariableClick,
    })

    expect(fakeEditor.innerHTML).toContain('User name')
    expect(fakeEditor.innerHTML).toContain('Profile')
    expect(fakeEditor.innerHTML).toContain('Draft')
    expect(textContent(tree)).toContain('Missing variables need setup')

    const missingButtons = buttonsWith(tree, '{{missing}}')
    expect(missingButtons).toHaveLength(1)

    ;(missingButtons[0].props.onClick as () => void)()
    expect(onUndefinedVariableClick).toHaveBeenCalledWith('missing')
  })

  it('filters suggestions by query and inserts the selected variable from keyboard controls', () => {
    let { tree, onChange } = renderEditor({ groupMode: 'system-user', systemGroupLabel: 'System', userGroupLabel: 'User' })
    const editor = editorFrom(tree)

    inputText(editor, 'Hello {{user')
    ;({ tree, onChange } = renderEditor({ onChange, groupMode: 'system-user', systemGroupLabel: 'System', userGroupLabel: 'User' }))

    expect(textContent(tree)).toContain('System')
    expect(textContent(tree)).toContain('User name')
    expect(textContent(tree)).toContain('Profile')
    expect(textContent(tree)).toContain('string')
    expect(textContent(tree)).not.toContain('Order total')

    ;(editorFrom(tree).props.onKeyDown as (event: Record<string, unknown>) => void)({ key: 'Enter', preventDefault: mock(() => {}) })

    expect(onChange).toHaveBeenLastCalledWith('Hello {{user.name}}')
    expect(fakeEditor.innerHTML).toContain('User name')
  })

  it('supports mouse insertion, grouped labels, plain text edits, and closing suggestions', () => {
    let { tree, onChange } = renderEditor({ groupMode: 'custom' })
    let editor = editorFrom(tree)

    inputText(editor, '{{draft')
    ;({ tree, onChange } = renderEditor({ onChange, groupMode: 'custom' }))

    expect(textContent(tree)).toContain('Draft fields')

    const draftButton = buttonsWith(tree, 'Draft')[0]
    ;(draftButton.props.onMouseDown as (event: Record<string, unknown>) => void)({ preventDefault: mock(() => {}) })
    expect(onChange).toHaveBeenLastCalledWith('{{draft}}')

    editor = editorFrom(renderEditor({ onChange, groupMode: 'custom' }).tree)
    inputText(editor, 'plain edit')
    expect(onChange).toHaveBeenLastCalledWith('plain edit')

    inputText(editor, '{{order')
    ;({ tree, onChange } = renderEditor({ onChange, groupMode: 'custom' }))
    expect(textContent(tree)).toContain('Order total')

    ;(editorFrom(tree).props.onKeyDown as (event: Record<string, unknown>) => void)({ key: 'Escape', preventDefault: mock(() => {}) })
    ;({ tree } = renderEditor({ onChange, groupMode: 'custom' }))
    expect(textContent(tree)).not.toContain('Order total')
  })

  it('shows no-result validation text and create-variable control when creation is allowed', () => {
    const onCreateVariable = mock(() => {})
    let { tree } = renderEditor({
      allowCreateVariable: true,
      onCreateVariable,
      noVariablesText: 'No matching variables',
      variableNotFoundText: (query: string) => `No variable named ${query}`,
      createVariableText: (name: string) => `Add ${name}`,
    })

    inputText(editorFrom(tree), '{{new.field')
    ;({ tree } = renderEditor({
      allowCreateVariable: true,
      onCreateVariable,
      noVariablesText: 'No matching variables',
      variableNotFoundText: (query: string) => `No variable named ${query}`,
      createVariableText: (name: string) => `Add ${name}`,
    }))

    expect(textContent(tree)).toContain('No variable named new.field')

    const createButton = buttonsWith(tree, 'Add new.field')[0]
    ;(createButton.props.onMouseDown as (event: Record<string, unknown>) => void)({ preventDefault: mock(() => {}) })
    expect(onCreateVariable).toHaveBeenCalledWith('new.field')
  })

  it('keeps suggestions closed for invalid variable syntax and during composition', () => {
    let { tree, onChange } = renderEditor({ noVariablesText: 'No variables' })
    let editor = editorFrom(tree)

    inputText(editor, '{{bad query')
    ;({ tree, onChange } = renderEditor({ onChange, noVariablesText: 'No variables' }))

    expect(onChange).toHaveBeenLastCalledWith('{{bad query')
    expect(textContent(tree)).not.toContain('No variables')

    editor = editorFrom(tree)
    ;(editor.props.onCompositionStart as () => void)()
    inputText(editor, '{{user')
    ;({ tree, onChange } = renderEditor({ onChange, noVariablesText: 'No variables' }))
    expect(textContent(tree)).not.toContain('User name')

    ;(editorFrom(tree).props.onCompositionEnd as () => void)()
    ;({ tree } = renderEditor({ onChange, noVariablesText: 'No variables' }))
    expect(textContent(tree)).toContain('User name')
  })
})
