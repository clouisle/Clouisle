"use client"

import * as React from "react"
import { CheckIcon, CopyIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type CodeBlockVariant = "default" | "destructive"
type CodeBlockSize = "default" | "sm"

type CodeBlockProps = React.ComponentProps<"div"> & {
  variant?: CodeBlockVariant
  size?: CodeBlockSize
}

function CodeBlock({
  className,
  variant = "default",
  size = "default",
  ...props
}: CodeBlockProps) {
  return (
    <div
      data-slot="code-block"
      data-variant={variant}
      data-size={size}
      className={cn(
        "group/code-block relative w-full min-w-0 overflow-hidden rounded-md border bg-background text-foreground",
        size === "sm" && "text-xs",
        variant === "destructive" && "border-destructive/40",
        className
      )}
      {...props}
    />
  )
}

function CodeBlockHeader({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="code-block-header"
      className={cn(
        "flex h-10 min-w-0 items-center justify-between gap-3 border-b bg-muted/40 px-3 text-xs",
        className
      )}
      {...props}
    />
  )
}

function CodeBlockTitle({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="code-block-title"
      className={cn("flex min-w-0 items-center gap-2 truncate font-medium", className)}
      {...props}
    />
  )
}

function CodeBlockActions({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="code-block-actions"
      className={cn(
        "flex shrink-0 items-center gap-1",
        "group-has-[[data-slot=code-block-header]]/code-block:static group-has-[[data-slot=code-block-header]]/code-block:ml-auto",
        "absolute top-1.5 right-1.5 z-10 opacity-0 transition-opacity group-hover/code-block:opacity-100 focus-within:opacity-100",
        "supports-hover:[@media(hover:none)]:opacity-100",
        className
      )}
      {...props}
    />
  )
}

type CodeBlockContentProps = React.ComponentProps<"pre"> & {
  wrap?: boolean
  lineNumbers?: boolean
  startLine?: number
}

function CodeBlockContent({
  className,
  wrap = false,
  lineNumbers = false,
  startLine = 1,
  children,
  ...props
}: CodeBlockContentProps) {
  const content =
    lineNumbers && typeof children === "string"
      ? children.split("\n").map((line, index) => (
          <CodeBlockLine key={index}>
            <span aria-hidden="true" className="mr-4 inline-block min-w-8 select-none text-right text-muted-foreground">
              {startLine + index}
            </span>
            {line || " "}
          </CodeBlockLine>
        ))
      : children

  return (
    <pre
      data-slot="code-block-content"
      dir="ltr"
      tabIndex={0}
      className={cn(
        "max-w-full overflow-auto p-4 font-mono text-sm leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        wrap ? "whitespace-pre-wrap break-words scroll-fade-y" : "whitespace-pre",
        className
      )}
      {...props}
    >
      {content}
    </pre>
  )
}

type CodeBlockLineProps = React.ComponentProps<"span"> & {
  variant?: "default" | "added" | "removed" | "highlighted"
}

function CodeBlockLine({
  className,
  variant = "default",
  ...props
}: CodeBlockLineProps) {
  return (
    <span
      data-slot="code-block-line"
      data-variant={variant}
      className={cn(
        "block min-h-[1lh]",
        variant === "added" && "bg-emerald-500/10 before:mr-2 before:text-emerald-700 before:content-['+'] dark:before:text-emerald-400",
        variant === "removed" && "bg-destructive/10 before:mr-2 before:text-destructive before:content-['−']",
        variant === "highlighted" && "bg-muted/80",
        className
      )}
      {...props}
    />
  )
}

function CodeBlockFooter({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="code-block-footer"
      className={cn("flex items-center gap-2 border-t px-3 py-2", className)}
      {...props}
    />
  )
}

type CodeBlockCopyButtonProps = Omit<
  React.ComponentProps<typeof Button>,
  "onCopy" | "onError"
> & {
  value?: string
  onCopy?: () => void
  onError?: (error: Error) => void
  timeout?: number
}

function CodeBlockCopyButton({
  value = "",
  onCopy,
  onError,
  timeout = 2000,
  children,
  className,
  ...props
}: CodeBlockCopyButtonProps) {
  const [isCopied, setIsCopied] = React.useState(false)
  const timeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(
    () => () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
    },
    []
  )

  const copyToClipboard = async () => {
    if (typeof window === "undefined" || !navigator?.clipboard?.writeText) {
      onError?.(new Error("Clipboard API not available"))
      return
    }

    try {
      await navigator.clipboard.writeText(value)
      setIsCopied(true)
      onCopy?.()
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => setIsCopied(false), timeout)
    } catch (error) {
      onError?.(error instanceof Error ? error : new Error(String(error)))
    }
  }

  const Icon = isCopied ? CheckIcon : CopyIcon

  return (
    <Button
      data-slot="code-block-copy-button"
      aria-label="Copy code"
      className={cn("shrink-0", className)}
      onClick={copyToClipboard}
      size="icon"
      variant="ghost"
      {...props}
    >
      {children ?? <Icon size={14} />}
      <span aria-live="polite" className="sr-only">
        {isCopied ? "Copied" : ""}
      </span>
    </Button>
  )
}

export {
  CodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton,
  CodeBlockFooter,
  CodeBlockHeader,
  CodeBlockLine,
  CodeBlockTitle,
}
