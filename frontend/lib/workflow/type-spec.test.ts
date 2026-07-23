import { describe, expect, test } from 'bun:test'

import { describeTypeSpec, isAssignable, legacyTypeToSpec } from './type-spec'

describe('workflow type specs', () => {
  test('normalizes legacy aliases and unknown types', () => {
    expect(legacyTypeToSpec('TEXT')).toEqual({ kind: 'string' })
    expect(legacyTypeToSpec('list')).toEqual({ kind: 'array' })
    expect(legacyTypeToSpec()).toEqual({ kind: 'any' })
    expect(legacyTypeToSpec('custom')).toEqual({ kind: 'any' })
  })

  test('describes arrays and compact object field labels', () => {
    expect(describeTypeSpec()).toBe('')
    expect(describeTypeSpec({ kind: 'array', item: { kind: 'string' } })).toBe('array<string>')
    expect(describeTypeSpec({
      kind: 'object',
      fields: { a: { kind: 'string' }, b: { kind: 'number' }, c: { kind: 'boolean' }, d: { kind: 'null' } },
    })).toBe('object{a, b, c, …}')
  })

  test('checks wildcard, nullable, array, and object assignability', () => {
    expect(isAssignable({ kind: 'string' }, undefined)).toBe(true)
    expect(isAssignable(undefined, { kind: 'number' })).toBe(true)
    expect(isAssignable({ kind: 'null' }, { kind: 'string', nullable: true })).toBe(true)
    expect(isAssignable({ kind: 'null' }, { kind: 'string' })).toBe(false)
    expect(isAssignable(
      { kind: 'array', item: { kind: 'string' } },
      { kind: 'array', item: { kind: 'number' } },
    )).toBe(false)
    expect(isAssignable(
      { kind: 'object', fields: { name: { kind: 'string' }, age: { kind: 'number' } } },
      { kind: 'object', fields: { name: { kind: 'string' } } },
    )).toBe(true)
    expect(isAssignable(
      { kind: 'object', fields: { name: { kind: 'string' } } },
      { kind: 'object', fields: { age: { kind: 'number' } } },
    )).toBe(false)
  })
})
