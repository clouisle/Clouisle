import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldTitle,
} from './field'

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
    const singleMarkup = renderToStaticMarkup(<FieldError errors={[{ message: 'Email is required' }]} />)
    const customMarkup = renderToStaticMarkup(
      <FieldError errors={[{ message: 'Email is required' }]}>Custom error</FieldError>
    )

    expect(validationMarkup).toContain('role="alert"')
    expect(validationMarkup.match(/Email is required/g)).toHaveLength(1)
    expect(validationMarkup).toContain('Enter a valid email address')
    expect(singleMarkup).toContain('Email is required')
    expect(singleMarkup).not.toContain('<ul')
    expect(customMarkup).toContain('Custom error')
    expect(customMarkup).not.toContain('Email is required')
  })

  test('renders set, group, legend, content, title, description, and separator slots', () => {
    const markup = renderToStaticMarkup(
      <FieldSet className="custom-set">
        <FieldLegend variant="label" className="custom-legend">Account</FieldLegend>
        <FieldGroup className="custom-group">
          <Field orientation="responsive" className="custom-field">
            <FieldContent className="custom-content">
              <FieldTitle className="custom-title">Email</FieldTitle>
              <FieldDescription className="custom-description">Used for login.</FieldDescription>
            </FieldContent>
          </Field>
          <FieldSeparator className="custom-separator">or</FieldSeparator>
        </FieldGroup>
      </FieldSet>
    )

    expect(markup).toContain('data-slot="field-set"')
    expect(markup).toContain('custom-set')
    expect(markup).toContain('data-slot="field-legend"')
    expect(markup).toContain('data-variant="label"')
    expect(markup).toContain('data-slot="field-group"')
    expect(markup).toContain('data-orientation="responsive"')
    expect(markup).toContain('custom-field')
    expect(markup).toContain('data-slot="field-content"')
    expect(markup).toContain('data-slot="field-description"')
    expect(markup).toContain('data-slot="field-separator"')
    expect(markup).toContain('data-content="true"')
    expect(markup).toContain('data-slot="field-separator-content"')
    expect(markup).toContain('Used for login.')
  })
})
