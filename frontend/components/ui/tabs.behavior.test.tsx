import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs'

describe('Tabs', () => {
  test('exposes the selected panel and hides inactive panel', () => {
    const markup = renderToStaticMarkup(
      <Tabs defaultValue="details" orientation="vertical">
        <TabsList variant="line" aria-label="Settings sections">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
        </TabsList>
        <TabsContent value="details">Details panel</TabsContent>
        <TabsContent value="permissions">Permissions panel</TabsContent>
      </Tabs>
    )

    expect(markup).toContain('role="tablist"')
    expect(markup).toContain('aria-label="Settings sections"')
    expect(markup).toContain('role="tab"')
    expect(markup).toContain('aria-selected="true"')
    expect(markup).toContain('>Details panel</div>')
    expect(markup).not.toContain('Permissions panel')
    expect(markup).toContain('data-orientation="vertical"')
    expect(markup).toContain('data-variant="line"')
  })
})
