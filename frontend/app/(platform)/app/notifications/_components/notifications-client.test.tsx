import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const list = mock(() =>
  Promise.resolve({
    items: [
      {
        id: "notification-1",
        scope: "team",
        type: "workflow.run_failed",
        source: "system",
        title: "Workflow failed",
        content: "The run stopped.",
        level: "high",
        status: "active",
        created_at: "2026-07-20T12:00:00Z",
        updated_at: "2026-07-20T12:00:00Z",
        is_read: false,
      },
    ],
    total: 1,
    page: 1,
    page_size: 20,
  }),
);
const markRead = mock(() => Promise.resolve({ updated: 1 }));
const onReadUpdated = mock();
const submitPauseRequest = mock(() => Promise.resolve({ pause_request_id: "pr-1", status: "submitted" }));
const toastSuccess = mock();
const toastError = mock();

mock.module("next-intl", () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }));
mock.module("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark" }) }));
mock.module("next/dynamic", () => ({ default: () => () => <div /> }));
mock.module("lucide-react", () => ({
  Check: () => null,
  ChevronLeft: () => null,
  ChevronRight: () => null,
  Megaphone: () => null,
  Search: () => null,
  ShieldAlert: () => null,
  Sparkles: () => null,
  X: () => null,
}));
mock.module("@/lib/api", () => ({ notificationsApi: { list, markRead } }));
const getPendingPauseRequest = mock(() => Promise.resolve(null))
mock.module("@/lib/api/workflows", () => ({ workflowsApi: { getPendingPauseRequest, submitPauseRequest } }));
mock.module("@/components/chat/pause-request-actions", () => ({
  PauseRequestActions: (props: Record<string, unknown>) => <div data-pause-actions={JSON.stringify({ variant: props.variant, workflowId: props.workflowId, runId: props.runId, pauseRequestId: props.pauseRequestId })} onResolved={props.onResolved} />,
}));
mock.module("@/hooks/use-debounce", () => ({ useDebounce: (value: string) => value }));
mock.module("@/lib/notifications/display", () => ({
  getNotificationDisplayMeta: () => ({
    kind: "delivery",
    isAnnouncement: false,
    priorityScore: 5,
  }),
  getPauseActionMeta: (item: { type: string; data?: Record<string, unknown> | null }) =>
    item.type === "workflow.pause_pending" &&
    typeof item.data?.workflow_id === "string" &&
    typeof item.data?.run_id === "string" &&
    typeof item.data?.pause_request_id === "string"
      ? { workflowId: item.data.workflow_id, runId: item.data.run_id, requestId: item.data.pause_request_id }
      : null,
}));
mock.module("@/lib/utils", () => ({ formatDateTime: (value: unknown) => String(value), cn: (...values: string[]) => values.filter(Boolean).join(" ") }));
mock.module("sonner", () => ({ toast: { success: toastSuccess, error: toastError } }));

const element = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/button", () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: element }));
mock.module("@/components/ui/data-table-faceted-filter", () => ({ DataTableFacetedFilter: element }));
mock.module("@/components/ui/table", () => ({
  Table: element,
  TableBody: element,
  TableCell: element,
  TableHead: element,
  TableHeader: element,
  TableRow: element,
}));
mock.module("@/components/ui/dialog", () => ({
  Dialog: element,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}));

const { NotificationsClient } = await import("./notifications-client");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

async function renderClient() {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<NotificationsClient onReadUpdated={onReadUpdated} />);
  });
  return renderer!;
}

test("loads notifications and marks an unread notification read", async () => {
  const renderer = await renderClient();

  expect(list).toHaveBeenCalledWith({
    page: 1,
    page_size: 20,
    scope: undefined,
    level: undefined,
    search: undefined,
    unread_only: false,
  });
  expect(renderer.root.findAllByType("button").map((node) => node.children.join(""))).toContain("markRead");

  await act(async () => {
    renderer.root
      .findAllByType("button")
      .find((node) => node.children.join("") === "markRead")!
      .props.onClick({ stopPropagation: mock() });
  });

  expect(markRead).toHaveBeenCalledWith({ notification_ids: ["notification-1"] });
  expect(onReadUpdated).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});

test("marks all notifications read", async () => {
  const renderer = await renderClient();

  await act(async () => {
    renderer.root.findAllByType("button")[0]!.props.onClick();
  });

  expect(markRead).toHaveBeenCalledWith({ mark_all: true });
  act(() => renderer.unmount());
});

const approvalItem = {
  id: "approval-1",
  scope: "team",
  type: "workflow.pause_pending",
  source: "system",
  title: "Workflow waiting for review",
  content: "Review the quote",
  level: "high",
  status: "active",
  created_at: "2026-07-20T12:00:00Z",
  updated_at: "2026-07-20T12:00:00Z",
  is_read: false,
  data: { workflow_id: "wf-1", run_id: "run-1", pause_request_id: "pr-1" },
};

test("wires an approval notification to the shared inline actions", async () => {
  list.mockResolvedValueOnce({
    items: [approvalItem],
    total: 1,
    page: 1,
    page_size: 20,
  });

  const renderer = await renderClient();
  await act(async () => { await Promise.resolve() })

  const actions = renderer.root.findAll((node) => typeof node.props["data-pause-actions"] === "string")[0];
  const props = JSON.parse(actions.props["data-pause-actions"]);
  expect(props).toMatchObject({
    variant: "compact",
    workflowId: "wf-1",
    runId: "run-1",
    pauseRequestId: "pr-1",
  });
  expect(typeof actions.props.onResolved).toBe("function");
  act(() => renderer.unmount());
});

test("routes variable-input notifications to the run page from compact rows", async () => {
  list.mockResolvedValueOnce({
    items: [approvalItem],
    total: 1,
    page: 1,
    page_size: 20,
  });

  const renderer = await renderClient();
  await act(async () => { await Promise.resolve() })

  expect(renderer.root.findAll((node) => typeof node.props["data-pause-actions"] === "string")).toHaveLength(1)
  act(() => renderer.unmount());
});
