import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const defaultItem = {
  id: 'notification-1', scope: 'team', type: 'workflow.run_failed', source: 'system',
  title: 'Workflow failed', content: 'The run stopped.', level: 'high', status: 'active',
  created_at: '2026-07-20T12:00:00Z', updated_at: '2026-07-20T12:00:00Z', is_read: false,
}
interface NotificationListParams {
  page: number
  page_size: number
  scope?: string
  level?: string
  search?: string
  unread_only: boolean
}
const list = mock(async (...args: [NotificationListParams]) => { void args; return { items: [defaultItem], total: 1, page: 1, page_size: 20 } })
const markRead = mock(() => Promise.resolve({ updated: 1 }));
const onReadUpdated = mock();
const submitPauseRequest = mock(() => Promise.resolve({ pause_request_id: "pr-1", status: "submitted" }));
const toastSuccess = mock();
const toastError = mock();

mock.module("next-intl", () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }));
mock.module("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark" }) }));
mock.module("next/dynamic", () => ({ default: () => (props: Record<string, unknown>) => <div data-markdown-source={props.source} /> }));
mock.module("lucide-react", () => ({
  Check: () => null,
  Loader2: () => null,
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
const infiniteScrollCalls: Array<{ hasMore: boolean; loading: boolean; onLoadMore: () => void }> = [];
mock.module("@/hooks/use-infinite-scroll", () => ({
  useInfiniteScroll: (options: { hasMore: boolean; loading: boolean; onLoadMore: () => void }) => {
    infiniteScrollCalls.length = 0;
    infiniteScrollCalls.push(options);
    return { current: null };
  },
}));
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
mock.module("@/components/ui/data-table-faceted-filter", () => ({
  DataTableFacetedFilter: ({
    title,
    options,
    selectedValues,
    onSelectionChange,
  }: {
    title: string;
    options: { value: string; label: string }[];
    selectedValues: Set<string>;
    onSelectionChange: (values: Set<string>) => void;
  }) => (
    <div data-filter={title}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={selectedValues.has(option.value)}
          onClick={() => {
            const next = new Set(selectedValues);
            if (next.has(option.value)) next.delete(option.value);
            else next.add(option.value);
            onSelectionChange(next);
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  ),
}));
mock.module("@/components/ui/table", () => ({
  Table: element,
  TableBody: element,
  TableCell: element,
  TableHead: element,
  TableHeader: element,
  TableRow: element,
}));
mock.module("@/components/ui/dialog", () => ({
  Dialog: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
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

function nodeText(node: ReactTestRenderer['root']): string {
  return node.children.map((child) => typeof child === 'string' ? child : nodeText(child)).join('')
}

beforeEach(() => {
  infiniteScrollCalls.length = 0;
  list.mockClear();
  list.mockImplementation(() => Promise.resolve({ items: [defaultItem], total: 1, page: 1, page_size: 20 }));
  markRead.mockClear();
  onReadUpdated.mockClear();
  submitPauseRequest.mockClear();
  getPendingPauseRequest.mockClear();
  toastSuccess.mockClear();
  toastError.mockClear();
});

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
test("opens notification details with content and closes from the dialog", async () => {
  list.mockResolvedValueOnce({
    items: [{
      id: "detail-1",
      scope: "user",
      type: "workflow.run_failed",
      source: "system",
      title: "Failed run details",
      content: "Expanded failure explanation",
      level: "medium",
      status: "active",
      created_at: "2026-07-20T13:00:00Z",
      updated_at: "2026-07-20T13:00:00Z",
      is_read: true,
    }],
    total: 1,
    page: 1,
    page_size: 20,
  });

  const renderer = await renderClient();
  const titleButton = renderer.root.findAllByType("button").find((node) =>
    nodeText(node).includes("Failed run details"),
  )!;
  act(() => titleButton.props.onClick());

  expect(renderer.root.findAll((node) => node.props["data-markdown-source"] === "Expanded failure explanation")).toHaveLength(1);
  const dialog = renderer.root.findAllByType("div").find((node) => node.props.open === true);
  expect(dialog).toBeDefined();
  act(() => dialog!.props.onOpenChange(false));
  expect(renderer.root.findAllByType("div").some((node) => node.props.open === true)).toBe(false);
  act(() => renderer.unmount());
});

test("loads unread results incrementally instead of fetching every page", async () => {
  const firstUnread = { ...approvalItem, id: "unread-1", title: "First unread", is_read: false };
  const secondUnread = { ...approvalItem, id: "unread-2", title: "Second unread", is_read: false };
  const renderer = await renderClient();
  const scopeFilter = renderer.root.findByProps({ "data-filter": "scope" });
  const unreadFilter = renderer.root.findByProps({ "data-filter": "unreadOnly" });

  list.mockResolvedValueOnce({ items: [defaultItem], total: 1, page: 1, page_size: 20 });
  await act(async () => {
    scopeFilter.findAllByType("button").find((node) => node.children.join("") === "scopeOptions.user")!.props.onClick();
  });
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ scope: "user", page: 1 }));

  list.mockResolvedValueOnce({ items: [firstUnread], total: 2, page: 1, page_size: 20 });
  await act(async () => {
    unreadFilter.findAllByType("button")[0]!.props.onClick();
  });
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({
    scope: "user",
    unread_only: true,
    page: 1,
  }));
  expect(list.mock.calls.filter(([params]) => params.unread_only)).toHaveLength(1);
  expect(nodeText(renderer.root)).toContain("First unread");
  expect(nodeText(renderer.root)).not.toContain("Second unread");

  list.mockResolvedValueOnce({ items: [secondUnread], total: 2, page: 2, page_size: 20 });
  await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() });
  await act(async () => {});
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({
    unread_only: true,
    page: 2,
  }));
  expect(nodeText(renderer.root)).toContain("First unread");
  expect(nodeText(renderer.root)).toContain("Second unread");
  act(() => renderer.unmount());
});

test("clears the search and appends the next page at the bottom", async () => {
  list.mockImplementation(async (params) => ({
    items: [approvalItem],
    total: 41,
    page: params.page,
    page_size: 20,
  }));
  const renderer = await renderClient();
  const input = renderer.root.findByType("input");
  await act(async () => input.props.onChange({ target: { value: "  deployment  " } }));
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: "deployment", page: 1 }));

  const searchClear = renderer.root.findAllByType("button").find((node) =>
    node.children.length === 1 && node.props.className?.includes("absolute right-2"),
  );
  await act(async () => searchClear!.props.onClick());
  expect(renderer.root.findByType("input").props.value).toBe("");
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, page: 1 }));

  const nextItem = { ...approvalItem, id: "page-2", title: "Deployment approved", is_read: true };
  list.mockResolvedValueOnce({ items: [nextItem], total: 41, page: 2, page_size: 20 });
  await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() });
  await act(async () => {});
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  expect(nodeText(renderer.root)).toContain("Deployment approved");
  expect(renderer.root.findAllByType("span").some((node) => nodeText(node) === "2 / 3")).toBe(false);
  act(() => renderer.unmount());
});

test("refreshes the loaded window after marking read so unread items are not skipped", async () => {
  const firstUnread = { ...defaultItem, id: "unread-1", title: "First unread", is_read: false };
  const nextUnread = { ...defaultItem, id: "unread-3", title: "Third unread", is_read: false };
  list.mockImplementation(async (params) => ({
    items: [firstUnread],
    total: 2,
    page: params.page,
    page_size: 20,
  }));

  const renderer = await renderClient();
  const unreadFilter = renderer.root.findByProps({ "data-filter": "unreadOnly" });
  list.mockResolvedValueOnce({ items: [firstUnread], total: 2, page: 1, page_size: 20 });
  await act(async () => { unreadFilter.findAllByType("button")[0]!.props.onClick() });
  expect(nodeText(renderer.root)).toContain("First unread");

  list.mockResolvedValueOnce({ items: [nextUnread], total: 1, page: 1, page_size: 20 });
  await act(async () => {
    renderer.root.findAllByType("button")
      .find((node) => node.children.join("") === "markRead")!
      .props.onClick({ stopPropagation: mock() });
  });

  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ unread_only: true, page: 1 }));
  expect(markRead).toHaveBeenCalledWith({ notification_ids: ["unread-1"] });
  expect(nodeText(renderer.root)).toContain("Third unread");
  expect(nodeText(renderer.root)).not.toContain("First unread");
  act(() => renderer.unmount());
});

test("invalidates an in-flight append when a mutation refreshes the window", async () => {
  list.mockImplementation(async (params) => ({
    items: [defaultItem],
    total: 3,
    page: params.page,
    page_size: 20,
  }));
  const renderer = await renderClient();

  type NotificationPageFixture = {
    items: (typeof defaultItem)[];
    total: number;
    page: number;
    page_size: number;
  };
  const appendGate = Promise.withResolvers<NotificationPageFixture>();
  list.mockImplementationOnce(() => appendGate.promise);
  await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() });

  const refreshedItem = { ...defaultItem, id: "refreshed-1", title: "Refreshed unread", is_read: false };
  const staleItem = { ...defaultItem, id: "stale-1", title: "Stale page two", is_read: false };
  list.mockResolvedValueOnce({ items: [refreshedItem], total: 1, page: 1, page_size: 20 });
  await act(async () => {
    renderer.root.findAllByType("button")
      .find((node) => node.children.join("") === "markRead")!
      .props.onClick({ stopPropagation: mock() });
  });
  await act(async () => {});

  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }));
  expect(nodeText(renderer.root)).toContain("Refreshed unread");

  await act(async () => { appendGate.resolve({ items: [staleItem], total: 3, page: 2, page_size: 20 }) });
  await act(async () => {});
  expect(nodeText(renderer.root)).not.toContain("Stale page two");
  act(() => renderer.unmount());
});

test("retries a failed window refresh instead of appending the next page", async () => {
  const secondPage = { ...defaultItem, id: "page-2", title: "Second page", is_read: true };
  list.mockImplementation(async (params) => ({
    items: params.page === 1 ? [defaultItem] : [secondPage],
    total: 41,
    page: params.page,
    page_size: 20,
  }));
  const renderer = await renderClient();
  await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() });
  await act(async () => {});
  expect(nodeText(renderer.root)).toContain("Second page");

  list.mockRejectedValueOnce(new Error("refresh failed"));
  await act(async () => {
    renderer.root.findAllByType("button")
      .find((node) => node.children.join("") === "markRead")!
      .props.onClick({ stopPropagation: mock() });
  });
  await act(async () => {});
  expect(nodeText(renderer.root)).toContain("loadFailed");

  list.mockClear();
  await act(async () => {
    renderer.root.findAllByType("button")
      .find((node) => node.children.join("") === "retry")!
      .props.onClick();
  });
  await act(async () => {});

  expect(list.mock.calls.map(([params]) => params.page)).toEqual([1, 2]);
  expect(nodeText(renderer.root)).toContain("Second page");
  act(() => renderer.unmount());
});

test("clears the total when a refresh returns no items", async () => {
  const renderer = await renderClient();
  list.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });

  await act(async () => { renderer.root.findAllByType("button")[0]!.props.onClick() });
  await act(async () => {});

  expect(nodeText(renderer.root)).toContain("empty");
  expect(infiniteScrollCalls.at(-1)!.hasMore).toBe(false);
  act(() => renderer.unmount());
});
