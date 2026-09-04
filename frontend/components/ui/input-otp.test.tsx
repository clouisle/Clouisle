import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create } from '@/test-utils/rtl-renderer'

let slots: Array<{ char?: string; hasFakeCaret?: boolean; isActive?: boolean }> = []

function OTPInput({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
  return React.createElement('otp-input', props, children)
}

const OTPInputContext = React.createContext<{ slots: typeof slots } | null>(null)

mock.module('input-otp', () => ({ OTPInput, OTPInputContext }))

const { InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator } = await import('./input-otp')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

describe('InputOTP primitives', () => {
  test('forwards input and group classes', () => {
    let renderer!: ReturnType<typeof create>

    act(() => {
      renderer = create(
        <InputOTP className="custom-input" containerClassName="custom-container" maxLength={6}>
          <InputOTPGroup className="custom-group" />
        </InputOTP>,
      )
    })

    const input = renderer.root.findByType('otp-input')
    expect(input.props.spellCheck).toBe(false)
    expect(input.props.maxLength).toBe(6)
    expect(input.props.className).toContain('custom-input')
    expect(input.props.containerClassName).toContain('custom-container')
    expect(renderer.root.findByProps({ 'data-slot': 'input-otp-group' }).props.className).toContain('custom-group')
  })

  test('renders slot state, caret, fallback, and separator', () => {
    slots = [{ char: '7', hasFakeCaret: true, isActive: true }]
    let active!: ReturnType<typeof create>
    let fallback!: ReturnType<typeof create>

    act(() => {
      active = create(
        <OTPInputContext.Provider value={{ slots }}>
          <InputOTPSlot index={0} className="custom-slot" />
          <InputOTPSeparator data-testid="separator" />
        </OTPInputContext.Provider>,
      )
      fallback = create(<InputOTPSlot index={5} />)
    })

    const slot = active.root.findByProps({ 'data-slot': 'input-otp-slot' })
    expect(slot.props['data-active']).toBe(true)
    expect(slot.props.className).toContain('custom-slot')
    expect(slot.children[0]).toBe('7')
    expect(active.root.findAll((node) => typeof node.props?.className === 'string' && node.props.className.includes('animate-caret-blink'))).toHaveLength(1)
    expect(active.root.findByProps({ 'data-slot': 'input-otp-separator' }).props.role).toBe('separator')
    expect(fallback.root.findByProps({ 'data-slot': 'input-otp-slot' }).props['data-active']).toBeUndefined()
  })
})
