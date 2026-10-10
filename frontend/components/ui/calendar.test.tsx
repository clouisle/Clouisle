import { expect, mock, test } from "bun:test"
import React from "react"
import type { DateRange } from "react-day-picker"
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer"
import { Calendar } from "./calendar"

globalThis.IS_REACT_ACT_ENVIRONMENT = true

test("selects and marks a complete date range through the calendar buttons", () => {
  const onSelect = mock<(range: DateRange | undefined) => void>(() => {})
  let renderer: ReactTestRenderer | undefined

  function RangeCalendar() {
    const [selected, setSelected] = React.useState<DateRange | undefined>()
    const handleSelect = (range: DateRange | undefined) => {
      onSelect(range)
      setSelected(range)
    }

    return (
      <Calendar
        mode="range"
        selected={selected}
        onSelect={handleSelect}
        defaultMonth={new Date(2026, 9, 1)}
        today={new Date(2026, 9, 1)}
      />
    )
  }

  try {
    act(() => {
      renderer = create(<RangeCalendar />)
    })

    const dayButton = (isoDate: string) => renderer!.root.findAllByProps({ "data-day": isoDate })
      .find((node) => node.type === "button")
    const clickDay = (isoDate: string) => {
      const button = dayButton(isoDate)
      expect(button).toBeDefined()
      const onClick = button!.props.onClick as (event: React.MouseEvent<HTMLButtonElement>) => void
      act(() => onClick({ preventDefault() {}, stopPropagation() {} } as React.MouseEvent<HTMLButtonElement>))
    }

    clickDay("2026-10-08")
    expect(onSelect).toHaveBeenLastCalledWith({ from: new Date(2026, 9, 8), to: new Date(2026, 9, 8) })
    expect(dayButton("2026-10-08")!.props["data-range-start"]).toBe(true)

    clickDay("2026-10-10")
    expect(onSelect).toHaveBeenLastCalledWith({ from: new Date(2026, 9, 8), to: new Date(2026, 9, 10) })
    expect(dayButton("2026-10-08")!.props["data-range-start"]).toBe(true)
    expect(dayButton("2026-10-09")!.props["data-range-middle"]).toBe(true)
    expect(dayButton("2026-10-10")!.props["data-range-end"]).toBe(true)
  } finally {
    if (renderer) act(() => renderer!.unmount())
  }
})
