import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const createAPIKey = mock(() => Promise.resolve({ key: "new-key" }));
const getAgents = mock(() => Promise.resolve({ items: [] }));
const getWorkflows = mock(() => Promise.resolve({ items: [] }));

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("sonner", () => ({ toast: { success: mock() } }));
mock.module("@/lib/api", () => ({
  apiKeysApi: { createAPIKey, updateAPIKey: mock() },
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
mock.module("@/components/ui/switch", () => ({ Switch: element }));
mock.module("@/components/ui/checkbox", () => ({ Checkbox: element }));
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
    const { [field]: _, ...rest } = errors;
    return rest;
  },
  getValidationSummaryEntries: () => [],
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (_: string, message: string) => message,
}));

const { APIKeyDialog } = await import("./api-key-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = async () => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeyDialog open onOpenChange={mock()} />);
  });
  return renderer!;
};

test("blocks API-key creation until a name is provided", async () => {
  const renderer = await render();

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
