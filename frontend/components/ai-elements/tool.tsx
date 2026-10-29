"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CodeBlock, CodeBlockContent } from "@/components/ui/code-block";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import type { ToolUIPart } from "ai";
import { useTranslations } from "next-intl";
import { CheckCircleIcon, CircleIcon, ClockIcon, WrenchIcon, XCircleIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { createContext, isValidElement, useCallback, useContext, useId, useMemo, useState } from "react";

export type ToolProps = ComponentProps<"div"> & {
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};
export type ToolPart = ToolUIPart;

type ToolContextValue = {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  contentId: string;
};

const ToolContext = createContext<ToolContextValue | null>(null);

function useToolContext() {
  const context = useContext(ToolContext);
  if (!context) {
    throw new Error("Tool components must be used within Tool");
  }
  return context;
}

export const Tool = ({ className, defaultOpen = false, open, onOpenChange, children, ...props }: ToolProps) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const contentId = useId();
  const isOpen = open ?? uncontrolledOpen;
  const setIsOpen = useCallback((nextOpen: boolean) => {
    if (open === undefined) setUncontrolledOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }, [open, onOpenChange]);
  const contextValue = useMemo(() => ({ isOpen, setIsOpen, contentId }), [isOpen, setIsOpen, contentId]);

  return (
    <ToolContext.Provider value={contextValue}>
      <Trace className={cn("not-prose mb-4 w-full rounded-md border", className)} data-state={isOpen ? "open" : "closed"} {...props}>
        <TraceCollapsible open={isOpen} onOpenChange={setIsOpen}>
          {children}
        </TraceCollapsible>
      </Trace>
    </ToolContext.Provider>
  );
};

export type ToolHeaderProps = {
  title?: string;
  type: ToolUIPart["type"];
  state: ToolUIPart["state"];
  className?: string;
};

export const getStatusBadge = (
  status: ToolUIPart["state"],
  t: (key: string) => string
) => {
  const labels: Record<ToolUIPart["state"], string> = {
    "input-streaming": t("pending"),
    "input-available": t("running"),
    "approval-requested": t("awaitingApproval"),
    "approval-responded": t("responded"),
    "output-available": t("completed"),
    "output-error": t("error"),
    "output-denied": t("denied"),
  };
  const icons: Record<ToolUIPart["state"], ReactNode> = {
    "input-streaming": <CircleIcon className="size-4" />,
    "input-available": <ClockIcon className="size-4 animate-pulse" />,
    "approval-requested": <ClockIcon className="size-4 text-yellow-600" />,
    "approval-responded": <CheckCircleIcon className="size-4 text-blue-600" />,
    "output-available": <CheckCircleIcon className="size-4 text-green-600" />,
    "output-error": <XCircleIcon className="size-4 text-red-600" />,
    "output-denied": <XCircleIcon className="size-4 text-orange-600" />,
  };
  return <Badge className="gap-1.5 rounded-full text-xs" variant="secondary">{icons[status]}{labels[status]}</Badge>;
};

export const ToolHeader = ({ className, title, type, state, ...props }: ToolHeaderProps) => {
  const t = useTranslations("chat.tool");
  const { isOpen, contentId } = useToolContext();
  const running = state === "input-streaming" || state === "input-available";
  const failed = state === "output-error" || state === "output-denied";
  const statusLabels: Record<ToolUIPart["state"], string> = {
    "input-streaming": t("running"),
    "input-available": t("running"),
    "approval-requested": t("awaitingApproval"),
    "approval-responded": t("responded"),
    "output-available": t("completed"),
    "output-error": t("error"),
    "output-denied": t("denied"),
  };
  const text = `${statusLabels[state]}: ${title ?? type.split("-").slice(1).join("-")}`;

  return (
    <TraceCollapsibleTrigger
      className={cn("flex w-full items-center justify-between gap-4 p-3", className)}
      aria-expanded={isOpen}
      aria-controls={contentId}
      {...props}
    >
      <TraceLine status={failed ? "error" : running ? "running" : undefined}>
        <TraceIcon><WrenchIcon /></TraceIcon>
        <TraceTitle className="font-medium">{text}</TraceTitle>
      </TraceLine>
    </TraceCollapsibleTrigger>
  );
};

export type ToolContentProps = ComponentProps<"div">;

export const ToolContent = ({ className, children, ...props }: ToolContentProps) => {
  const { contentId } = useToolContext();

  return (
    <TraceCollapsibleContent
      id={contentId}
      className={cn("text-popover-foreground outline-none", className)}
      {...props}
    >
      {children}
    </TraceCollapsibleContent>
  );
};

export type ToolInputProps = ComponentProps<"div"> & {
  input: ToolUIPart["input"];
};

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => {
  const t = useTranslations("chat.tool");

  return (
    <div className={cn("space-y-2 overflow-hidden p-4", className)} {...props}>
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {t("parameters")}
      </h4>
      <CodeBlock size="sm" className="bg-muted/50">
        <CodeBlockContent wrap>{JSON.stringify(input, null, 2)}</CodeBlockContent>
      </CodeBlock>
    </div>
  );
};

export type ToolOutputProps = ComponentProps<"div"> & {
  output: ToolUIPart["output"];
  errorText: ToolUIPart["errorText"];
};

export const ToolOutput = ({
  className,
  output,
  errorText,
  ...props
}: ToolOutputProps) => {
  const t = useTranslations("chat.tool");

  if (!(output || errorText)) {
    return null;
  }

  let Output = <>{output as ReactNode}</>;

  if (typeof output === "object" && output !== null && !isValidElement(output)) {
    Output = <CodeBlock size="sm"><CodeBlockContent wrap>{JSON.stringify(output, null, 2)}</CodeBlockContent></CodeBlock>;
  } else if (typeof output === "string") {
    Output = <CodeBlock size="sm"><CodeBlockContent wrap>{output}</CodeBlockContent></CodeBlock>;
  }
  return (
    <div className={cn("space-y-2 p-4", className)} {...props}>
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {errorText ? t("error") : t("result")}
      </h4>
      <div
        className={cn(
          "overflow-x-auto rounded-md text-xs [&_table]:w-full",
          errorText
            ? "bg-destructive/10 text-destructive"
            : "bg-muted/50 text-foreground"
        )}
      >
        {errorText && (
          <div className="px-4 py-3 whitespace-pre-wrap break-words">
            {errorText}
          </div>
        )}
        {Output}
      </div>
    </div>
  );
};
