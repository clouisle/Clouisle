import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function Header() {}
function ActivitiesClient() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-intl/server', () => ({
  getTranslations: () => (key: string) => `activities.${key}`,
}))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('./_components/activities-client', () => ({ ActivitiesClient }))

const { default: ActivitiesPage, generateMetadata } = await import('./page')

test('provides localized activity metadata', async () => {
  await expect(generateMetadata()).resolves.toEqual({
    title: 'activities.title',
    description: 'activities.description',
  })
})

test('renders the activities client inside the dashboard layout', () => {
  const tree = ActivitiesPage() as { props: Record<string, unknown> }
  const [header, content] = tree.props.children as Array<{ props: Record<string, unknown> }>

  expect(tree.props.className).toBe('flex h-full flex-col')
  expect((header.type as { name?: string }).name).toBe('Header')
  expect(content.props.className).toBe('flex flex-1 flex-col gap-4 overflow-auto p-4')
  expect(((content.props.children as { type: { name?: string } }).type as { name?: string }).name).toBe(
    'ActivitiesClient',
  )
})
