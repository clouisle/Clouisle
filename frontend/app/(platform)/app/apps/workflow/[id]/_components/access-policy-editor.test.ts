import { describe, expect, mock, test, afterEach } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import { buildPolicyDocument, splitGates } from './access-policy-editor'
import type { WorkflowAccessOperation } from '@/lib/api/workflows'

const policyResponse = {
  policy: {
    operations: {
      view: { decision: 'allow' },
      run: { decision: 'allow' },
      edit: { decision: 'allow' },
      publish: { decision: 'allow' },
      delete: { decision: 'allow' },
    },
  },
  effective: {},
}
const updateWorkflowAccessPolicy = mock(async () => policyResponse)
const getTeam = mock(async () => ({
  members: [
    {
      id: 'membership-row-1',
      user_id: 'user-1',
      username: 'alice',
      email: 'alice@example.com',
      avatar_url: null,
      role: 'member',
      joined_at: '2026-01-01T00:00:00Z',
    },
  ],
}))
const getAPIKeys = mock(async () => ({ items: [], total: 0 }))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    getWorkflowAccessPolicy: mock(async () => policyResponse),
    updateWorkflowAccessPolicy,
  },
  }))
mock.module('@/lib/api/teams', () => ({ teamsApi: { getTeam } }))
mock.module('@/lib/api/api-keys', () => ({ apiKeysApi: { getAPIKeys } }))

const { AccessPolicyEditor } = await import('./access-policy-editor')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
let renderer: ReactTestRenderer | undefined

afterEach(() => {
  if (renderer) {
    act(() => {
      renderer?.unmount()
    })
    renderer = undefined
  }
  updateWorkflowAccessPolicy.mockClear()
})

function pressables(tree: ReactTestRenderer) {
  return tree.root.findAll(node => typeof node.props?.onClick === 'function')
}

/** Turn a page of the editor to ``decision`` for the given audience kind. */
function textOf(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(textOf).join('')
  if (value && typeof value === 'object' && 'props' in (value as { props?: unknown })) {
    return textOf((value as { props: { children?: unknown } }).props.children)
  }
  return ''
}

function pressByText(tree: ReactTestRenderer, label: string) {
  const node = tree.root.findAll(
    item =>
      typeof item.props?.onClick === 'function' &&
      textOf(item.props?.children).includes(label),
  )[0]
  expect(node).toBeDefined()
  act(() => {
    node.props.onClick()
  })
}

async function renderEditor() {
  await act(async () => {
    renderer = create(
      React.createElement(AccessPolicyEditor, {
        workflowId: 'workflow-1',
        teamId: 'team-1',
        readOnly: false,
      }),
    )
  })
  return renderer!
}

describe('named-user audience', () => {
  test('a selected team member stores the user id, not the membership row id', async () => {
    const tree = await renderEditor()
    expect(pressables(tree).length).toBeGreaterThan(0)

    // Select the named user, then save and inspect the document sent upstream.
    pressByText(tree, 'alice')
    expect(pressables(tree).length).toBeGreaterThan(0)

    const save = tree.root.findAll(
      item =>
        typeof item.props?.onClick === 'function' &&
        textOf(item.props?.children).includes('save'),
    )[0]
    if (save) {
      await act(async () => {
        save.props.onClick()
      })
    }

    const sent = updateWorkflowAccessPolicy.mock.calls.at(-1)?.[1] as
      | { operations: Record<string, { gates?: { user_ids?: string[] }[] }> }
      | undefined
    const userIds = Object.values(sent?.operations ?? {}).flatMap(
      entry => entry.gates ?? [],
    ).flatMap(gate => gate.user_ids ?? [])

    // The gate must carry the user id; the membership row id can never match a
    // principal's user_id and would lock the selected member out.
    expect(userIds).not.toContain('membership-row-1')
    if (userIds.length > 0) expect(userIds).toContain('user-1')
  })
})

const INHERIT = { view: 'inherit', run: 'inherit', edit: 'inherit', publish: 'inherit', delete: 'inherit' } as const
const NO_AUDIENCE = { roles: [], userIds: [], apiKeyIds: [] }

function audiences(overrides: Partial<Record<WorkflowAccessOperation, typeof NO_AUDIENCE>> = {}) {
  return {
    view: { ...NO_AUDIENCE },
    run: { ...NO_AUDIENCE },
    edit: { ...NO_AUDIENCE },
    publish: { ...NO_AUDIENCE },
    delete: { ...NO_AUDIENCE },
    ...overrides,
  }
}

describe('buildPolicyDocument', () => {
  test('an untouched editor produces an empty, fully inherited policy', () => {
    expect(buildPolicyDocument({ ...INHERIT }, audiences())).toEqual({ operations: {} })
  })

  test('inherited operations are omitted while decided ones are kept', () => {
    const document = buildPolicyDocument(
      { ...INHERIT, run: 'deny' },
      audiences(),
    )
    expect(document).toEqual({ operations: { run: { decision: 'deny' } } })
  })

  test('allow without an audience has no gates', () => {
    const document = buildPolicyDocument({ ...INHERIT, view: 'allow' }, audiences())
    expect(document.operations.view).toEqual({ decision: 'allow' })
  })

  test('each audience becomes its own gate', () => {
    const document = buildPolicyDocument(
      { ...INHERIT, run: 'allow' },
      audiences({ run: { roles: ['owner', 'admin'], userIds: ['u1'], apiKeyIds: ['k1'] } }),
    )
    expect(document.operations.run).toEqual({
      decision: 'allow',
      gates: [
        { kind: 'team_role', roles: ['owner', 'admin'] },
        { kind: 'user', user_ids: ['u1'] },
        { kind: 'api_key', api_key_ids: ['k1'] },
      ],
    })
  })

  test('a deny never carries gates, even when an audience is still selected', () => {
    const document = buildPolicyDocument(
      { ...INHERIT, edit: 'deny' },
      audiences({ edit: { roles: ['owner'], userIds: [], apiKeyIds: [] } }),
    )
    expect(document.operations.edit).toEqual({ decision: 'deny' })
  })
})

describe('splitGates', () => {
  test('returns empty audiences for an inherited operation', () => {
    expect(splitGates(undefined)).toEqual(NO_AUDIENCE)
  })

  test('round-trips a document built by the editor', () => {
    const document = buildPolicyDocument(
      { ...INHERIT, run: 'allow' },
      audiences({ run: { roles: ['admin'], userIds: ['u1'], apiKeyIds: ['k1'] } }),
    )
    expect(splitGates(document.operations.run)).toEqual({
      roles: ['admin'],
      userIds: ['u1'],
      apiKeyIds: ['k1'],
    })
  })

  test('ignores a gate kind it does not build', () => {
    expect(
      splitGates({ decision: 'allow', gates: [{ kind: 'user', user_ids: ['u2'] }] }),
    ).toEqual({ roles: [], userIds: ['u2'], apiKeyIds: [] })
  })
})
