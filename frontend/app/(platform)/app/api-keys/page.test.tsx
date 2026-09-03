import { afterEach, beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const getAPIKeys = mock(() => Promise.resolve({ items: [] }));
const deactivateAPIKey = mock(() => Promise.resolve({}));
const activateAPIKey = mock(() => Promise.resolve({}));
const success = mock();

mock.module("next-intl", () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Plus: () => null,
  Search: () => null,
  MoreHorizontal: () => null,
  Pencil: () => null,
  Trash2: () => null,
  Key: () => null,
  KeyRound: () => null,
  X: () => null,
  AlertCircle: () => null,
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/api", () => ({
  apiKeysApi: { getAPIKeys, deactivateAPIKey, activateAPIKey },
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
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: element,
  DropdownMenuContent: element,
  DropdownMenuItem: element,
  DropdownMenuSeparator: element,
  DropdownMenuTrigger: element,
}));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: element }));
mock.module("./_components/api-key-dialog", () => ({
  APIKeyDialog: ({ open, apiKey, onSuccess }: Record<string, unknown>) => (
    <div data-dialog="api-key" data-open={String(open)} data-api-key={(apiKey as { id?: string } | null)?.id ?? ""} onClick={() => (onSuccess as (key?: string) => void)?.("new-key")} />
  ),
}));
mock.module("./_components/delete-api-key-dialog", () => ({
  DeleteAPIKeyDialog: ({ open, apiKey, onSuccess }: Record<string, unknown>) => (
    <div data-dialog="delete-key" data-open={String(open)} data-api-key={(apiKey as { id?: string } | null)?.id ?? ""} onClick={() => (onSuccess as () => void)?.()} />
  ),
}));
mock.module("./_components/show-key-dialog", () => ({
  ShowKeyDialog: ({ open, apiKey }: Record<string, unknown>) => <div data-dialog="show-key" data-open={String(open)} data-api-key={apiKey as string | null ?? ""} />,
}));

const { default: APIKeysPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const apiKey = {
  id: "key-1",
  name: "Release key",
  key_prefix: "clsk_live",
  user_id: "user-1",
  scopes: [],
  rate_limit: 0,
  is_active: true,
  expires_at: null,
  last_used_at: null,
  agents: [],
  workflows: [],
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
};

beforeEach(() => {
  getAPIKeys.mockImplementation(() => Promise.resolve({ items: [] }));
  getAPIKeys.mockClear();
  deactivateAPIKey.mockClear();
  activateAPIKey.mockClear();
  success.mockClear();
});

afterEach(() => {
  mock.restore();
});

test("loads API keys and presents the empty creation state", async () => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeysPage />);
  });

  expect(getAPIKeys).toHaveBeenCalledWith({ pageSize: 100 });
  expect(renderer!.root.findByProps({ "data-testid": "api-keys-page" })).toBeDefined();
  expect(renderer!.root.findByProps({ "data-testid": "api-keys-create-button" })).toBeDefined();
  expect(
    renderer!.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("noKeys");
  const createButton = renderer!.root
    .findAllByType("button")
    .find((node) => node.children.join("").includes("createKey"))!;
  act(() => createButton.props.onClick());
  expect(renderer!.root.findByProps({ "data-dialog": "api-key" }).props["data-open"]).toBe("true");
  act(() => renderer!.unmount());
});

test("filters keys and clears an empty search result", async () => {
  getAPIKeys.mockImplementationOnce(() => Promise.resolve({ items: [apiKey] }));
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeysPage />);
  });

  act(() => {
    renderer!.root.findByType("input").props.onChange({ target: { value: "missing" } });
  });
  expect(JSON.stringify(renderer!.toJSON())).toContain("noKeysFound");
  act(() => {
    renderer!.root.findAllByType("button").find((button) => button.children.join("").includes("clearSearch"))!.props.onClick();
  });

  expect(JSON.stringify(renderer!.toJSON())).toContain("Release key");
  act(() => renderer!.unmount());
});

test("opens dialogs and toggles API key status", async () => {
  getAPIKeys.mockImplementation(() => Promise.resolve({ items: [apiKey] }));
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeysPage />);
  });

  const menuItems = renderer!.root.findAll((node) => node.props.onClick && node.children.join("").length > 0);
  act(() => menuItems.find((node) => node.children.join("").includes("edit"))!.props.onClick());
  expect(renderer!.root.findByProps({ "data-dialog": "api-key" }).props["data-api-key"]).toBe("key-1");

  act(() => menuItems.find((node) => node.children.join("").includes("delete"))!.props.onClick());
  expect(renderer!.root.findByProps({ "data-dialog": "delete-key" }).props["data-api-key"]).toBe("key-1");

  await act(async () => menuItems.find((node) => node.children.join("").includes("deactivate"))!.props.onClick());
  expect(deactivateAPIKey).toHaveBeenCalledWith("key-1");
  expect(success).toHaveBeenCalledWith("keyDeactivated");
  act(() => renderer!.unmount());
});

test("activates inactive API keys", async () => {
  getAPIKeys.mockImplementation(() => Promise.resolve({ items: [{ ...apiKey, is_active: false }] }));
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeysPage />);
  });

  await act(async () =>
    renderer!.root.findAll((node) => node.props.onClick && node.children.join("").includes("activate"))[0].props.onClick(),
  );

  expect(activateAPIKey).toHaveBeenCalledWith("key-1");
  expect(success).toHaveBeenCalledWith("keyActivated");
  act(() => renderer!.unmount());
});
