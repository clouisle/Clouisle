import { expect, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { TraceCollapsible, TraceCollapsibleContent } from './trace'

test('keeps force-mounted trace content hidden while closed', () => {
  const html = renderToStaticMarkup(
    <TraceCollapsible>
      <TraceCollapsibleContent forceMount>Trace details</TraceCollapsibleContent>
    </TraceCollapsible>,
  )
  expect(html).toContain('data-state="closed"')
  expect(html).toContain('data-[state=closed]:hidden')
  expect(html).toContain('Trace details')
})

test('preserves open-state trace content animation', () => {
  const html = renderToStaticMarkup(
    <TraceCollapsible open onOpenChange={() => {}}>
      <TraceCollapsibleContent>Trace details</TraceCollapsibleContent>
    </TraceCollapsible>,
  )
  expect(html).toContain('data-state="open"')
  expect(html).toContain('data-[state=open]:animate-in')
  expect(html).toContain('Trace details')
})
