import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const deleteAPIKey = mock(() => Promise.resolve());
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/api", () => ({ apiKeysApi: { deleteAPIKey } }));
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("@/components/ui/dialog", () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <p>{children}</p>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <footer>{children}</footer>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <header>{children}</header>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <h1>{children}</h1>,
}));

const { DeleteAPIKeyDialog } = await import("./delete-api-key-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  deleteAPIKey.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
});

const render = (apiKey: unknown) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <DeleteAPIKeyDialog
        open
        onOpenChange={onOpenChange}
        apiKey={apiKey as never}
        onSuccess={onSuccess}
      />,
    );
  });
  return renderer!;
};

test("deletes the selected API key and refreshes the key list", async () => {
  const renderer = render({ id: "key-1", name: "Key" });

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(deleteAPIKey).toHaveBeenCalledWith("key-1");
  expect(success).toHaveBeenCalledWith("keyDeleted");
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});

test("does not delete when no API key is selected", async () => {
  const renderer = render(null);

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(deleteAPIKey).not.toHaveBeenCalled();
  act(() => renderer.unmount());
});
