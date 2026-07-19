import { describe, expect, test } from 'bun:test'

import { getLoopVarTypeName, getTypeName, isValidVariableName } from './utils'

describe('node config utilities', () => {
  test('accepts variable names beginning with a letter or underscore', () => {
    expect(isValidVariableName('result')).toBe(true)
    expect(isValidVariableName('_result_2')).toBe(true)
  })

  test('rejects empty, numeric-leading, and punctuated variable names', () => {
    expect(isValidVariableName('')).toBe(false)
    expect(isValidVariableName('2result')).toBe(false)
    expect(isValidVariableName('result-name')).toBe(false)
    expect(isValidVariableName('result name')).toBe(false)
  })

  test('maps parameter types and falls back to String', () => {
    expect(getTypeName('number')).toBe('Number')
    expect(getTypeName('checkbox')).toBe('Boolean')
    expect(getTypeName('array')).toBe('Array')
    expect(getTypeName('object')).toBe('Object')
    expect(getTypeName('file')).toBe('File')
    expect(getTypeName('image')).toBe('Image')
    expect(getTypeName('files')).toBe('Files')
    expect(getTypeName('images')).toBe('Images')
    expect(getTypeName('unknown')).toBe('String')
  })

  test('maps loop variable types and falls back to String', () => {
    expect(getLoopVarTypeName('number')).toBe('Number')
    expect(getLoopVarTypeName('boolean')).toBe('Boolean')
    expect(getLoopVarTypeName('array')).toBe('Array')
    expect(getLoopVarTypeName('object')).toBe('Object')
    expect(getLoopVarTypeName('')).toBe('String')
  })
})
