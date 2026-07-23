import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const remove = mock(() => Promise.resolve());
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/api/admin", () => ({ adminToolsApi: { delete: remove } }));
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

const { DeleteToolDialog } = await import("./delete-tool-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  remove.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
});

const render = (tool: unknown) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <DeleteToolDialog
        open
        onOpenChange={onOpenChange}
        tool={tool as never}
        onSuccess={onSuccess}
      />,
    );
  });
  return renderer!;
};

test("deletes the selected tool and closes the confirmation dialog", async () => {
  const renderer = render({ id: "tool-1", display_name: "Tool" });

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(remove).toHaveBeenCalledWith("tool-1");
  expect(success).toHaveBeenCalledWith("toolDeleted");
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});

test("does not issue a deletion request without a tool id", async () => {
  const renderer = render(null);

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(remove).not.toHaveBeenCalled();
  act(() => renderer.unmount());
});
