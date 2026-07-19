import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { TOTPQRCode } from './totp-qr-code'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

const renderers: ReactTestRenderer[] = []
const originalSetTimeout = globalThis.setTimeout

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  globalThis.setTimeout = originalSetTimeout
})

function render() {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<TOTPQRCode secret="SECRET123" qrCode="data:image/png;base64,qr" />)
  })
  renderers.push(renderer!)
  return renderer!
}

describe('TOTPQRCode', () => {
  test('shows the QR code and toggles manual entry', () => {
    const renderer = render()

    expect(renderer.root.findByType('img').props).toMatchObject({
      src: 'data:image/png;base64,qr',
      alt: 'TOTP QR Code',
    })
    expect(renderer.root.findAllByProps({ id: 'secret' })).toHaveLength(0)

    act(() => renderer.root.findByType('button').props.onClick())

    expect(renderer.root.findByProps({ id: 'secret' }).props).toMatchObject({
      value: 'SECRET123',
      readOnly: true,
    })
  })

  test('copies the secret and reports success', async () => {
    const writeText = mock(() => Promise.resolve())
    Object.assign(globalThis, { navigator: { clipboard: { writeText } } })
    const renderer = render()
    act(() => renderer.root.findByType('button').props.onClick())

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())

    expect(writeText).toHaveBeenCalledWith('SECRET123')
    expect(JSON.stringify(renderer.toJSON())).toContain('setupStep2CodeCopied')
  })

  test('resets the copy confirmation after two seconds', async () => {
    let resetCopied: (() => void) | undefined
    globalThis.setTimeout = ((callback: () => void) => {
      resetCopied = callback
      return 0 as unknown as ReturnType<typeof setTimeout>
    }) as typeof setTimeout
    const writeText = mock(() => Promise.resolve())
    Object.assign(globalThis, { navigator: { clipboard: { writeText } } })
    const renderer = render()
    act(() => renderer.root.findByType('button').props.onClick())

    await act(async () => renderer.root.findAllByType('button')[1].props.onClick())
    act(() => resetCopied?.())

    expect(JSON.stringify(renderer.toJSON())).not.toContain('setupStep2CodeCopied')
  })
})
