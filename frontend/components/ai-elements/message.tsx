"use client";

import { Button } from "@/components/ui/button";
import {
  ButtonGroup,
  ButtonGroupText,
} from "@/components/ui/button-group";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTrigger,
  AttachmentTitle,
} from "@/components/ui/attachment";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Message as MessageRoot,
  MessageContent as MessageBody,
  MessageFooter,
} from "@/components/ui/message";
import { cn } from "@/lib/utils";
import type { FileUIPart, UIMessage } from "ai";
import { FileTypeIcon } from "@/components/file-type-icon";
import { AuthenticatedImage } from "@/components/chat/authenticated-media";
import { downloadAuthenticatedAsset } from "@/components/chat/authenticated-asset";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  XIcon,
} from "lucide-react";
import type { ComponentProps, HTMLAttributes, ReactElement } from "react";
import {
  Children,
  createContext,
  isValidElement,
  memo,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Streamdown } from "streamdown";

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

const MessageRoleContext = createContext<UIMessage["role"]>("assistant");

export const Message = ({ className, from, ...props }: MessageProps) => (
  <MessageRoleContext.Provider value={from}>
    <MessageRoot
      align={from === "user" ? "end" : "start"}
      className={cn(
        "group !flex-col w-full max-w-[95%] gap-2",
        from === "user" ? "is-user ml-auto justify-end" : "is-assistant",
        className
      )}
      {...props}
    />
  </MessageRoleContext.Provider>
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageContent = ({
  children,
  className,
  ...props
}: MessageContentProps) => {
  const from = useContext(MessageRoleContext);

  return (
    <MessageBody
      className={cn(
        "w-full min-w-0 flex-col gap-2 overflow-hidden text-sm",
        className
      )}
      {...props}
    >
      {from === "user" ? (
        <Bubble
          align="end"
          variant="muted"
          className="w-fit max-w-full [&>[data-slot=bubble-content]]:bg-secondary"
        >
          <BubbleContent className="rounded-lg !bg-secondary px-4 py-3 text-foreground dark:!bg-secondary">
            {children}
          </BubbleContent>
        </Bubble>
      ) : (
        children
      )}
    </MessageBody>
  );
};

export type MessageActionsProps = ComponentProps<"div">;

export const MessageActions = ({
  className,
  children,
  ...props
}: MessageActionsProps) => (
  <MessageFooter
    className={cn(
      "flex items-center gap-1 px-0 text-sm font-normal text-inherit",
      className
    )}
    {...props}
  >
    {children}
  </MessageFooter>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
  tooltip?: string;
  label?: string;
};

export const MessageAction = ({
  tooltip,
  children,
  label,
  "aria-label": ariaLabel,
  variant = "ghost",
  size = "icon-sm",
  ...props
}: MessageActionProps) => {
  const button = (
    <Button
      aria-label={ariaLabel || label || tooltip}
      size={size}
      variant={variant}
      {...props}
    >
      {children}
    </Button>
  );
  if (tooltip) {
    return (
      <Tooltip>
        <TooltipTrigger render={button} />
        <TooltipContent>
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return button;
};

type MessageBranchContextType = {
  currentBranch: number;
  totalBranches: number;
  goToPrevious: () => void;
  goToNext: () => void;
  branches: ReactElement[];
  setBranches: (branches: ReactElement[]) => void;
};

const MessageBranchContext = createContext<MessageBranchContextType | null>(
  null
);

const useMessageBranch = () => {
  const context = useContext(MessageBranchContext);

  if (!context) {
    throw new Error(
      "MessageBranch components must be used within MessageBranch"
    );
  }

  return context;
};

export type MessageBranchProps = HTMLAttributes<HTMLDivElement> & {
  defaultBranch?: number;
  onBranchChange?: (branchIndex: number) => void;
};

export const MessageBranch = ({
  defaultBranch = 0,
  onBranchChange,
  className,
  ...props
}: MessageBranchProps) => {
  const [currentBranch, setCurrentBranch] = useState(defaultBranch);
  const [branches, setBranches] = useState<ReactElement[]>([]);

  const handleBranchChange = (newBranch: number) => {
    setCurrentBranch(newBranch);
    onBranchChange?.(newBranch);
  };

  const goToPrevious = () => {
    const newBranch =
      currentBranch > 0 ? currentBranch - 1 : branches.length - 1;
    handleBranchChange(newBranch);
  };

  const goToNext = () => {
    const newBranch =
      currentBranch < branches.length - 1 ? currentBranch + 1 : 0;
    handleBranchChange(newBranch);
  };

  const contextValue: MessageBranchContextType = {
    currentBranch,
    totalBranches: branches.length,
    goToPrevious,
    goToNext,
    branches,
    setBranches,
  };

  return (
    <MessageBranchContext.Provider value={contextValue}>
      <div
        className={cn("grid w-full gap-2 [&>div]:pb-0", className)}
        {...props}
      />
    </MessageBranchContext.Provider>
  );
};

export type MessageBranchContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageBranchContent = ({
  children,
  ...props
}: MessageBranchContentProps) => {
  const { currentBranch, setBranches, branches } = useMessageBranch();
  const childrenArray = useMemo(
    () => (Array.isArray(children) ? children : [children]),
    [children]
  );

  // Use useEffect to update branches when they change
  useEffect(() => {
    if (branches.length !== childrenArray.length) {
      setBranches(childrenArray);
    }
  }, [childrenArray, branches, setBranches]);

  return childrenArray.map((branch, index) => (
    <div
      className={cn(
        "grid gap-2 overflow-hidden [&>div]:pb-0",
        index === currentBranch ? "block" : "hidden"
      )}
      key={branch.key}
      {...props}
    >
      {branch}
    </div>
  ));
};

export type MessageBranchSelectorProps = Omit<HTMLAttributes<HTMLDivElement>, 'className'> & {
  from?: UIMessage["role"];  // Made optional since it's not used
};

export const MessageBranchSelector = ({
  ...props
}: MessageBranchSelectorProps) => {
  const { totalBranches } = useMessageBranch();

  // Don't render if there's only one branch
  if (totalBranches <= 1) {
    return null;
  }

  return (
    <ButtonGroup
      className="[&>*:not(:first-child)]:rounded-l-md [&>*:not(:last-child)]:rounded-r-md"
      orientation="horizontal"
      {...props}
    />
  );
};

export type MessageBranchPreviousProps = ComponentProps<typeof Button>;

export const MessageBranchPrevious = ({
  children,
  ...props
}: MessageBranchPreviousProps) => {
  const { goToPrevious, totalBranches } = useMessageBranch();

  return (
    <Button
      aria-label="Previous branch"
      disabled={totalBranches <= 1}
      onClick={goToPrevious}
      size="icon-sm"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronLeftIcon size={14} />}
    </Button>
  );
};

export type MessageBranchNextProps = ComponentProps<typeof Button>;

export const MessageBranchNext = ({
  children,
  ...props
}: MessageBranchNextProps) => {
  const { goToNext, totalBranches } = useMessageBranch();

  return (
    <Button
      aria-label="Next branch"
      disabled={totalBranches <= 1}
      onClick={goToNext}
      size="icon-sm"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronRightIcon size={14} />}
    </Button>
  );
};

export type MessageBranchPageProps = HTMLAttributes<HTMLSpanElement>;

export const MessageBranchPage = ({
  className,
  ...props
}: MessageBranchPageProps) => {
  const { currentBranch, totalBranches } = useMessageBranch();

  return (
    <ButtonGroupText
      className={cn(
        "border-none bg-transparent text-muted-foreground shadow-none",
        className
      )}
      {...props}
    >
      {currentBranch + 1} of {totalBranches}
    </ButtonGroupText>
  );
};

export type MessageResponseProps = ComponentProps<typeof Streamdown>;

export const MessageResponse = memo(
  ({ className, components, ...props }: MessageResponseProps) => (
    <Streamdown
      className={cn(
        "size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        className
      )}
      components={{
        // Use div instead of p when paragraph contains block elements (like images)
        // This prevents React hydration error: <div> cannot be a descendant of <p>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        p: ({ children, node, ...pProps }: any) => {
          // Check AST node for img elements
          const hasImgInNode = node?.children?.some(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (child: any) => child.tagName === 'img'
          )
          const hasBlockElements = Children.toArray(children).some(
            (child) =>
              isValidElement(child) &&
              (child.type === 'div' || child.type === 'img' || typeof child.type === 'function')
          )
          if (hasImgInNode || hasBlockElements) {
            return <div className="my-4" {...pProps}>{children}</div>
          }
          return <p {...pProps}>{children}</p>
        },
        ...components,
      }}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

MessageResponse.displayName = "MessageResponse";

export type MessageAttachmentProps = HTMLAttributes<HTMLDivElement> & {
  data: FileUIPart;
  className?: string;
  onRemove?: () => void;
};

export function MessageAttachment({
  data,
  className,
  onRemove,
  ...props
}: MessageAttachmentProps) {
  const filename = data.filename || "";
  const anchorProps = props as React.AnchorHTMLAttributes<HTMLAnchorElement>;
  const isImage = data.mediaType?.startsWith("image/") && Boolean(data.url);

  const handleDownload = (event: React.MouseEvent<HTMLAnchorElement>) => {
    anchorProps.onClick?.(event);
    if (event.defaultPrevented) return;
    event.preventDefault();
    if (!data.url) return;
    void downloadAuthenticatedAsset(data.url, filename).catch((error) => {
      console.error("Failed to download attachment:", error);
    });
  };

  if (isImage) {
    return (
      <Attachment
        className={cn(
          "group relative h-24 w-24 overflow-hidden rounded-lg bg-transparent !border-0 !p-0",
          className
        )}
        orientation="vertical"
        {...props}
      >
        <AttachmentMedia
          className="absolute inset-0 size-full rounded-lg p-0"
          variant="image"
        >
          <AuthenticatedImage
            alt={filename || "attachment"}
            className="size-full object-cover"
            height={100}
            src={data.url}
            width={100}
          />
        </AttachmentMedia>
        {onRemove && (
          <AttachmentActions className="absolute top-2 right-2 z-20">
            <AttachmentAction
              aria-label="Remove attachment"
              className="size-6 rounded-full bg-background/80 p-0 opacity-0 backdrop-blur-sm transition-opacity hover:bg-background group-hover:opacity-100 [&>svg]:size-3"
              onClick={(event) => {
                event.stopPropagation();
                onRemove();
              }}
              size="icon-xs"
              variant="ghost"
            >
              <XIcon />
              <span className="sr-only">Remove</span>
            </AttachmentAction>
          </AttachmentActions>
        )}
      </Attachment>
    );
  }

  return (
    <Tooltip>
      <Attachment
        className={cn(
          "group inline-flex min-w-0 max-w-48 cursor-pointer items-center gap-1.5 rounded-md border bg-muted/50 px-2 py-1 text-xs transition-colors hover:bg-muted",
          className
        )}
        size="xs"
      >
        <AttachmentMedia className="size-auto w-auto shrink-0 rounded-none bg-transparent p-0">
          <FileTypeIcon
            className="size-3.5 shrink-0"
            filename={filename}
            mimeType={data.mediaType}
          />
        </AttachmentMedia>
        <AttachmentContent className="min-w-0 flex-none leading-normal">
          <AttachmentTitle className="max-w-32 font-normal">
            {filename || "Attachment"}
          </AttachmentTitle>
        </AttachmentContent>
        {onRemove && (
          <AttachmentActions className="relative z-20">
            <AttachmentAction
              aria-label="Remove attachment"
              className="size-5 shrink-0 rounded p-0 opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100 [&>svg]:size-3"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onRemove();
              }}
              size="icon-xs"
              variant="ghost"
            >
              <XIcon />
              <span className="sr-only">Remove</span>
            </AttachmentAction>
          </AttachmentActions>
        )}
        <TooltipTrigger
          render={
            <AttachmentTrigger
              render={
                <a
                  aria-label={filename || "Attachment"}
                  href={data.url}
                  download={filename}
                  {...anchorProps}
                  onClick={handleDownload}
                />
              }
            />
          }
        />
      </Attachment>
      <TooltipContent>
        <p>{filename || "Attachment"}</p>
      </TooltipContent>
    </Tooltip>
  );
}

export type MessageAttachmentsProps = ComponentProps<"div">;

export function MessageAttachments({
  children,
  className,
  ...props
}: MessageAttachmentsProps) {
  if (!children) {
    return null;
  }

  return (
    <AttachmentGroup
      className={cn(
        "ml-auto flex w-fit flex-wrap items-start gap-2 overflow-x-visible overflow-y-visible py-0",
        className
      )}
      {...props}
    >
      {children}
    </AttachmentGroup>
  );
}

export type MessageToolbarProps = ComponentProps<"div">;

export const MessageToolbar = ({
  className,
  children,
  ...props
}: MessageToolbarProps) => (
  <div
    className={cn(
      "mt-4 flex w-full items-center justify-between gap-4",
      className
    )}
    {...props}
  >
    {children}
  </div>
);

