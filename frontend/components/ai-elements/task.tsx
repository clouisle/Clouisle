"use client";
import { cn } from "@/lib/utils";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import {
  CheckCircleIcon,
  CircleIcon,
  Loader2Icon,
  type LucideIcon,
} from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { createContext, memo, useContext, useState, Children } from "react";

export type TaskState = "pending" | "running" | "completed" | "error";

// Task Context
type TaskContextValue = {
  state: TaskState;
  hasContent: boolean;
};

const TaskContext = createContext<TaskContextValue | null>(null);

export const useTask = () => {
  const context = useContext(TaskContext);
  if (!context) {
    throw new Error("useTask must be used within a Task component");
  }
  return context;
};

// Task Container
export type TaskProps = Omit<ComponentProps<typeof TraceCollapsible>, "open" | "defaultOpen" | "onOpenChange"> & {
  state?: TaskState;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export const Task = memo(
  ({ className, state = "pending", open: openProp, defaultOpen = false, onOpenChange, children, ...props }: TaskProps) => {
    const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
    const isOpen = openProp ?? uncontrolledOpen;
    const setIsOpen = (nextOpen: boolean) => {
      if (openProp === undefined) setUncontrolledOpen(nextOpen);
      onOpenChange?.(nextOpen);
    };

    // Check if there's a TaskContent child
    const hasContent = Children.toArray(children).some(
      (child) =>
        typeof child === "object" &&
        child !== null &&
        "type" in child &&
        (child.type as { displayName?: string }).displayName === "TaskContent"
    );

    return (
      <TaskContext.Provider value={{ state, hasContent }}>
        <Trace className={cn("not-prose", className)} {...props}>
          <TraceCollapsible open={isOpen} onOpenChange={setIsOpen}>
            {children}
          </TraceCollapsible>
        </Trace>
      </TaskContext.Provider>
    );
  }
);
Task.displayName = "Task";

// Task Header/Trigger
export type TaskTriggerProps = Omit<ComponentProps<typeof TraceCollapsibleTrigger>, 'asChild'> & {
  icon?: LucideIcon;
  title: string;
  description?: string;
};

const stateIcons: Record<TaskState, ReactNode> = {
  pending: <CircleIcon className="size-3 text-muted-foreground" />,
  running: <Loader2Icon className="size-3 text-primary animate-spin" />,
  completed: <CheckCircleIcon className="size-3 text-green-600" />,
  error: <CheckCircleIcon className="size-3 text-destructive" />,
};

export const TaskTrigger = memo(
  ({
    className,
    icon: Icon,
    title,
    description,
    ...props
  }: TaskTriggerProps) => {
    const { state, hasContent } = useTask();

    const content = (
      <TraceLine status={state === "running" ? "running" : state === "error" ? "error" : state === "pending" ? "pending" : undefined}>
        <TraceIcon>{stateIcons[state]}</TraceIcon>
        {Icon && <TraceIcon><Icon className="size-3" /></TraceIcon>}
        <TraceTitle>{title}</TraceTitle>
        {description && <span className="text-muted-foreground/70">{description}</span>}
      </TraceLine>
    );

    if (!hasContent) {
      return (
        <div className={cn("flex items-center gap-2 py-1 text-xs text-muted-foreground", className)}>
          {content}
        </div>
      );
    }

    return (
      <TraceCollapsibleTrigger className={cn("py-1 text-xs", className)} {...props}>
        {content}
      </TraceCollapsibleTrigger>
    );
  }
);
TaskTrigger.displayName = "TaskTrigger";

// Task Content
export type TaskContentProps = ComponentProps<typeof TraceCollapsibleContent>;

export const TaskContent = memo(
  ({ className, children, ...props }: TaskContentProps) => (
    <TraceCollapsibleContent
      forceMount
      className={cn("py-1 pl-5 text-xs text-muted-foreground", className)}
      {...props}
    >
      <Trace><TraceLine><TraceTitle>{children}</TraceTitle></TraceLine></Trace>
    </TraceCollapsibleContent>
  )
);
TaskContent.displayName = "TaskContent";

// Task List Container
export type TaskListProps = ComponentProps<"div">;

export const TaskList = memo(({ className, children, ...props }: TaskListProps) => (
  <Trace className={cn("space-y-0.5 mb-3", className)} {...props}>
    {children}
  </Trace>
));
TaskList.displayName = "TaskList";
