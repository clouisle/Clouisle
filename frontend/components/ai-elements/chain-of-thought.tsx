"use client";

import { useControllableState } from "@radix-ui/react-use-controllable-state";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import {
  BrainIcon,
  ChevronDownIcon,
  CheckCircleIcon,
  CircleIcon,
  Loader2Icon,
  type LucideIcon,
} from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { createContext, memo, useContext, useEffect, useState } from "react";
import { Shimmer } from "./shimmer";

// Chain of Thought Context
type ChainOfThoughtContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  isStreaming: boolean;
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
export type ChainOfThoughtProps = ComponentProps<typeof Collapsible> & {
  isStreaming?: boolean;
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
    const [isOpen, setIsOpen] = useControllableState({
      prop: open,
      defaultProp: defaultOpen,
      onChange: onOpenChange,
    });

    const [hasAutoClosed, setHasAutoClosed] = useState(false);

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
      <ChainOfThoughtContext.Provider value={{ isOpen, setIsOpen, isStreaming }}>
        <Collapsible
          className={cn("not-prose mb-4 w-full", className)}
          open={isOpen}
          onOpenChange={setIsOpen}
          {...props}
        >
          {children}
        </Collapsible>
      </ChainOfThoughtContext.Provider>
    );
  }
);
ChainOfThought.displayName = "ChainOfThought";

// Header with collapsible trigger
export type ChainOfThoughtHeaderProps = ComponentProps<typeof CollapsibleTrigger> & {
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
    const { isOpen, isStreaming } = useChainOfThought();

    return (
      <CollapsibleTrigger
        className={cn(
          "flex w-full items-center gap-2 text-muted-foreground text-sm transition-colors hover:text-foreground",
          className
        )}
        {...props}
      >
        <Icon className="size-4" />
        {children ?? (
          isStreaming ? (
            <Shimmer duration={1}>{title ?? "思考中..."}</Shimmer>
          ) : (
            <span>{title ?? "思考过程"}</span>
          )
        )}
        <ChevronDownIcon
          className={cn(
            "size-4 ml-auto transition-transform",
            isOpen ? "rotate-180" : "rotate-0"
          )}
        />
      </CollapsibleTrigger>
    );
  }
);
ChainOfThoughtHeader.displayName = "ChainOfThoughtHeader";

// Content container
export type ChainOfThoughtContentProps = ComponentProps<typeof CollapsibleContent>;

export const ChainOfThoughtContent = memo(
  ({ className, children, ...props }: ChainOfThoughtContentProps) => (
    <CollapsibleContent
      className={cn(
        "mt-3 space-y-2 text-sm",
        "data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 outline-none data-[state=closed]:animate-out data-[state=open]:animate-in",
        className
      )}
      {...props}
    >
      {children}
    </CollapsibleContent>
  )
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
        <div className="flex items-center gap-2">
          {statusIcons[status]}
          {Icon && <Icon className="size-3.5" />}
          <span className="text-xs">{label}</span>
        </div>
        {children && (
          <div className="ml-5 mt-1.5">
            {children}
          </div>
        )}
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
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-xs rounded-full",
        "bg-muted text-muted-foreground",
        className
      )}
      {...props}
    >
      {children}
    </span>
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
