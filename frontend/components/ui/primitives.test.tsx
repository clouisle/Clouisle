import { afterEach, describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { Alert, AlertAction, AlertDescription, AlertTitle } from './alert'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './card'
import { Progress } from './progress'
import { Skeleton } from './skeleton'
import { Table, TableBody, TableCaption, TableCell, TableFooter, TableHead, TableHeader, TableRow } from './table'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function render(component: React.ReactNode) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(component)
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('simple UI primitives', () => {
  test('renders alert semantics, content slots, and warning variant', () => {
    const renderer = render(
      <Alert variant="warning" aria-label="Quota warning">
        <AlertTitle>Almost full</AlertTitle>
        <AlertDescription>Only 10% remains.</AlertDescription>
        <AlertAction>Upgrade</AlertAction>
      </Alert>,
    )

    const alert = renderer.root.findByProps({ role: 'alert' })
    expect(alert.props['aria-label']).toBe('Quota warning')
    expect(alert.props.className).toContain('text-amber-600')
    expect(alert.findByProps({ 'data-slot': 'alert-title' }).children).toEqual(['Almost full'])
    expect(alert.findByProps({ 'data-slot': 'alert-description' }).children).toEqual(['Only 10% remains.'])
    expect(alert.findByProps({ 'data-slot': 'alert-action' }).children).toEqual(['Upgrade'])
  })

  test('renders a small card with all composition slots and forwarded props', () => {
    const renderer = render(
      <Card size="sm" data-testid="account-card">
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Team plan</CardDescription>
          <CardAction>Edit</CardAction>
        </CardHeader>
        <CardContent>12 members</CardContent>
        <CardFooter>Active</CardFooter>
      </Card>,
    )

    const card = renderer.root.find(node => node.type === 'div' && node.props['data-testid'] === 'account-card')
    expect(card.props['data-size']).toBe('sm')
    expect(card.findByProps({ 'data-slot': 'card-title' }).children).toEqual(['Account'])
    expect(card.findByProps({ 'data-slot': 'card-description' }).children).toEqual(['Team plan'])
    expect(card.findByProps({ 'data-slot': 'card-action' }).children).toEqual(['Edit'])
    expect(card.findByProps({ 'data-slot': 'card-content' }).children).toEqual(['12 members'])
    expect(card.findByProps({ 'data-slot': 'card-footer' }).children).toEqual(['Active'])
  })

  test('reflects progress values in accessibility state and indicator width', () => {
    const renderer = render(<Progress value={42} aria-label="Upload progress" />)

    const progress = renderer.root.find(node => node.type === 'div' && node.props['data-slot'] === 'progress')
    expect(progress.props['aria-label']).toBe('Upload progress')
    expect(progress.props['aria-valuenow']).toBe(42)
    const indicator = progress.find(node => node.type === 'div' && node.props.style?.width === '42%')
    expect(indicator.props.style.width).toBe('42%')
  })

  test('renders a customizable skeleton placeholder', () => {
    const renderer = render(<Skeleton className="h-6" aria-label="Loading profile" />)
    const skeleton = renderer.root.findByProps({ 'data-slot': 'skeleton' })

    expect(skeleton.props['aria-label']).toBe('Loading profile')
    expect(skeleton.props.className).toContain('animate-pulse')
    expect(skeleton.props.className).toContain('h-6')
  })

  test('renders native table structure and selected row state', () => {
    const renderer = render(
      <Table aria-label="Invoices">
        <TableCaption>Recent invoices</TableCaption>
        <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>Total</TableHead></TableRow></TableHeader>
        <TableBody><TableRow data-state="selected"><TableCell>#100</TableCell><TableCell>$20</TableCell></TableRow></TableBody>
        <TableFooter><TableRow><TableCell>Total</TableCell><TableCell>$20</TableCell></TableRow></TableFooter>
      </Table>,
    )

    const table = renderer.root.findByType('table')
    expect(table.props['aria-label']).toBe('Invoices')
    expect(table.findByType('caption').children).toEqual(['Recent invoices'])
    expect(table.findAllByType('thead')).toHaveLength(1)
    expect(table.findAllByType('tbody')).toHaveLength(1)
    expect(table.findAllByType('tfoot')).toHaveLength(1)
    expect(table.findAllByType('th').map(cell => cell.children[0])).toEqual(['Invoice', 'Total'])
    const selected = table.find(node => node.type === 'tr' && node.props['data-state'] === 'selected')
    expect(selected.props.className).toContain('data-[state=selected]:bg-muted')
  })
})
