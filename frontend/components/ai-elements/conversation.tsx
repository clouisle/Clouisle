"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";
import { useTranslations } from "next-intl";
import * as React from "react";
import {
  MessageScroller,
  MessageScrollerItem,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";

export type ConversationProps = ComponentProps<typeof MessageScroller>;

export const Conversation = ({
  className,
  role = "log",
  ...props
}: ConversationProps) => (
  <MessageScrollerProvider autoScroll>
    <MessageScroller
      className={cn("relative flex-1 overflow-y-hidden", className)}
      role={role}
      {...props}
    />
  </MessageScrollerProvider>
);

export type ConversationContentProps = ComponentProps<
  typeof MessageScrollerContent
> & {
  messageIds?: readonly string[];
  scrollAnchorIndex?: number;
};

export const ConversationContent = ({
  className,
  children,
  messageIds,
  scrollAnchorIndex,
  ...props
}: ConversationContentProps) => {
  const items = React.Children.map(children, (child, index) => (
    <MessageScrollerItem
      key={React.isValidElement(child) && child.key ? child.key : index}
      messageId={messageIds?.[index]}
      scrollAnchor={index === scrollAnchorIndex}
    >
      {child}
    </MessageScrollerItem>
  ));
  return (
    <MessageScrollerViewport>
      <MessageScrollerContent
        className={cn("flex flex-col gap-8 p-4", className)}
        {...props}
      >
        {items}
      </MessageScrollerContent>
    </MessageScrollerViewport>
  );
};

export type ConversationScrollButtonProps = ComponentProps<typeof Button> &
  Pick<ComponentProps<typeof MessageScrollerButton>, "behavior" | "direction">;

export const ConversationScrollButton = ({
  className,
  direction = "end",
  behavior,
  variant = "outline",
  size = "icon",
  onClick,
  ref,
  ...buttonProps
}: ConversationScrollButtonProps) => {
  const t = useTranslations("chat.message");
  return (
    <MessageScrollerButton
      direction={direction}
      behavior={behavior}
      onClick={onClick}
      ref={ref}
      label={t(direction === "start" ? "scrollToStart" : "scrollToEnd")}
      className={cn("absolute bottom-4 left-[50%] translate-x-[-50%] rounded-full", className)}
      render={<Button variant={variant} size={size} {...buttonProps} />}
    />
  );
};

export type ConversationEmptyStateProps = ComponentProps<"div"> & {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
};

export const ConversationEmptyState = ({
  className,
  title = "No messages yet",
  description = "Start a conversation to see messages here",
  icon,
  children,
  ...props
}: ConversationEmptyStateProps) => (
  <div
    className={cn(
      "flex size-full flex-col items-center justify-center gap-3 p-8 text-center",
      className
    )}
    {...props}
  >
    {children ?? (
      <>
        {icon && <div className="text-muted-foreground">{icon}</div>}
        <div className="space-y-1">
          <h3 className="font-medium text-sm">{title}</h3>
          {description && (
            <p className="text-muted-foreground text-sm">{description}</p>
          )}
        </div>
      </>
    )}
  </div>
);

