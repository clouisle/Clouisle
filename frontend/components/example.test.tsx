import { describe, expect, it } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { Example, ExampleWrapper } from './example'

describe('Example', () => {
  it('renders its title and content in their semantic slots', () => {
    const html = renderToStaticMarkup(
      <Example title="Account settings" data-testid="example">
        <button>Save changes</button>
      </Example>
    )

    expect(html).toContain('data-slot="example"')
    expect(html).toContain('data-slot="example-content"')
    expect(html).toContain('Account settings')
    expect(html).toContain('<button>Save changes</button>')
    expect(html).toContain('data-testid="example"')
  })

  it('renders wrapper children and forwards wrapper attributes', () => {
    const html = renderToStaticMarkup(
      <ExampleWrapper aria-label="Examples">
        <span>Preview</span>
      </ExampleWrapper>
    )

    expect(html).toContain('data-slot="example-wrapper"')
    expect(html).toContain('aria-label="Examples"')
    expect(html).toContain('<span>Preview</span>')
  })
})
