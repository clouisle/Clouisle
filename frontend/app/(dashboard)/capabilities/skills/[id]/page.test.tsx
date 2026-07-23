import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function Header() {}
function SkillDetailClient() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('@/components/skill-detail-client', () => ({ SkillDetailClient }))

const { default: AdminSkillDetailPage } = await import('./page')

test('renders the selected admin skill with a return route to the skills tab', async () => {
  const tree = (await AdminSkillDetailPage({ params: Promise.resolve({ id: 'skill-1' }) })) as {
    props: Record<string, unknown>
  }
  const [header, content] = tree.props.children as Array<{ props: Record<string, unknown> }>
  const detail = content.props.children as { type: { name?: string }; props: Record<string, unknown> }

  expect(tree.props.className).toBe('flex h-full flex-col')
  expect((header.type as { name?: string }).name).toBe('Header')
  expect(content.props.className).toBe('flex-1 overflow-auto p-4')
  expect(detail.type.name).toBe('SkillDetailClient')
  expect(detail.props).toMatchObject({
    skillId: 'skill-1',
    mode: 'admin',
    backHref: '/capabilities?tab=skills',
  })
})
