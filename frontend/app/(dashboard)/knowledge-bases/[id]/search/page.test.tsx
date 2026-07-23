import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const SearchTestClient = function SearchTestClient() {}
const Header = function Header() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('./_components/search-test-client', () => ({ SearchTestClient }))

const { default: SearchTestPage } = await import('./page')

type TreeNode = { type: unknown; props: Record<string, unknown> }

function findAll(node: unknown, type: unknown): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, type))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(current.type === type ? [current] : []), ...findAll(current.props.children, type)]
}

test('resolves the route ID and renders the dashboard search shell', async () => {
  const tree = await SearchTestPage({ params: Promise.resolve({ id: 'kb-1' }) })

  expect(findAll(tree, Header)).toHaveLength(1)
  expect(findAll(tree, SearchTestClient)).toEqual([
    { type: SearchTestClient, props: { knowledgeBaseId: 'kb-1' } },
  ])
})
