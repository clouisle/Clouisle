import { afterEach, beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const createAPIKey = mock(() => Promise.resolve({ key: "new-key" }));
const updateAPIKey = mock(() => Promise.resolve({}));
const getAgents = mock(() => Promise.resolve({ items: [] }));
const getWorkflows = mock(() => Promise.resolve({ items: [] }));
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/api", () => ({
  apiKeysApi: { createAPIKey, updateAPIKey },
  agentsApi: { getAgents },
  workflowsApi: { getWorkflows },
}));
const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} />
  ),
}));
mock.module("@/components/ui/label", () => ({ Label: element }));
mock.module("@/components/ui/switch", () => ({
  Switch: (props: Record<string, unknown>) => <button {...props} />,
}));
mock.module("@/components/ui/checkbox", () => ({
  Checkbox: (props: Record<string, unknown>) => <button {...props} />,
}));
mock.module("@/components/ui/scroll-area", () => ({ ScrollArea: element }));
mock.module("lucide-react", () => ({
  Bot: () => null,
  Loader2: () => null,
  Workflow: () => null,
}));
mock.module("@/components/ui/dialog", () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogContent: element,
  DialogDescription: element,
  DialogFooter: element,
  DialogHeader: element,
  DialogTitle: element,
}));
mock.module("@/components/ui/field", () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}));
mock.module("@/lib/validation", () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const rest = { ...errors };
    delete rest[field];
    return rest;
  },
  getValidationSummaryEntries: () => [],
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (_: string, message: string) => message,
}));

const { APIKeyDialog } = await import("./api-key-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = async (props: Partial<React.ComponentProps<typeof APIKeyDialog>> = {}) => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      <APIKeyDialog
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
        {...props}
      />,
    );
  });
  return renderer!;
};

beforeEach(() => {
  createAPIKey.mockClear();
  updateAPIKey.mockClear();
  getAgents.mockClear();
  getWorkflows.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
});

afterEach(() => {
  mock.restore();
});

test("blocks API-key creation until a name is provided", async () => {
  const renderer = await render();

  expect(renderer.root.findByProps({ "data-testid": "api-key-dialog" })).toBeDefined();
  expect(renderer.root.findByProps({ "data-testid": "api-key-name-input" })).toBeDefined();
  expect(renderer.root.findByProps({ "data-testid": "api-key-submit" })).toBeDefined();

  await act(async () =>
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }),
  );

  expect(createAPIKey).not.toHaveBeenCalled();
  expect(renderer.root.findByProps({ id: "name" }).props["aria-invalid"]).toBe(
    true,
  );
  expect(renderer.root.findAllByProps({ role: "alert" })).toHaveLength(1);
  act(() => renderer.unmount());
});

test("creates an API key with selected agents and workflows", async () => {
  getAgents.mockImplementationOnce(() =>
    Promise.resolve({ items: [{ id: "agent-1", name: "Agent", icon: "icon.png" }] }),
  );
  getWorkflows.mockImplementationOnce(() =>
    Promise.resolve({ items: [{ id: "workflow-1", name: "Workflow", icon: "flow.png" }] }),
  );
  const renderer = await render();

  await act(async () => {
    await Promise.resolve();
  });
  act(() => {
    renderer.root.findByProps({ id: "name" }).props.onChange({ target: { value: "Release key" } });
  });
  act(() => {
    renderer.root.findByProps({ id: "rate_limit" }).props.onChange({ target: { value: "120" } });
  });
  act(() => {
    renderer.root.findByProps({ id: "expires_at" }).props.onChange({ target: { value: "2026-02-03" } });
  });
  const selectableRows = renderer.root
    .findAllByProps({ className: "flex items-center space-x-3 rounded-md p-2 hover:bg-muted/50 cursor-pointer" });
  act(() => {
    selectableRows[0].props.onClick();
    selectableRows[1].props.onClick();
  });
  await act(async () =>
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }),
  );

  expect(createAPIKey).toHaveBeenCalledWith({
    name: "Release key",
    rate_limit: 120,
    expires_at: new Date("2026-02-03").toISOString(),
    agent_ids: ["agent-1"],
    workflow_ids: ["workflow-1"],
  });
  expect(success).toHaveBeenCalledWith("keyCreated");
  expect(onSuccess).toHaveBeenCalledWith("new-key");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});

test("updates an existing API key and clears selected resources", async () => {
  getAgents.mockImplementationOnce(() =>
    Promise.resolve({ items: [{ id: "agent-1", name: "Agent", avatar_url: "avatar.png" }] }),
  );
  getWorkflows.mockImplementationOnce(() =>
    Promise.resolve({ items: [{ id: "workflow-1", name: "Workflow" }] }),
  );
  const renderer = await render({
    apiKey: {
      id: "key-1",
      name: "Old key",
      key_prefix: "clsk_1234",
      user_id: "user-1",
      scopes: [],
      rate_limit: 60,
      is_active: true,
      expires_at: "2026-01-02T00:00:00.000Z",
      last_used_at: null,
      agents: [{ id: "agent-1", name: "Agent" }],
      workflows: [{ id: "workflow-1", name: "Workflow" }],
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
    },
  });

  await act(async () => {
    await Promise.resolve();
  });
  act(() => {
    renderer.root.findByProps({ id: "name" }).props.onChange({ target: { value: "Updated key" } });
  });
  act(() => {
    renderer.root.findByProps({ id: "rate_limit" }).props.onChange({ target: { value: "" } });
  });
  act(() => {
    renderer.root.findByProps({ id: "is_active" }).props.onCheckedChange(false);
  });
  const selectableRows = renderer.root
    .findAllByProps({ className: "flex items-center space-x-3 rounded-md p-2 hover:bg-muted/50 cursor-pointer" });
  act(() => {
    selectableRows[0].props.onClick();
    selectableRows[1].props.onClick();
  });
  await act(async () =>
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }),
  );

  expect(updateAPIKey).toHaveBeenCalledWith("key-1", {
    name: "Updated key",
    rate_limit: 0,
    expires_at: new Date("2026-01-02").toISOString(),
    is_active: false,
    agent_ids: [],
    workflow_ids: [],
  });
  expect(success).toHaveBeenCalledWith("keyUpdated");
  expect(onSuccess).toHaveBeenCalledWith();
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});
