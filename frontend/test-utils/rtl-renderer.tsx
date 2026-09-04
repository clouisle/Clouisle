import * as React from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { Window } from 'happy-dom'

export function act<T>(callback: () => T | Promise<T>): T | Promise<T> {
  const reactAct = (React as unknown as { act?: typeof React.act }).act
  if (!reactAct) return callback()
  return reactAct(() => {
    let result: T | Promise<T>
    flushSync(() => {
      result = callback()
    })
    return result!
  })
}

type TestProps = Record<string, unknown>
type TestType = string | ((props: TestProps) => unknown) | symbol | object

type VirtualElement = {
  type: TestType
  props?: TestProps
}

type TestChild = ReactTestInstance | string
type TestPredicate = (node: ReactTestInstance) => boolean

export interface ReactTestInstance {
  readonly type: TestType
  readonly props: TestProps
  readonly children: TestChild[]
  find(predicate: TestPredicate): ReactTestInstance
  findAll(predicate: TestPredicate): ReactTestInstance[]
  findByType(type: TestType): ReactTestInstance
  findAllByType(type: TestType): ReactTestInstance[]
  findByProps(props: TestProps): ReactTestInstance
  findAllByProps(props: TestProps): ReactTestInstance[]
}

export interface ReactTestRenderer {
  readonly root: ReactTestInstance
  toJSON(): unknown
  update(element: React.ReactNode): void
  unmount(): void
}

function isVirtualElement(value: unknown): value is VirtualElement {
  return Boolean(
    value
    && typeof value === 'object'
    && 'type' in value
    && !('$$typeof' in value),
  )
}

function propMatches(props: TestProps, expected: TestProps) {
  return Object.entries(expected).every(([key, value]) => Object.is(props[key], value))
}

function resolveVirtualValue(value: unknown): TestChild[] {
  if (value === null || value === undefined || typeof value === 'boolean') return []
  if (typeof value === 'string' || typeof value === 'number') return [String(value)]
  if (Array.isArray(value)) return value.flatMap(resolveVirtualValue)
  if (!isVirtualElement(value)) return []
  return [resolveVirtualElement(value)]
}

class VirtualNode implements ReactTestInstance {
  constructor(
    readonly type: TestType,
    readonly props: TestProps,
    readonly children: TestChild[],
  ) {}

  find(predicate: TestPredicate) {
    const match = this.findAll(predicate)[0]
    if (!match) throw new Error('No matching test instance found')
    return match
  }

  findAll(predicate: TestPredicate) {
    const matches: ReactTestInstance[] = []
    const visit = (node: ReactTestInstance) => {
      if (predicate(node)) matches.push(node)
      for (const child of node.children) {
        if (typeof child !== 'string') visit(child)
      }
    }
    visit(this)
    return matches
  }

  findByType(type: TestType) {
    return this.find((node) => node.type === type)
  }

  findAllByType(type: TestType) {
    return this.findAll((node) => node.type === type)
  }

  findByProps(props: TestProps) {
    return this.find((node) => propMatches(node.props, props))
  }

  findAllByProps(props: TestProps) {
    return this.findAll((node) => propMatches(node.props, props))
  }
}

function resolveVirtualElement(element: VirtualElement): VirtualNode {
  const props = element.props ?? {}
  if (typeof element.type === 'function') {
    return new VirtualNode(element.type, props, resolveVirtualValue(element.type(props)))
  }
  return new VirtualNode(element.type, props, resolveVirtualValue(props.children))
}

function virtualJson(node: ReactTestInstance): unknown {
  const children = node.children.map((child) => typeof child === 'string' ? child : virtualJson(child))
  if (typeof node.type !== 'string') {
    if (!children.length) return null
    return children.length === 1 ? children[0] : children
  }
  const props = { ...node.props }
  delete props.children
  return { type: node.type, props, children: children.length ? children : null }
}

class VirtualRenderer implements ReactTestRenderer {
  private tree: VirtualNode

  constructor(element: VirtualElement) {
    this.tree = resolveVirtualElement(element)
  }

  get root() {
    return this.tree
  }

  toJSON() {
    return virtualJson(this.tree)
  }

  update(element: React.ReactNode) {
    this.tree = resolveVirtualElement(element as VirtualElement)
  }

  unmount() {
    this.tree = new VirtualNode('root', {}, [])
  }
}

type Fiber = {
  tag: number
  type: TestType
  elementType?: TestType
  child: Fiber | null
  sibling: Fiber | null
  return: Fiber | null
  alternate?: Fiber | null
  stateNode?: { current?: Fiber } | object
  memoizedProps: TestProps | string | null
}

const HOST_ROOT = 3
const HOST_COMPONENT = 5
const HOST_TEXT = 6
const FRAGMENT = 7
const MODE = 8
const PROFILER = 12
const SUSPENSE = 13
const MEMO = 14
const SIMPLE_MEMO = 15

function fiberKey(target: object, prefix: string) {
  return Object.getOwnPropertyNames(target).find((key) => key.startsWith(prefix))
}

function currentRoot(container: HTMLElement): Fiber {
  const key = fiberKey(container, '__reactContainer$')
  const root = key
    ? (container as unknown as Record<string, { stateNode?: { current?: Fiber } } | undefined>)[key]
    : undefined
  const current = root?.stateNode?.current
  if (current) return current

  const firstNode = container.firstChild
  if (firstNode && typeof firstNode === 'object') {
    const fiberKeyName = fiberKey(firstNode, '__reactFiber$')
    const fiber = fiberKeyName
      ? (firstNode as unknown as Record<string, Fiber | undefined>)[fiberKeyName]
      : undefined
    if (fiber) {
      let currentFiber = fiber
      while (currentFiber.return) currentFiber = currentFiber.return
      return currentFiber
    }
  }

  throw new Error('Unable to locate the mounted React root')
}

type FiberRootGetter = () => Fiber

function fiberForHostNode(fiber: Fiber): Fiber | undefined {
  if (!fiber.stateNode || typeof fiber.stateNode !== 'object') return undefined
  const key = fiberKey(fiber.stateNode, '__reactFiber$')
  return key ? (fiber.stateNode as Record<string, Fiber | undefined>)[key] : undefined
}

function containsFiber(root: Fiber, target: Fiber): boolean {
  const pending: Fiber[] = [root]
  const visited = new Set<Fiber>()
  while (pending.length) {
    const fiber = pending.pop()!
    if (fiber === target) return true
    if (visited.has(fiber)) continue
    visited.add(fiber)
    if (fiber.child) pending.push(fiber.child)
    if (fiber.sibling) pending.push(fiber.sibling)
  }
  return false
}

function currentFiber(fiber: Fiber, getRoot: FiberRootGetter): Fiber {
  const root = getRoot()
  const hostFiber = fiberForHostNode(fiber)
  if (hostFiber && containsFiber(root, hostFiber)) return hostFiber
  if (hostFiber?.alternate && containsFiber(root, hostFiber.alternate)) return hostFiber.alternate
  if (containsFiber(root, fiber)) return fiber
  if (fiber.alternate && containsFiber(root, fiber.alternate)) return fiber.alternate
  return fiber
}

function publicRoot(fiber: Fiber): Fiber {
  if (fiber.tag !== HOST_ROOT) return fiber
  const firstChild = fiber.child
  return firstChild && !firstChild.sibling ? firstChild : fiber
}
function fiberProps(fiber: Fiber): TestProps {
  if (fiber.memoizedProps && typeof fiber.memoizedProps === 'object') return fiber.memoizedProps
  return {}
}

function fiberType(fiber: Fiber): TestType {
  if (fiber.tag === FRAGMENT || fiber.tag === MODE || fiber.tag === PROFILER || fiber.tag === SUSPENSE) {
    return fiber.elementType ?? fiber.type ?? Symbol.for('react.fragment')
  }
  if (fiber.tag === MEMO || fiber.tag === SIMPLE_MEMO) return fiber.elementType ?? fiber.type
  return fiber.type
}

function isTestFiber(fiber: Fiber) {
  return fiber.tag !== HOST_ROOT && fiber.tag !== HOST_TEXT
}

function fiberChildren(fiber: Fiber, getRoot: FiberRootGetter): TestChild[] {
  const children: TestChild[] = []
  let child = fiber.child
  while (child) {
    if (child.tag === HOST_TEXT) {
      if (typeof child.memoizedProps === 'string') children.push(child.memoizedProps)
    } else if (isTestFiber(child)) {
      children.push(new DomTestInstance(child, getRoot))
    }
    child = child.sibling
  }
  if (!children.length) {
    const value = fiberProps(fiber).children
    if (typeof value === 'string' || typeof value === 'number') children.push(String(value))
  }
  return children
}

class DomTestInstance implements ReactTestInstance {
  constructor(
    private readonly fiber: Fiber,
    private readonly getRoot: FiberRootGetter,
  ) {}

  private get current() {
    return currentFiber(this.fiber, this.getRoot)
  }

  get type() {
    return fiberType(this.current)
  }

  get props() {
    return fiberProps(this.current)
  }

  get children() {
    return fiberChildren(this.current, this.getRoot)
  }

  find(predicate: TestPredicate) {
    const match = this.findAll(predicate)[0]
    if (!match) throw new Error('No matching test instance found')
    return match
  }

  findAll(predicate: TestPredicate) {
    const matches: ReactTestInstance[] = []
    const visit = (node: ReactTestInstance) => {
      if (predicate(node)) matches.push(node)
      for (const child of node.children) {
        if (typeof child !== 'string') visit(child)
      }
    }
    visit(this)
    return matches
  }

  findByType(type: TestType) {
    return this.find((node) => node.type === type)
  }

  findAllByType(type: TestType) {
    return this.findAll((node) => node.type === type)
  }

  findByProps(props: TestProps) {
    return this.find((node) => propMatches(node.props, props))
  }

  findAllByProps(props: TestProps) {
    return this.findAll((node) => propMatches(node.props, props))
  }
}


function jsonValue(value: unknown, ancestors: Set<object>): unknown {
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'function' || typeof value === 'symbol' || typeof value === 'bigint') return undefined
  if (value instanceof Date) return value.toISOString()
  if (value instanceof RegExp) return String(value)
  if (typeof value !== 'object') return undefined
  if (ancestors.has(value)) return undefined
  if (value instanceof Map || value instanceof Set || 'nodeType' in value || 'ownerDocument' in value) return {}

  let prototype: object | null
  try {
    prototype = Object.getPrototypeOf(value)
  } catch {
    return undefined
  }
  if (prototype !== Object.prototype && prototype !== null && !Array.isArray(value)) return {}

  ancestors.add(value)
  let result: unknown
  if (Array.isArray(value)) {
    result = value.map((item) => jsonValue(item, ancestors))
  } else {
    const object: Record<string, unknown> = {}
    for (const key of Object.keys(value)) {
      if (key === 'toJSON') continue
      let item: unknown
      try {
        item = (value as Record<string, unknown>)[key]
      } catch {
        continue
      }
      const normalized = jsonValue(item, ancestors)
      if (normalized !== undefined) object[key] = normalized
    }
    result = object
  }
  ancestors.delete(value)
  return result
}

function jsonProps(fiber: Fiber): TestProps {
  const props: TestProps = {}
  const source = fiberProps(fiber)
  for (const [key, value] of Object.entries(source)) {
    if (key === 'children' || key === 'ref') continue
    const normalized = jsonValue(value, new Set())
    if (normalized !== undefined) props[key] = normalized
  }
  return props
}

function fiberJson(fiber: Fiber): unknown {
  if (fiber.tag === HOST_TEXT) return typeof fiber.memoizedProps === 'string' ? fiber.memoizedProps : null

  const children: unknown[] = []
  let child = fiber.child
  while (child) {
    const value = fiberJson(child)
    if (value !== null && value !== undefined) children.push(value)
    child = child.sibling
  }

  if (fiber.tag !== HOST_COMPONENT) {
    if (!children.length) return null
    return children.length === 1 ? children[0] : children
  }

  const props = jsonProps(fiber)
  if (!children.length) {
    const value = fiberProps(fiber).children
    if (typeof value === 'string' || typeof value === 'number') children.push(String(value))
  }
  return {
    type: typeof fiber.type === 'string' ? fiber.type : String(fiber.type),
    props,
    children: children.length ? children : null,
  }
}

type SuppliedWindow = Record<string, unknown>
type SuppliedDocument = {
  title?: string
  querySelector?: (selectors: string) => unknown
  head?: { appendChild?: (node: unknown) => unknown }
  createElement?: (tag: string) => unknown
  body?: { appendChild?: (node: unknown) => unknown; removeChild?: (node: unknown) => unknown }
}

type GlobalObject = typeof globalThis & Record<string, unknown>

const PRESERVED_GLOBALS = [
  'localStorage',
  'navigator',
  'URL',
  'history',
  'location',
  'innerWidth',
  'innerHeight',
  'getSelection',
  'matchMedia',
  'confirm',
  'open',
  'setTimeout',
  'clearTimeout',
  'setInterval',
  'clearInterval',
  'requestAnimationFrame',
  'cancelAnimationFrame',
  'IntersectionObserver',
  'ResizeObserver',
  'MutationObserver',
  'EventSource',
  'WebSocket',
  'fetch',
  'File',
  'Blob',
  'FormData',
  'Headers',
  'Request',
  'Response',
]
type RendererElement = { type: string; props: TestProps }
type RendererOptions = {
  createNodeMock?: (element: RendererElement) => unknown
}

function applyNodeMock(element: Element, nodeMock: unknown) {
  if (!nodeMock || typeof nodeMock !== 'object') return
  for (const key of Object.keys(nodeMock)) {
    if (key === 'nodeType' || key === 'ownerDocument') continue
    const value = (nodeMock as Record<string, unknown>)[key]
    if (typeof value === 'function') {
      try {
        Object.defineProperty(element, key, {
          configurable: true,
          value: value.bind(nodeMock),
        })
      } catch {
        // Read-only DOM methods are left intact.
      }
      continue
    }
    try {
      Object.defineProperty(element, key, {
        configurable: true,
        get: () => (nodeMock as Record<string, unknown>)[key],
        set: (nextValue) => { (nodeMock as Record<string, unknown>)[key] = nextValue },
      })
    } catch {
      // Read-only DOM properties are left intact.
    }
  }
}

function renderWithNodeMocks<T>(
  document: Document,
  options: RendererOptions | undefined,
  render: () => T,
): T {
  const createNodeMock = options?.createNodeMock
  if (!createNodeMock) return render()

  const nativeCreateElement = document.createElement.bind(document)
  document.createElement = ((tag: string, elementOptions?: ElementCreationOptions) => {
    const element = nativeCreateElement(tag, elementOptions)
    applyNodeMock(element, createNodeMock({ type: tag, props: {} }))
    return element
  }) as typeof document.createElement
  try {
    return render()
  } finally {
    document.createElement = nativeCreateElement as typeof document.createElement
  }
}


function globalValue(name: string) {
  return (globalThis as GlobalObject)[name]
}

function defineGlobal(name: string, value: unknown) {
  if (value === undefined) return
  try {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  } catch {
    // Some host globals cannot be redefined; the current environment remains usable.
  }
}

function usableDocument(value: unknown): value is Document {
  if (!value || typeof value !== 'object') return false
  const document = value as Document
  const probe = typeof document.createElement === 'function' ? document.createElement('div') : undefined
  return Boolean(
    document.body
    && typeof document.body.appendChild === 'function'
    && probe
    && typeof probe === 'object'
    && 'nodeType' in probe,
  )
}

function localDocument() {
  return new Window({ url: 'http://localhost' }).document as unknown as Document
}

function canRegisterGlobally() {
  for (const name of ['window', 'document', 'navigator', 'location']) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name)
    if (descriptor && !descriptor.configurable) return false
  }
  return true
}

function copySuppliedWindow(windowValue: unknown) {
  if (!windowValue || typeof windowValue !== 'object' || windowValue === globalThis) return
  for (const [name, value] of Object.entries(windowValue as SuppliedWindow)) {
    if (name !== 'window' && name !== 'document' && name !== 'globalThis') defineGlobal(name, value)
  }
}

function restoreSuppliedDocument(
  suppliedDocument: SuppliedDocument | undefined,
  actualDocument: Document,
) {
  if (!suppliedDocument) return
  if (suppliedDocument.title !== undefined) {
    const suppliedTitle = suppliedDocument.title
    try {
      Object.defineProperty(actualDocument, 'title', {
        configurable: true,
        get: () => suppliedDocument.title ?? '',
        set: (value: string) => { suppliedDocument.title = value },
      })
      actualDocument.title = suppliedTitle
    } catch {
      actualDocument.title = suppliedTitle
    }
  }

  const suppliedQuerySelector = suppliedDocument.querySelector
  if (suppliedQuerySelector) {
    const nativeQuerySelector = actualDocument.querySelector.bind(actualDocument)
    actualDocument.querySelector = ((selectors: string) => {
      const node = suppliedQuerySelector.call(suppliedDocument, selectors)
      return (node as Element | null) ?? nativeQuerySelector(selectors)
    }) as typeof actualDocument.querySelector
  }

  const suppliedCreateElement = suppliedDocument.createElement
  if (suppliedCreateElement) {
    const nativeCreateElement = actualDocument.createElement.bind(actualDocument)
    actualDocument.createElement = ((tag: string, options?: ElementCreationOptions) => {
      const suppliedElement = suppliedCreateElement.call(suppliedDocument, tag)
      if (
        tag === 'a'
        && suppliedElement
        && typeof suppliedElement === 'object'
        && typeof (suppliedElement as { click?: unknown }).click === 'function'
      ) {
        return suppliedElement as HTMLAnchorElement
      }
      return nativeCreateElement(tag, options)
    }) as typeof actualDocument.createElement
  }

  const suppliedAppendHead = suppliedDocument.head?.appendChild
  if (suppliedAppendHead) {
    actualDocument.head.appendChild = ((node: Node) => {
      const relativeHref = (node as HTMLLinkElement).getAttribute?.('href')
      suppliedAppendHead.call(suppliedDocument.head, relativeHref ? { href: relativeHref } : node)
      return node
    }) as typeof actualDocument.head.appendChild
  }

  const suppliedAppendBody = suppliedDocument.body?.appendChild
  const nativeAppendBody = actualDocument.body.appendChild.bind(actualDocument.body)
  if (suppliedAppendBody) {
    actualDocument.body.appendChild = ((node: Node) => {
      if (!('nodeType' in (node as object))) return suppliedAppendBody.call(suppliedDocument.body, node)
      return nativeAppendBody(node)
    }) as typeof actualDocument.body.appendChild
  }

  const suppliedRemoveBody = suppliedDocument.body?.removeChild
  const nativeRemoveBody = actualDocument.body.removeChild.bind(actualDocument.body)
  if (suppliedRemoveBody) {
    actualDocument.body.removeChild = ((node: Node) => {
      if (!('nodeType' in (node as object))) return suppliedRemoveBody.call(suppliedDocument.body, node)
      return nativeRemoveBody(node)
    }) as typeof actualDocument.body.removeChild
  }
}

function installDomGlobals(document: Document) {
  const view = document.defaultView as unknown as Record<string, unknown> | null
  if (!view) return
  if (globalValue('window') === undefined) defineGlobal('window', view)
  for (const name of ['CustomEvent', 'Event']) {
    if (view[name] !== undefined) defineGlobal(name, view[name])
  }
  for (const name of ['File', 'Blob', 'FormData', 'Headers', 'Request', 'Response']) {
    if (globalValue(name) === undefined && view[name] !== undefined) defineGlobal(name, view[name])
  }
}

function ensureDom(): Document {
  const currentDocument = globalValue('document')
  const suppliedWindow = globalValue('window')
  const suppliedDocument = currentDocument as SuppliedDocument | undefined
  if (usableDocument(currentDocument)) {
    copySuppliedWindow(suppliedWindow)
    installDomGlobals(currentDocument)
    return currentDocument
  }

  const suppliedGlobals = new Map(PRESERVED_GLOBALS.map((name) => [name, globalValue(name)]))
  if (!canRegisterGlobally()) {
    const document = localDocument()
    installDomGlobals(document)
    return document
  }

  if (GlobalRegistrator.isRegistered) {
    const unregisterResult = GlobalRegistrator.unregister()
    if (unregisterResult && typeof (unregisterResult as Promise<unknown>).catch === 'function') {
      void (unregisterResult as Promise<unknown>).catch(() => undefined)
    }
  }

  try {
    GlobalRegistrator.register({ url: 'http://localhost' })
  } catch {
    if (GlobalRegistrator.isRegistered) {
      const unregisterResult = GlobalRegistrator.unregister()
      if (unregisterResult && typeof (unregisterResult as Promise<unknown>).catch === 'function') {
        void (unregisterResult as Promise<unknown>).catch(() => undefined)
      }
    }
    const document = localDocument()
    installDomGlobals(document)
    return document
  }

  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  for (const [name, value] of suppliedGlobals) defineGlobal(name, value)
  copySuppliedWindow(suppliedWindow)
  restoreSuppliedDocument(suppliedDocument, globalThis.document)
  installDomGlobals(globalThis.document)
  return globalThis.document
}

class DomRenderer implements ReactTestRenderer {
  constructor(
    private readonly reactRoot: Root,
    private readonly container: HTMLElement,
    private readonly document: Document,
    private readonly options?: RendererOptions,
  ) {}

  get root() {
    const getRoot = () => publicRoot(currentRoot(this.container))
    return new DomTestInstance(getRoot(), getRoot)
  }

  toJSON() {
    return fiberJson(currentRoot(this.container))
  }

  update(element: React.ReactNode) {
    renderWithNodeMocks(this.document, this.options, () => {
      flushSync(() => this.reactRoot.render(element))
    })
  }

  unmount() {
    flushSync(() => this.reactRoot.unmount())
    this.container.remove()
  }
}

export function create(element: React.ReactNode, options?: RendererOptions): ReactTestRenderer {
  if (isVirtualElement(element)) return new VirtualRenderer(element)

  const candidate = element as unknown as {
    $$typeof?: unknown
    type?: unknown
    props?: TestProps
  }
  if (
    candidate
    && typeof candidate === 'object'
    && '$$typeof' in candidate
    && typeof candidate.type === 'function'
    && typeof (React as unknown as { createElement?: unknown }).createElement !== 'function'
  ) {
    const output = candidate.type(candidate.props ?? {})
    if (isVirtualElement(output)) return new VirtualRenderer(output)
  }

  const document = ensureDom()
  const container = document.createElement('div')
  document.body.appendChild(container)
  const reactRoot = createRoot(container)
  renderWithNodeMocks(document, options, () => {
    flushSync(() => reactRoot.render(element))
  })
  return new DomRenderer(reactRoot, container, document, options)
}

type TestRendererNamespace = {
  create: typeof create
}

const TestRenderer: TestRendererNamespace = { create }
export default TestRenderer
