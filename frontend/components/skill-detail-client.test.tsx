import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
let adminSkill: unknown
let adminError: unknown
const push = mock(() => {})
const setState = mock(() => {})
const adminGet = mock(async () => {
  if (adminError) throw adminError
  return adminSkill
})
const toastError = mock(() => {})

class ApiError extends Error {}

function Badge() {}
function Button() {}
function Card() {}
function CardContent() {}
function CardHeader() {}
function CardTitle() {}
function Streamdown() {}
function ArrowLeft() {}
function Loader2() {}
function PackageOpen() {}

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  useState: () => [stateValues.shift(), setState],
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => unknown) => {
    void effect()
  },
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('streamdown', () => ({ Streamdown }))
mock.module('lucide-react', () => ({ ArrowLeft, Loader2, PackageOpen }))
mock.module('@/components/ui/badge', () => ({ Badge }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/card', () => ({ Card, CardContent, CardHeader, CardTitle }))
mock.module('@/lib/api', () => ({ ApiError, skillsApi: { get: mock(() => {}) } }))
mock.module('@/lib/api/admin', () => ({ adminSkillsApi: { get: adminGet } }))
mock.module('sonner', () => ({ toast: { error: toastError } }))

const { SkillDetailClient } = await import('./skill-detail-client')

test('shows a loading indicator while the skill is unavailable', () => {
  adminSkill = undefined
  adminError = undefined
  stateValues = [null, true]
  const tree = SkillDetailClient({ skillId: 'skill-1', mode: 'admin', backHref: '/skills' }) as {
    props: Record<string, unknown>
  }

  expect(tree.props.className).toContain('h-64')
  expect((tree.props.children as { type: Function }).type.name).toBe('Loader2')
})

test('renders detailed skill metadata, parameter names, and navigation', () => {
  const skill = {
    team_id: null,
    icon: '',
    display_name: 'Weather',
    name: 'weather',
    description: '',
    is_enabled: false,
    category: 'utility',
    version: '1.2.0',
    source_type: 'builtin',
    package_path: '',
    input_schema: { properties: { city: {}, unit: {} } },
    updated_at: '2026-07-20T12:00:00Z',
    instructions: 'Use forecast data.',
  }
  adminSkill = skill
  adminError = undefined
  stateValues = [skill, false]
  const tree = SkillDetailClient({ skillId: 'skill-1', mode: 'admin', backHref: '/skills' }) as {
    props: Record<string, unknown>
  }
  const content = JSON.stringify(tree)
  const header = (tree.props.children as Array<{ props: Record<string, unknown> }>)[0]
  const backButton = (header.props.children as Array<{ props: Record<string, unknown> }>)[0]

  backButton.props.onClick()

  expect(content).toContain('Weather')
  expect(content).toContain('noDescription')
  expect(content).toContain('disabled')
  expect(content).toContain('system')
  expect(content).toContain('city, unit')
  expect(content).toContain('Use forecast data.')
  expect((backButton.props.children as { type: Function }).type.name).toBe('ArrowLeft')
  expect(adminGet).toHaveBeenCalledWith('skill-1')
  expect(push).toHaveBeenCalledWith('/skills')
})

test('reports failed admin loads and returns to the skill list', async () => {
  adminSkill = undefined
  adminError = new ApiError('Skill unavailable')
  stateValues = [null, true]

  SkillDetailClient({ skillId: 'skill-2', mode: 'admin', backHref: '/skills' })
  await Promise.resolve()

  expect(toastError).toHaveBeenCalledWith('Skill unavailable')
  expect(push).toHaveBeenCalledWith('/skills')
  expect(setState).toHaveBeenCalledWith(false)
})

test('uses standard and fallback messages for failed loads', async () => {
  adminSkill = undefined
  adminError = new Error('Network unavailable')
  stateValues = [null, true]
  SkillDetailClient({ skillId: 'skill-3', mode: 'admin', backHref: '/skills' })
  await Promise.resolve()

  adminError = 'unexpected response'
  stateValues = [null, true]
  SkillDetailClient({ skillId: 'skill-4', mode: 'admin', backHref: '/skills' })
  await Promise.resolve()

  expect(toastError).toHaveBeenCalledWith('Network unavailable')
  expect(toastError).toHaveBeenCalledWith('Unknown error')
})
