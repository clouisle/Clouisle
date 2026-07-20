import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { ComponentExample } from './component-example'

describe('ComponentExample', () => {
  test('renders the card and form demonstrations with their initial controls', () => {
    const html = renderToStaticMarkup(<ComponentExample />)

    expect(html).toContain('Observability Plus is replacing Monitoring')
    expect(html).toContain('User Information')
    expect(html).toContain('Show Dialog')
    expect(html).toContain('Comments')
    expect(html).toContain('Submit')
    expect(html).toContain('Cancel')
  })
})
