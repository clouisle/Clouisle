import { describe, expect, test } from 'bun:test'
import React from 'react'
import { act, create } from 'react-test-renderer'

import { Dialog, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from './dialog'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('Dialog', () => {
  test('renders an accessible trigger and labelled content slots', () => {
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(
        <Dialog>
          <DialogTrigger aria-label="Open settings">Open settings</DialogTrigger>
          <DialogHeader>
            <DialogTitle>Settings</DialogTitle>
            <DialogDescription>Manage application preferences.</DialogDescription>
          </DialogHeader>
        </Dialog>,
      )
    })

    const trigger = renderer.root.findByProps({ 'data-slot': 'dialog-trigger' })
    expect(trigger.props['aria-label']).toBe('Open settings')
    expect(trigger.props.className).toContain('cursor-pointer')
    expect(renderer.root.findByProps({ 'data-slot': 'dialog-header' }).children).toHaveLength(2)
    expect(JSON.stringify(renderer.toJSON())).toContain('Settings')
    expect(JSON.stringify(renderer.toJSON())).toContain('Manage application preferences.')

    act(() => renderer.unmount())
  })
})
