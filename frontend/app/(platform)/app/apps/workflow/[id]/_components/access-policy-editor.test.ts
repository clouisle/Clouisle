import { describe, expect, test } from 'bun:test'

import { buildPolicyDocument, splitGates } from './access-policy-editor'
import type { WorkflowAccessOperation } from '@/lib/api/workflows'

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
