import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setters = [mock(() => {}), mock(() => {}), mock(() => {})]
let states: unknown[] = [false, null, false], stateIndex = 0
mock.module('react', () => ({ useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]] }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
const translate = Object.assign((key: string) => `memories.${key}`, { has: (key: string) => key.endsWith('.person') || key.endsWith('.knows') })
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('lucide-react', () => ({ Trash2: component, X: component }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
for (const [path, names] of [
  ['@/components/ui/alert-dialog', ['AlertDialog', 'AlertDialogAction', 'AlertDialogCancel', 'AlertDialogContent', 'AlertDialogDescription', 'AlertDialogFooter', 'AlertDialogHeader', 'AlertDialogTitle']],
  ['@/components/ui/badge', ['Badge']], ['@/components/ui/button', ['Button']],
  ['@/components/ui/sheet', ['Sheet', 'SheetContent', 'SheetDescription', 'SheetHeader', 'SheetTitle']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/api/memories', () => ({ memoriesApi: { deleteEntity: mock(() => Promise.resolve()), deleteRelation: mock(() => Promise.resolve()) } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))

const { memoriesApi } = await import('@/lib/api/memories')
const { toast } = await import('sonner')
const { EntityDetailSheet } = await import('./entity-detail-sheet')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}
const entity = { id: 'one', name: 'Alice', entity_type: 'person', description: 'Profile', properties: { role: 'Admin' }, access_count: 3, last_accessed_at: 'later', created_at: 'first' }
const other = { id: 'two', name: 'Bob', entity_type: 'custom', access_count: 0, created_at: 'second' }
const relations = [
  { id: 'out', source_entity_id: 'one', target_entity_id: 'two', relation_type: 'knows', description: 'Works together' },
  { id: 'in', source_entity_id: 'missing', target_entity_id: 'one', relation_type: 'custom' },
]

test('returns nothing without an entity', () => {
  stateIndex = 0
  expect(EntityDetailSheet({ entity: null, entities: [], relations: [], onClose: mock(() => {}), onNavigateToEntity: mock(() => {}) })).toBeNull()
})

test('shows entity details and navigates or opens deletion controls', () => {
  stateIndex = 0
  states = [false, null, false]
  const onClose = mock(() => {}), onNavigateToEntity = mock(() => {})
  const tree = EntityDetailSheet({ entity, entities: [entity, other], relations, onClose, onNavigateToEntity }) as TreeNode
  expect(text(tree)).toContain('Alice')
  expect(text(tree)).toContain('memories.entityTypes.person')
  expect(text(tree)).toContain('Profile')
  expect(text(tree)).toContain('role:Admin')
  expect(text(tree)).toContain('memories.relationTypes.knows')
  expect(text(tree)).toContain('memories.unknown')
  expect(text(tree)).toContain('date:later')
  const sheet = findAll(tree, (node) => node.props.open === true)[0]
  ;(sheet.props.onOpenChange as () => void)()
  expect(onClose).toHaveBeenCalledTimes(1)
  const relationButtons = findAll(tree, (node) => String(node.props.className).includes('flex-1 justify-start'))
  ;(relationButtons[0].props.onClick as () => void)()
  ;(relationButtons[1].props.onClick as () => void)()
  expect(onNavigateToEntity).toHaveBeenNthCalledWith(1, 'two')
  expect(onNavigateToEntity).toHaveBeenNthCalledWith(2, 'missing')
  const relationDelete = findAll(tree, (node) => String(node.props.className).includes('hover:text-destructive cursor-pointer'))[0]
  ;(relationDelete.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock(() => {}) })
  expect(setters[1]).toHaveBeenCalledWith('out')
  const entityDelete = findAll(tree, (node) => String(node.props.className).includes('w-full text-destructive'))[0]
  ;(entityDelete.props.onClick as () => void)()
  expect(setters[0]).toHaveBeenCalledWith(true)
})

test('deletes an entity and relation and resets confirmation state', async () => {
  stateIndex = 0
  states = [true, 'out', false]
  const onClose = mock(() => {}), onDeleteEntity = mock(() => {}), onDeleteRelation = mock(() => {})
  const tree = EntityDetailSheet({ entity, entities: [entity, other], relations, onClose, onNavigateToEntity: mock(() => {}), onDeleteEntity, onDeleteRelation }) as TreeNode
  const actions = findAll(tree, (node) => node.props.children === 'memories.delete' && node.props.onClick)
  await (actions[0].props.onClick as () => Promise<void>)()
  expect(memoriesApi.deleteEntity).toHaveBeenCalledWith('one')
  expect(toast.success).toHaveBeenCalledWith('memories.deleteEntitySuccess')
  expect(onDeleteEntity).toHaveBeenCalledWith('one')
  expect(onClose).toHaveBeenCalledTimes(1)
  await (actions[1].props.onClick as () => Promise<void>)()
  expect(memoriesApi.deleteRelation).toHaveBeenCalledWith('out')
  expect(toast.success).toHaveBeenCalledWith('memories.deleteRelationSuccess')
  expect(onDeleteRelation).toHaveBeenCalledWith('out')
  expect(setters[2]).toHaveBeenCalledWith(false)
  expect(setters[1]).toHaveBeenCalledWith(null)
})
