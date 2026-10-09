"use client"

import * as React from "react"
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
} from "lucide-react"
import { DayPicker, type DayButton, type ChevronProps } from "react-day-picker"

import { cn } from "@/lib/utils"
import { Button, buttonVariants } from "@/components/ui/button"

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  navLayout = "around",
  components,
  ...props
}: React.ComponentProps<typeof DayPicker>) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      navLayout={navLayout}
      className={cn(
        "w-fit max-w-full bg-background p-3 text-foreground [--cell-size:2rem] sm:[--cell-size:2.25rem]",
        className,
      )}
      classNames={{
        months: "relative flex flex-col gap-4 sm:flex-row sm:gap-6",
        month: "relative min-w-0 space-y-3",
        month_caption: "flex h-(--cell-size) items-center justify-center px-9",
        caption_label: "text-sm font-medium",
        nav: "absolute inset-x-0 top-0 flex items-center justify-between",
        button_previous: cn(
          buttonVariants({ variant: "outline", size: "icon-sm" }),
          "absolute start-0 top-0 size-(--cell-size) p-0 aria-disabled:pointer-events-none aria-disabled:opacity-50",
        ),
        button_next: cn(
          buttonVariants({ variant: "outline", size: "icon-sm" }),
          "absolute end-0 top-0 size-(--cell-size) p-0 aria-disabled:pointer-events-none aria-disabled:opacity-50",
        ),
        chevron: "size-4",
        month_grid: "w-full border-collapse",
        weekdays: "border-0",
        weekday: "h-8 w-(--cell-size) text-center text-xs font-normal text-muted-foreground",
        week: "border-0",
        day: "relative size-(--cell-size) p-0 text-center text-sm",
        day_button: "size-(--cell-size)",
        range_start: "rounded-s-md bg-accent",
        range_middle: "bg-accent",
        range_end: "rounded-e-md bg-accent",
        today: "[&:not([data-selected])>button]:bg-accent [&:not([data-selected])>button]:text-accent-foreground",
        outside: "text-muted-foreground [&:not([data-selected])]:opacity-50",
        disabled: "text-muted-foreground opacity-50",
        hidden: "invisible",
        dropdowns: "flex items-center justify-center gap-2 text-sm font-medium",
        dropdown_root: "relative rounded-md border border-input bg-background px-2 py-1 focus-within:ring-2 focus-within:ring-ring",
        dropdown: "absolute inset-0 w-full cursor-pointer opacity-0",
        week_number_header: "size-(--cell-size)",
        week_number: "size-(--cell-size) text-xs text-muted-foreground",
        footer: "pt-3 text-sm",
        ...classNames,
      }}
      components={{
        Chevron: CalendarChevron,
        DayButton: CalendarDayButton,
        ...components,
      }}
      {...props}
    />
  )
}

function CalendarChevron({
  className,
  orientation = "left",
  size = 16,
  style,
}: ChevronProps) {
  const Icon = orientation === "right"
    ? ChevronRightIcon
    : orientation === "down"
      ? ChevronDownIcon
      : orientation === "up"
        ? ChevronUpIcon
        : ChevronLeftIcon

  return <Icon aria-hidden="true" className={className} size={size} style={style} />
}

function CalendarDayButton({
  className,
  day,
  modifiers,
  ...props
}: React.ComponentProps<typeof DayButton>) {
  const ref = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    if (modifiers.focused) ref.current?.focus()
  }, [modifiers.focused])

  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      data-day={day.isoDate}
      data-selected-single={modifiers.selected && !modifiers.range_start && !modifiers.range_end && !modifiers.range_middle}
      data-range-start={modifiers.range_start}
      data-range-end={modifiers.range_end}
      data-range-middle={modifiers.range_middle}
      className={cn(
        "size-(--cell-size) rounded-md p-0 font-normal data-[selected-single=true]:bg-primary data-[selected-single=true]:text-primary-foreground data-[selected-single=true]:hover:bg-primary/80 data-[range-start=true]:bg-primary data-[range-start=true]:text-primary-foreground data-[range-start=true]:hover:bg-primary/80 data-[range-end=true]:bg-primary data-[range-end=true]:text-primary-foreground data-[range-end=true]:hover:bg-primary/80 data-[range-middle=true]:rounded-none data-[range-middle=true]:bg-accent data-[range-middle=true]:text-accent-foreground",
        className,
      )}
      {...props}
    />
  )
}

export { Calendar }
