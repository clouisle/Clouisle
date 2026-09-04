import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const deleteModel = mock(() => Promise.resolve());
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/api/admin/models", () => ({ modelsApi: { deleteModel } }));
mock.module("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogAction: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => (
    <button>{children}</button>
  ),
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <p>{children}</p>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <footer>{children}</footer>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <header>{children}</header>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <h1>{children}</h1>
  ),
}));

const { DeleteModelDialog } = await import("./delete-model-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  deleteModel.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
});

const render = (model: unknown) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <DeleteModelDialog
        open
        onOpenChange={onOpenChange}
        model={model as never}
        onSuccess={onSuccess}
      />,
    );
  });
  return renderer!;
};

test("deletes the selected model and refreshes its list", async () => {
  const renderer = render({ id: "model-1", name: "Model" });

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(deleteModel).toHaveBeenCalledWith("model-1");
  expect(success).toHaveBeenCalledWith("modelDeleted");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  expect(onSuccess).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});

test("does not delete when no model is selected", async () => {
  const renderer = render(null);

  await act(async () =>
    renderer.root.findAllByType("button")[1].props.onClick(),
  );

  expect(deleteModel).not.toHaveBeenCalled();
  act(() => renderer.unmount());
});
