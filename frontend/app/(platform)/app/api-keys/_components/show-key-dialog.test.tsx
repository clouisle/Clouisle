import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const writeText = mock(() => Promise.resolve());
const success = mock();
const onOpenChange = mock();

Object.assign(globalThis, { navigator: { clipboard: { writeText } } });

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Copy: () => null,
  Check: () => null,
  AlertTriangle: () => null,
}));
mock.module("sonner", () => ({ toast: { success, error: mock() } }));
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
mock.module("@/components/ui/alert", () => ({
  Alert: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDescription: ({ children }: React.PropsWithChildren) => (
    <p>{children}</p>
  ),
}));

const { ShowKeyDialog } = await import("./show-key-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  writeText.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
});

const render = (apiKey: string | null) => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <ShowKeyDialog open onOpenChange={onOpenChange} apiKey={apiKey} />,
    );
  });
  return renderer!;
};

test("copies a newly generated API key to the clipboard", async () => {
  const originalSetTimeout = globalThis.setTimeout
  let timeoutCallback: (() => void) | undefined
  let renderer!: ReactTestRenderer
  globalThis.setTimeout = ((callback: () => void) => { timeoutCallback = callback; return 1 }) as unknown as typeof globalThis.setTimeout
  try {
    renderer = render("test-api-key")

    await act(async () =>
      renderer.root.findAllByType("button")[0].props.onClick(),
    )

    expect(writeText).toHaveBeenCalledWith("test-api-key")
    expect(success).toHaveBeenCalledWith("copied")
    expect(renderer.root.findByType("input").props.value).toBe("test-api-key")
    act(() => timeoutCallback!())
  } finally {
    globalThis.setTimeout = originalSetTimeout
  }
  act(() => renderer.unmount())
})

test("does not copy when the dialog has no generated key", async () => {
  const renderer = render(null);

  await act(async () =>
    renderer.root.findAllByType("button")[0].props.onClick(),
  );

  expect(writeText).not.toHaveBeenCalled();
  act(() => renderer.unmount());
});
