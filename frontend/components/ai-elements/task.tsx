"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import {
  CheckCircleIcon,
  ChevronDownIcon,
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
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
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
export type TaskProps = ComponentProps<typeof Collapsible> & {
  state?: TaskState;
};

export const Task = memo(
  ({ className, state = "pending", children, ...props }: TaskProps) => {
    const [isOpen, setIsOpen] = useState(false);

    // Check if there's a TaskContent child
    const hasContent = Children.toArray(children).some(
      (child) =>
        typeof child === "object" &&
        child !== null &&
        "type" in child &&
        (child.type as { displayName?: string }).displayName === "TaskContent"
    );

    return (
      <TaskContext.Provider value={{ state, isOpen, setIsOpen, hasContent }}>
        <Collapsible
          className={cn("not-prose", className)}
          open={isOpen}
          onOpenChange={setIsOpen}
          {...props}
        >
          {children}
        </Collapsible>
      </TaskContext.Provider>
    );
  }
);
Task.displayName = "Task";

// Task Header/Trigger
export type TaskTriggerProps = Omit<ComponentProps<typeof CollapsibleTrigger>, 'asChild'> & {
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
    const { state, isOpen, hasContent } = useTask();

    const content = (
      <>
        {stateIcons[state]}
        {Icon && <Icon className="size-3" />}
        <span>{title}</span>
        {description && (
          <span className="text-muted-foreground/70">{description}</span>
        )}
        {hasContent && (
          <ChevronDownIcon
            className={cn(
              "size-3 ml-auto transition-transform",
              isOpen ? "rotate-180" : "rotate-0"
            )}
          />
        )}
      </>
    );

    // If no content, render as a simple div instead of a trigger
    if (!hasContent) {
      return (
        <div
          className={cn(
            "flex items-center gap-2 text-xs text-muted-foreground py-1",
            className
          )}
        >
          {content}
        </div>
      );
    }

    return (
      <CollapsibleTrigger
        className={cn(
          "flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors py-1",
          className
        )}
        {...props}
      >
        {content}
      </CollapsibleTrigger>
    );
  }
);
TaskTrigger.displayName = "TaskTrigger";

// Task Content
export type TaskContentProps = ComponentProps<typeof CollapsibleContent>;

export const TaskContent = memo(
  ({ className, ...props }: TaskContentProps) => {
    return (
      <CollapsibleContent
        className={cn(
          "text-xs text-muted-foreground pl-5 py-1",
          className
        )}
        {...props}
      />
    );
  }
);
TaskContent.displayName = "TaskContent";

// Task List Container
export type TaskListProps = ComponentProps<"div">;

export const TaskList = memo(({ className, children, ...props }: TaskListProps) => {
  return (
    <div
      className={cn("space-y-0.5 mb-3", className)}
      {...props}
    >
      {children}
    </div>
  );
});
TaskList.displayName = "TaskList";
