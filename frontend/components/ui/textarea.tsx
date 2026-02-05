import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, rows, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      rows={rows}
      className={cn(
        "border-input dark:bg-input/30 focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:aria-invalid:border-destructive/50 rounded-md border bg-transparent px-2.5 py-2 text-base shadow-xs transition-[color,box-shadow] focus-visible:ring-[3px] aria-invalid:ring-[3px] md:text-sm placeholder:text-muted-foreground flex w-full outline-none cursor-text disabled:cursor-not-allowed disabled:opacity-50",
        // 如果没有指定 rows，使用 field-sizing-content 自动调整大小
        !rows && "field-sizing-content min-h-16",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
