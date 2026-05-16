"use client"

import * as React from "react"
import { Input } from "./input"

interface NumberInputProps extends Omit<React.ComponentProps<typeof Input>, 'value' | 'onChange' | 'type'> {
  value: number | ''
  onChange: (value: number | '') => void
  min?: number
  max?: number
}

/**
 * NumberInput component that allows empty values
 *
 * Unlike standard number inputs, this component:
 * - Allows the input to be completely cleared (empty string)
 * - Only updates the value when a valid number is entered
 * - Prevents the browser from auto-filling max/min values when empty
 */
function NumberInput({ value, onChange, min, max, ...props }: NumberInputProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const inputValue = e.target.value

    // Allow empty string
    if (inputValue === '') {
      onChange('')
      return
    }

    // Parse and validate number
    const parsed = parseInt(inputValue, 10)
    if (!Number.isNaN(parsed)) {
      onChange(parsed)
    }
  }

  return (
    <Input
      type="number"
      value={value}
      onChange={handleChange}
      min={min}
      max={max}
      {...props}
    />
  )
}

export { NumberInput }
export type { NumberInputProps }
