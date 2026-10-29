"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import { cn } from "@/lib/utils";
import {
  BrainIcon,
  CheckCircleIcon,
  CircleIcon,
  Loader2Icon,
  type LucideIcon,
} from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { createContext, memo, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";

// Chain of Thought Context
type ChainOfThoughtContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  isStreaming: boolean;
  contentId: string;
};

const ChainOfThoughtContext = createContext<ChainOfThoughtContextValue | null>(null);

export const useChainOfThought = () => {
  const context = useContext(ChainOfThoughtContext);
  if (!context) {
    throw new Error("ChainOfThought components must be used within ChainOfThought");
  }
  return context;
};

// Main Container
export type ChainOfThoughtProps = ComponentProps<"div"> & {
  isStreaming?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const AUTO_CLOSE_DELAY = 3000;

export const ChainOfThought = memo(
  ({
    className,
    isStreaming = false,
    open,
    defaultOpen = true,
    onOpenChange,
    children,
    ...props
  }: ChainOfThoughtProps) => {
    const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
    const contentId = useId();
    const isOpen = open ?? uncontrolledOpen;
    const setIsOpen = useCallback((nextOpen: boolean) => {
      if (open === undefined) setUncontrolledOpen(nextOpen);
      onOpenChange?.(nextOpen);
    }, [open, onOpenChange]);

    const [hasAutoClosed, setHasAutoClosed] = useState(false);
    const contextValue = useMemo(
      () => ({ isOpen, setIsOpen, isStreaming, contentId }),
      [isOpen, setIsOpen, isStreaming, contentId]
    );

    // Auto-close when streaming ends (once only)
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
      <ChainOfThoughtContext.Provider value={contextValue}>
        <Trace
          className={cn("not-prose w-full", className)}
          data-state={isOpen ? "open" : "closed"}
          {...props}
        >
          <TraceCollapsible open={isOpen} onOpenChange={setIsOpen}>
            {children}
          </TraceCollapsible>
        </Trace>
      </ChainOfThoughtContext.Provider>
    );
  }
);
ChainOfThought.displayName = "ChainOfThought";

// Header with collapsible trigger
export type ChainOfThoughtHeaderProps = ComponentProps<"button"> & {
  title?: string;
  icon?: LucideIcon;
};

export const ChainOfThoughtHeader = memo(
  ({
    className,
    title,
    icon: Icon = BrainIcon,
    children,
    ...props
  }: ChainOfThoughtHeaderProps) => {
    const { isOpen, isStreaming, contentId } = useChainOfThought();
    const t = useTranslations('chat.reasoning');

    return (
      <TraceCollapsibleTrigger
        className={cn(
          "group flex w-full items-center gap-2 text-muted-foreground text-sm transition-colors hover:text-foreground",
          className
        )}
        aria-expanded={isOpen}
        aria-controls={contentId}
        {...props}
      >
        <TraceLine status={isStreaming ? "running" : undefined}>
          <TraceIcon><Icon /></TraceIcon>
          <TraceTitle>{children ?? title ?? (isStreaming ? t('thinkingDefault') : t('thoughtDefault'))}</TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
    );
  }
);
ChainOfThoughtHeader.displayName = "ChainOfThoughtHeader";

// Content container
export type ChainOfThoughtContentProps = ComponentProps<"div"> & {
  containScroll?: boolean;
};

export const ChainOfThoughtContent = memo(
  ({ className, children, containScroll = false, onWheel, ...props }: ChainOfThoughtContentProps) => {
    const { isOpen, contentId } = useChainOfThought();
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
      const element = ref.current;
      if (!element || !containScroll) {
        return;
      }

      const handleNativeWheel = (event: WheelEvent) => {
        const canScrollUp = element.scrollTop > 0.5;
        const canScrollDown = element.scrollHeight - element.scrollTop - element.clientHeight > 1;

        if ((event.deltaY < 0 && canScrollUp) || (event.deltaY > 0 && canScrollDown)) {
          event.stopPropagation();
        }
      };

      element.addEventListener("wheel", handleNativeWheel, { passive: true });
      return () => {
        element.removeEventListener("wheel", handleNativeWheel);
      };
    }, [containScroll]);

    return (
      <TraceCollapsibleContent forceMount>
        <div
          id={contentId}
          ref={ref}
          data-state={isOpen ? "open" : "closed"}
          className={cn(
            "mt-3 mb-0 ml-0 space-y-2 border-0 p-0 text-sm leading-normal text-muted-foreground outline-none",
            !isOpen && "hidden",
            className
          )}
          onWheel={onWheel}
          {...props}
        >
          <Trace>{children}</Trace>
        </div>
      </TraceCollapsibleContent>
    );
  }
);
ChainOfThoughtContent.displayName = "ChainOfThoughtContent";

// Step status
export type StepStatus = "pending" | "active" | "complete" | "error";

// Single step
export type ChainOfThoughtStepProps = ComponentProps<"div"> & {
  icon?: LucideIcon;
  label: string;
  status?: StepStatus;
};

const statusIcons: Record<StepStatus, ReactNode> = {
  pending: <CircleIcon className="size-3.5 text-muted-foreground/50" />,
  active: <Loader2Icon className="size-3.5 text-primary animate-spin" />,
  complete: <CheckCircleIcon className="size-3.5 text-green-600" />,
  error: <CheckCircleIcon className="size-3.5 text-destructive" />,
};

export const ChainOfThoughtStep = memo(
  ({
    className,
    icon: Icon,
    label,
    status = "pending",
    children,
    ...props
  }: ChainOfThoughtStepProps) => {
    return (
      <div className={cn("text-muted-foreground", className)} {...props}>
        <TraceLine status={status === "active" ? "running" : status === "complete" ? undefined : status}>
          <TraceIcon>{statusIcons[status]}</TraceIcon>
          {Icon && <TraceIcon><Icon className="size-3.5" /></TraceIcon>}
          <TraceTitle className="text-xs">{label}</TraceTitle>
        </TraceLine>
        {children && <div className="ml-5 mt-1.5">{children}</div>}
      </div>
    );
  }
);
ChainOfThoughtStep.displayName = "ChainOfThoughtStep";

// Search results container
export type ChainOfThoughtSearchResultsProps = ComponentProps<"div">;

export const ChainOfThoughtSearchResults = memo(
  ({ className, children, ...props }: ChainOfThoughtSearchResultsProps) => (
    <div className={cn("flex flex-wrap gap-1.5", className)} {...props}>
      {children}
    </div>
  )
);
ChainOfThoughtSearchResults.displayName = "ChainOfThoughtSearchResults";

// Single search result badge
export type ChainOfThoughtSearchResultProps = ComponentProps<"span">;

export const ChainOfThoughtSearchResult = memo(
  ({ className, children, ...props }: ChainOfThoughtSearchResultProps) => (
    <Badge className={cn("rounded-full", className)} variant="secondary" {...props}>
      {children}
    </Badge>
  )
);
ChainOfThoughtSearchResult.displayName = "ChainOfThoughtSearchResult";

// Image with caption
export type ChainOfThoughtImageProps = ComponentProps<"figure"> & {
  caption?: string;
};

export const ChainOfThoughtImage = memo(
  ({ className, caption, children, ...props }: ChainOfThoughtImageProps) => (
    <figure className={cn("space-y-1.5", className)} {...props}>
      {children}
      {caption && (
        <figcaption className="text-xs text-muted-foreground/70">
          {caption}
        </figcaption>
      )}
    </figure>
  )
);
ChainOfThoughtImage.displayName = "ChainOfThoughtImage";
