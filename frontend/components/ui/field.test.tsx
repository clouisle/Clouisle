import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { Field, FieldError, FieldLabel } from './field'

describe('Field composition', () => {
  test('composes a label with its control and field attributes', () => {
    const markup = renderToStaticMarkup(
      <Field orientation="horizontal" data-invalid="true">
        <FieldLabel htmlFor="email">Email address</FieldLabel>
        <input id="email" aria-invalid="true" />
      </Field>
    )

    expect(markup).toContain('role="group"')
    expect(markup).toContain('data-slot="field"')
    expect(markup).toContain('data-orientation="horizontal"')
    expect(markup).toContain('data-invalid="true"')
    expect(markup).toContain('<label data-slot="field-label"')
    expect(markup).toContain('for="email"')
    expect(markup).toContain('aria-invalid="true"')
  })

  test('omits an alert when validation produces no error', () => {
    expect(renderToStaticMarkup(<FieldError errors={[]} />)).toBe('')
  })

  test('deduplicates validation messages and lets explicit content override them', () => {
    const validationMarkup = renderToStaticMarkup(
      <FieldError
        errors={[
          { message: 'Email is required' },
          { message: 'Email is required' },
          { message: 'Enter a valid email address' },
        ]}
      />
    )
    const customMarkup = renderToStaticMarkup(
      <FieldError errors={[{ message: 'Email is required' }]}>Custom error</FieldError>
    )

    expect(validationMarkup).toContain('role="alert"')
    expect(validationMarkup.match(/Email is required/g)).toHaveLength(1)
    expect(validationMarkup).toContain('Enter a valid email address')
    expect(customMarkup).toContain('Custom error')
    expect(customMarkup).not.toContain('Email is required')
  })
})
