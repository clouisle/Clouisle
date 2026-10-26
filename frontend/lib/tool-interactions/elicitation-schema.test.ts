import { describe, expect, test } from 'bun:test'

import { buildElicitationContent, getElicitationFields } from './elicitation-schema'

const messages = {
  required: (field: string) => `${field} required`,
  invalidNumber: (field: string) => `${field} number`,
  invalidJson: (field: string) => `${field} json`,
}

describe('getElicitationFields', () => {
  test('maps object properties with types, enums, defaults and required flags', () => {
    const fields = getElicitationFields({
      type: 'object',
      required: ['name', 'mode'],
      properties: {
        name: { type: 'string', title: 'Your name', description: 'Display name', default: 'Ada' },
        mode: { type: 'string', enum: ['fast', 'safe'] },
        count: { type: 'integer', default: 3 },
        enabled: { type: 'boolean', default: true },
        payload: { type: 'object' },
      },
    })

    expect(fields.map((field) => field.name)).toEqual(['name', 'mode', 'count', 'enabled', 'payload'])
    expect(fields[0]).toMatchObject({
      label: 'Your name',
      description: 'Display name',
      type: 'string',
      required: true,
      defaultValue: 'Ada',
      secret: false,
    })
    expect(fields[1]).toMatchObject({ type: 'enum', required: true })
    expect(fields[1].options.map((option) => option.value)).toEqual(['fast', 'safe'])
    expect(fields[2]).toMatchObject({ type: 'number', required: false, defaultValue: '3' })
    expect(fields[3]).toMatchObject({ type: 'boolean', defaultValue: true })
    expect(fields[4].type).toBe('json')
  })

  test('marks credential-shaped fields so they are never collected', () => {
    const fields = getElicitationFields({
      type: 'object',
      properties: {
        password: { type: 'string' },
        api_token: { type: 'string' },
        accessKey: { type: 'string', format: 'password' },
      },
    })

    expect(fields.every((field) => field.secret)).toBe(true)

    const ordinary = getElicitationFields({
      type: 'object',
      properties: {
        max_tokens: { type: 'integer' },
        token_count: { type: 'integer' },
      },
    })
    expect(ordinary.some((field) => field.secret)).toBe(false)
  })

  test('returns no fields for unsupported schemas', () => {
    expect(getElicitationFields(null)).toEqual([])
    expect(getElicitationFields({ type: 'array' })).toEqual([])
    expect(getElicitationFields({ type: 'object', properties: [] })).toEqual([])
  })
})

describe('buildElicitationContent', () => {
  const fields = getElicitationFields({
    type: 'object',
    required: ['name', 'count'],
    properties: {
      name: { type: 'string' },
      count: { type: 'number' },
      enabled: { type: 'boolean' },
      meta: { type: 'object' },
    },
  })

  test('coerces values and omits blank optional fields', () => {
    const result = buildElicitationContent(
      fields,
      { name: ' Ada ', count: '2', enabled: true, meta: '' },
      messages
    )

    expect(result.errors).toEqual({})
    expect(result.content).toEqual({ name: ' Ada ', count: 2, enabled: true })
  })

  test('preserves numeric enum values', () => {
    const enumFields = getElicitationFields({
      type: 'object',
      required: ['level'],
      properties: { level: { type: 'integer', enum: [1, 2] } },
    })
    const result = buildElicitationContent(enumFields, { level: '2' }, messages)
    expect(result.errors).toEqual({})
    expect(result.content).toEqual({ level: 2 })
  })

  test('reports missing required and invalid numeric or JSON values', () => {
    const result = buildElicitationContent(
      fields,
      { name: '', count: 'nope', meta: '{bad' },
      messages
    )

    expect(result.errors).toEqual({
      name: 'name required',
      count: 'count number',
      meta: 'meta json',
    })
    expect(result.content).toEqual({ enabled: false })
  })
})
