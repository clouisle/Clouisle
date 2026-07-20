import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const getAPIKeys = mock(() => Promise.resolve({ items: [] }));

mock.module("next-intl", () => ({
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
mock.module("sonner", () => ({ toast: { success: mock() } }));
mock.module("@/lib/api", () => ({
  apiKeysApi: { getAPIKeys, deactivateAPIKey: mock(), activateAPIKey: mock() },
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
  APIKeyDialog: () => null,
}));
mock.module("./_components/delete-api-key-dialog", () => ({
  DeleteAPIKeyDialog: () => null,
}));
mock.module("./_components/show-key-dialog", () => ({
  ShowKeyDialog: () => null,
}));

const { default: APIKeysPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("loads API keys and presents the empty creation state", async () => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<APIKeysPage />);
  });

  expect(getAPIKeys).toHaveBeenCalledWith({ pageSize: 100 });
  expect(
    renderer!.root.findAllByType("p").map((node) => node.children.join("")),
  ).toContain("noKeys");
  expect(
    renderer!.root
      .findAllByType("button")
      .some((node) => node.children.join("").includes("createKey")),
  ).toBe(true);
  act(() => renderer!.unmount());
});
