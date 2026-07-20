import { describe, expect, test } from 'bun:test'

import {
  defaultStartParameters,
  loopVariableTypeConfig,
  parameterTypeConfig,
  systemParameters,
} from './constants'
import { getLoopVarTypeName, getTypeName, isValidVariableName } from './utils'

import {
  defaultStartParameters,
  loopVariableTypeConfig,
  parameterTypeConfig,
  systemParameters,
} from './constants'
import { getLoopVarTypeName, getTypeName, isValidVariableName } from './utils'

describe('node config utilities', () => {
  test('accepts workflow variable identifiers and rejects invalid names', () => {
    expect(isValidVariableName('result')).toBe(true)
    expect(isValidVariableName('_internal_2')).toBe(true)
    expect(isValidVariableName('2result')).toBe(false)
    expect(isValidVariableName('result-name')).toBe(false)
    expect(isValidVariableName('result name')).toBe(false)
    expect(isValidVariableName('')).toBe(false)
  })

  test('maps parameter and loop variable types to display names with string fallbacks', () => {
    expect(getTypeName('number')).toBe('Number')
    expect(getTypeName('checkbox')).toBe('Boolean')
    expect(getTypeName('images')).toBe('Images')
    expect(getTypeName('unknown')).toBe('String')

    expect(getLoopVarTypeName('boolean')).toBe('Boolean')
    expect(getLoopVarTypeName('array')).toBe('Array')
    expect(getLoopVarTypeName('unknown')).toBe('String')
  })

  test('keeps built-in parameter defaults and variable metadata consistent', () => {
    expect(defaultStartParameters).toEqual([
      expect.objectContaining({ name: 'query', type: 'text', required: true, defaultValue: '' }),
    ])
    expect(systemParameters.map(({ name, valueType }) => [name, valueType])).toEqual([
      ['sys_user_id', 'String'],
      ['sys_workflow_id', 'String'],
      ['sys_workflow_run_id', 'String'],
      ['sys_timestamp', 'Number'],
    ])
    expect(parameterTypeConfig.images.valueType).toBe('array')
    expect(parameterTypeConfig.image.valueType).toBe('file')
    expect(loopVariableTypeConfig.boolean.valueType).toBe('Boolean')
  })
})
