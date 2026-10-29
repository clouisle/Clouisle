"use client";

import { useControllableState } from "@radix-ui/react-use-controllable-state";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceDescription,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import { cn } from "@/lib/utils";
import { BrainIcon, Loader2Icon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { createContext, memo, useContext, useEffect, useState, useRef, Children, isValidElement } from "react";
import { Streamdown } from "streamdown";
type ReasoningContextValue = {
  isStreaming: boolean;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  duration: number | undefined;
};

const ReasoningContext = createContext<ReasoningContextValue | null>(null);

export const useReasoning = () => {
  const context = useContext(ReasoningContext);
  if (!context) {
    throw new Error("Reasoning components must be used within Reasoning");
  }
  return context;
};

export type ReasoningProps = Omit<ComponentProps<typeof TraceCollapsible>, "open" | "defaultOpen" | "onOpenChange"> & {
  isStreaming?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  duration?: number;
};

const AUTO_CLOSE_DELAY = 1000;
const MS_IN_S = 1000;

export const Reasoning = memo(
  ({
    className,
    isStreaming = false,
    open,
    defaultOpen = true,
    onOpenChange,
    duration: durationProp,
    children,
    ...props
  }: ReasoningProps) => {
    const [isOpen, setIsOpen] = useControllableState({
      prop: open,
      defaultProp: defaultOpen,
      onChange: onOpenChange,
    });
    const [duration, setDuration] = useControllableState({
      prop: durationProp,
      defaultProp: undefined,
    });

    const [hasAutoClosed, setHasAutoClosed] = useState(false);
    const startTimeRef = useRef<number | null>(null);

    // Track duration when streaming starts and ends
    useEffect(() => {
      if (isStreaming) {
        if (startTimeRef.current === null) {
          startTimeRef.current = Date.now();
        }
        setIsOpen(true);
      } else if (startTimeRef.current !== null) {
        setDuration(Math.ceil((Date.now() - startTimeRef.current) / MS_IN_S));
        startTimeRef.current = null;
      }
    }, [isStreaming, setDuration, setIsOpen]);

    // Auto-open when streaming starts, auto-close when streaming ends (once only)
    useEffect(() => {
      if (defaultOpen && !isStreaming && isOpen && !hasAutoClosed) {
        const timer = setTimeout(() => {
          setIsOpen(false);
          setHasAutoClosed(true);
        }, AUTO_CLOSE_DELAY);
        return () => clearTimeout(timer);
      }
    }, [isStreaming, isOpen, defaultOpen, setIsOpen, hasAutoClosed]);
    return (
      <ReasoningContext.Provider value={{ isStreaming, isOpen, setIsOpen, duration }}>
        <Trace className={cn("not-prose mb-4", className)} {...props}>
          <TraceCollapsible open={isOpen} onOpenChange={setIsOpen}>
            {children}
          </TraceCollapsible>
        </Trace>
      </ReasoningContext.Provider>
    );
  }
);

export type ReasoningTriggerProps = ComponentProps<typeof TraceCollapsibleTrigger> & {
  getThinkingMessage?: (isStreaming: boolean, duration?: number) => ReactNode;
};

const defaultGetThinkingMessage = (isStreaming: boolean, duration?: number) => {
  if (isStreaming || duration === 0) return "Thinking...";
  if (duration === undefined) return "Thought for a few seconds";
  return `Thought for ${duration} seconds`;
};

export const ReasoningTrigger = memo(
  ({ className, children, getThinkingMessage = defaultGetThinkingMessage, ...props }: ReasoningTriggerProps) => {
    const { isStreaming, duration } = useReasoning();
    return (
      <TraceCollapsibleTrigger
        className={cn(
          "flex w-full items-center gap-2 text-muted-foreground text-sm transition-colors hover:text-foreground",
          className
        )}
        {...props}
      >
        {children ?? (
          <TraceLine status={isStreaming ? "running" : undefined}>
            <TraceIcon>{isStreaming ? <Loader2Icon className="size-4 animate-spin" /> : <BrainIcon className="size-4" />}</TraceIcon>
            <TraceTitle>{getThinkingMessage(isStreaming, duration)}</TraceTitle>
            {duration !== undefined && !isStreaming && <TraceDescription>{duration}s</TraceDescription>}
          </TraceLine>
        )}
      </TraceCollapsibleTrigger>
    );
  }
);

export type ReasoningContentProps = ComponentProps<typeof TraceCollapsibleContent> & {
  children: string;
};

export const ReasoningContent = memo(
  ({ className, children, ...props }: ReasoningContentProps) => (
    <TraceCollapsibleContent
      forceMount
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    >
      <Streamdown
        components={{
          // Use div instead of p when paragraph contains block elements (like images)
          // This prevents React hydration error: <div> cannot be a descendant of <p>
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          p: ({ children: pChildren, node, ...pProps }: any) => {
            const hasImgInNode = node?.children?.some(
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (child: any) => child.tagName === 'img'
            )
            const hasBlockElements = Children.toArray(pChildren).some(
              (child) =>
                isValidElement(child) &&
                (child.type === 'div' || child.type === 'img' || typeof child.type === 'function')
            )
            if (hasImgInNode || hasBlockElements) {
              return <div className="my-4" {...pProps}>{pChildren}</div>
            }
            return <p {...pProps}>{pChildren}</p>
          },
        }}
      >
        {children}
      </Streamdown>
    </TraceCollapsibleContent>
  )
);

Reasoning.displayName = "Reasoning";
ReasoningTrigger.displayName = "ReasoningTrigger";
ReasoningContent.displayName = "ReasoningContent";
