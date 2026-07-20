import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "react-test-renderer";

mock.module("next-intl", () => ({
  useTranslations: () => {
    const translate = (key: string, options?: { defaultValue?: string }) =>
      key.startsWith("admin.typeOptions.") ? options?.defaultValue || "" : key;
    translate.has = (key: string) =>
      !key.endsWith("webhook") && !key.endsWith("failed");
    return translate;
  },
}));
mock.module("streamdown", () => ({
  Streamdown: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
mock.module("@/lib/utils", () => ({
  formatDateTime: (value: string) => `date:${value}`,
}));
const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/dialog", () => ({
  Dialog: element,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/tooltip", () => ({
  Tooltip: element,
  TooltipContent: element,
  TooltipTrigger: element,
}));
mock.module("lucide-react", () => ({
  Mail: () => <span>mail-icon</span>,
  MessageSquare: () => <span>message-icon</span>,
  CheckCircle2: () => <span>success-icon</span>,
  XCircle: () => <span>failed-icon</span>,
  Loader2: () => <span>sending-icon</span>,
  Clock: () => <span>pending-icon</span>,
}));

const { NotificationDetailDialog } =
  await import("./notification-detail-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const notification = {
  id: "notification-1",
  scope: "global",
  type: "workflow.run_failed",
  source: "system",
  title: "Workflow failed",
  content: "The run stopped.",
  level: "high",
  status: "active",
  created_at: "2026-07-20T12:00:00Z",
  updated_at: "2026-07-20T12:00:00Z",
  is_read: false,
  link_url: "https://example.test/run/1",
  expires_at: "2026-07-21T12:00:00Z",
  deliveries: [
    {
      channel: "email",
      status: "success",
      retry_count: 1,
      sent_at: "2026-07-20T12:01:00Z",
      created_at: "2026-07-20T12:00:00Z",
      updated_at: "2026-07-20T12:01:00Z",
    },
    {
      channel: "webhook",
      status: "failed",
      error_message: "endpoint unavailable",
      retry_count: 0,
      created_at: "2026-07-20T12:00:00Z",
      updated_at: "2026-07-20T12:00:00Z",
    },
  ],
} as const;

test("renders notification metadata, link, and delivery outcomes", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(
      <NotificationDetailDialog
        notification={notification}
        open
        onOpenChange={mock()}
      />,
    );
  });

  const text = renderer!.root
    .findAllByType("div")
    .map((node) => node.children.join(""))
    .join(" ");
  expect(text).toContain("Workflow failed");
  expect(text).toContain("The run stopped.");
  expect(text).toContain("workflow.run_failed");
  expect(text).toContain("date:2026-07-21T12:00:00Z");
  expect(
    renderer!.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("webhook: failed: endpoint unavailable");
  expect(
    renderer!.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("retryCount");
  expect(renderer!.root.findByType("a").props).toMatchObject({
    href: "https://example.test/run/1",
    target: "_blank",
    rel: "noopener noreferrer",
  });
  act(() => renderer!.unmount());
});

test("renders nothing without a selected notification", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(
      <NotificationDetailDialog
        notification={null}
        open
        onOpenChange={mock()}
      />,
    );
  });

  expect(renderer!.toJSON()).toBeNull();
  act(() => renderer!.unmount());
});
