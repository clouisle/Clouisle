import { describe, expect, test } from 'bun:test'

import { ApiError } from './api/client'
import {
  clearValidationError,
  clearValidationErrorsByPrefix,
  formatValidationSummaryMessage,
  getFieldErrorObjects,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  normalizeValidationErrorsRaw,
} from './validation'

describe('validation helpers', () => {
  test('normalizes validation errors into joined and raw field maps', () => {
    const error = new ApiError(1001, 'invalid', {
      errors: { name: 'Required', tags: ['Choose one', 'Invalid choice'] },
    })

    expect(normalizeValidationErrors(error)).toEqual({
      name: 'Required',
      tags: 'Choose one; Invalid choice',
    })
    expect(normalizeValidationErrorsRaw(error)).toEqual({
      name: ['Required'],
      tags: ['Choose one', 'Invalid choice'],
    })
  })

  test('ignores non-validation, missing-data, and non-ApiError values', () => {
    for (const error of [new Error('invalid'), new ApiError(500, 'failed'), new ApiError(1001, 'invalid')]) {
      expect(normalizeValidationErrors(error)).toEqual({})
      expect(normalizeValidationErrorsRaw(error)).toEqual({})
    }
  })

  test('clears one populated field without mutating the source', () => {
    const errors = { name: 'Required', email: 'Invalid' }

    expect(clearValidationError(errors, 'name')).toEqual({ email: 'Invalid' })
    expect(errors).toEqual({ name: 'Required', email: 'Invalid' })
  })

  test('returns the source when the requested field is absent or empty', () => {
    const errors = { name: '', email: 'Invalid' }

    expect(clearValidationError(errors, 'missing')).toBe(errors)
    expect(clearValidationError(errors, 'name')).toBe(errors)
  })

  test('clears an exact path and its descendants but not similar prefixes', () => {
    const errors = {
      profile: 'Invalid',
      'profile.name': 'Required',
      profileName: 'Too long',
      other: 'Invalid',
    }

    expect(clearValidationErrorsByPrefix(errors, 'profile')).toEqual({
      profileName: 'Too long',
      other: 'Invalid',
    })
    expect(errors).toHaveProperty('profile')
  })

  test('preserves identity when no path matches a prefix', () => {
    const errors = { profile: 'Invalid' }

    expect(clearValidationErrorsByPrefix(errors, 'other')).toBe(errors)
  })

  test('maps exact paths, descendant paths, and leaves unmatched paths intact', () => {
    const errors = {
      owner: 'Required',
      'items.0.name': 'Required',
      item: 'Unchanged',
    }

    expect(mapValidationErrors(errors, { owner: 'user', items: 'rows' })).toEqual({
      user: 'Required',
      'rows.0.name': 'Required',
      item: 'Unchanged',
    })
  })

  test('prefers exact mappings and preserves identity without a path map', () => {
    const errors = { 'items.0': 'Invalid' }

    expect(mapValidationErrors(errors, { items: 'rows', 'items.0': 'firstRow' })).toEqual({
      firstRow: 'Invalid',
    })
    expect(mapValidationErrors(errors)).toBe(errors)
  })

  test('converts populated field messages to form error objects', () => {
    const errors = { name: 'Required', empty: '' }

    expect(getFieldErrorObjects(errors, 'name')).toEqual([{ message: 'Required' }])
    expect(getFieldErrorObjects(errors, 'missing')).toBeUndefined()
    expect(getFieldErrorObjects(errors, 'empty')).toBeUndefined()
  })

  test('keeps only errors not rendered inline for any iterable', () => {
    const errors = { name: 'Required', email: 'Invalid', __all__: 'Fix the form' }

    expect(getValidationSummaryEntries(errors, new Set(['name', 'email']))).toEqual([
      ['__all__', 'Fix the form'],
    ])
    expect(getValidationSummaryEntries(errors, [])).toEqual(Object.entries(errors))
  })

  test('formats labeled fields while leaving global and unlabeled errors unchanged', () => {
    const labels = { name: 'Display name', empty: '' }

    expect(formatValidationSummaryMessage('name', 'Required', labels)).toBe('Display name: Required')
    expect(formatValidationSummaryMessage('email', 'Invalid', labels)).toBe('Invalid')
    expect(formatValidationSummaryMessage('empty', 'Required', labels)).toBe('Required')
    expect(formatValidationSummaryMessage('__all__', 'Fix the form', { __all__: 'Form' })).toBe('Fix the form')
  })
})
