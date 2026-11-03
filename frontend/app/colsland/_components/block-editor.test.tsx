import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { within } from '@testing-library/react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import platformMessages from '@/i18n/en/platform.json'
import { BlockEditor } from './block-editor'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
let renderer: ReactTestRenderer | undefined

afterEach(() => { if (renderer) act(() => renderer!.unmount()); renderer = undefined })

describe('Colsland block editor', () => {
  test('edits blocks, switches types, creates and deletes without implying persistence', async () => {
    await act(async () => { renderer = create(<NextIntlClientProvider locale="en" timeZone="UTC" messages={platformMessages}><BlockEditor /></NextIntlClientProvider>) })
    const screen = within(document.body)
    expect(screen.getByText('Not saved · refresh or leaving this page will discard changes')).toBeTruthy()
    const title = renderer!.root.findByProps({ 'aria-label': 'Document title' })
    await act(async () => { title.props.onChange({ target: { value: 'Project notes' } }) })
    await act(async () => { renderer!.root.findByProps({ 'aria-label': 'Text' }).props.onChange({ target: { value: 'First block' } }) })
    const enterPreventDefault = mock(() => {})
    await act(async () => { renderer!.root.findByProps({ 'aria-label': 'Text' }).props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false }, preventDefault: enterPreventDefault }) })
    expect(enterPreventDefault).not.toHaveBeenCalled()
    await act(async () => { renderer!.root.findByProps({ 'aria-label': 'Text' }).props.onKeyDown({ key: 'Enter', shiftKey: true, nativeEvent: { isComposing: false }, currentTarget: { selectionStart: 11, selectionEnd: 11 }, preventDefault: () => {} }) })
    expect(screen.getAllByLabelText('Text')).toHaveLength(2)
    const blockActions = renderer!.root.findAllByType('button').filter(node => node.props['aria-label'] === 'Block actions')
    expect(blockActions[0].props.className).toContain('opacity-0')
    expect(renderer!.root.findAll(node => node.type === 'div' && String(node.props.className).includes('absolute right-full top-1'))).toHaveLength(2)
    expect(renderer!.root.findAll(node => node.type === 'div' && String(node.props.className).includes('focus-within:border-border')).every(node => String(node.props.className).includes('mx-2') && !node.findAllByType('button').length)).toBe(true)
    await act(async () => { renderer!.root.findAllByType('button').filter(node => node.props['aria-label'] === 'Block actions')[1].props.onClick() })
    await act(async () => { renderer!.root.findAllByProps({ role: 'menuitem' })[4].props.onClick() })
    await act(async () => { renderer!.root.findByProps({ 'aria-label': 'Toggle to-do' }).props.onChange({ target: { checked: true } }) })
    expect((screen.getByLabelText('Toggle to-do') as HTMLInputElement).checked).toBe(true)
    await act(async () => { renderer!.root.findAllByType('button').filter(node => node.props['aria-label'] === 'Block actions')[1].props.onClick() })
    await act(async () => { renderer!.root.findAllByProps({ role: 'menuitem' })[5].props.onClick() })
    expect(screen.getAllByLabelText('Text')).toHaveLength(1)
    expect((screen.getByLabelText('Text') as HTMLTextAreaElement).value).toBe('First block')
  })
})
