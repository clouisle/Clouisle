import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const adminCreate = mock(() => Promise.resolve());
const getTeams = mock(() => Promise.resolve({ items: [] }));
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/lib/api/admin/notifications", () => ({
  notificationsApi: { adminCreate },
}));
mock.module("@/lib/api/admin/teams", () => ({ teamsApi: { getTeams } }));
mock.module("@/lib/api/admin/users", () => ({
  usersApi: { getUsers: mock() },
}));
mock.module("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));
mock.module("@/lib/validation", () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: _, ...remaining } = errors;
    return remaining;
  },
  formatValidationSummaryMessage: (field: string, message: string) =>
    `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>) =>
    Object.entries(errors),
  normalizeValidationErrors: () => ({}),
}));
mock.module("sonner", () => ({ toast: { success } }));

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
mock.module("@/components/ui/dialog", () => ({
  Dialog: element,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}));
mock.module("@/components/ui/field", () => ({ FieldError: element }));
mock.module("@/components/ui/select", () => ({
  Select: element,
  SelectContent: element,
  SelectItem: element,
  SelectTrigger: element,
}));
mock.module("@/components/ui/checkbox", () => ({
  Checkbox: ({
    onCheckedChange,
    ...props
  }: {
    onCheckedChange?: (checked: boolean) => void;
  }) => (
    <input
      {...props}
      type="checkbox"
      onChange={(event) => onCheckedChange?.(event.target.checked)}
    />
  ),
}));
mock.module("@/components/ui/markdown-editor", () => ({
  MarkdownEditor: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (value: string) => void;
  }) => (
    <textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
mock.module("@/components/ui/combobox", () => ({
  Combobox: element,
  ComboboxContent: element,
  ComboboxEmpty: element,
  ComboboxInput: element,
  ComboboxItem: element,
  ComboboxList: element,
  ComboboxTrigger: element,
}));

const { CreateNotificationDialog } =
  await import("./create-notification-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = async () => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      <CreateNotificationDialog
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
  });
  return renderer!;
};

beforeEach(() => {
  adminCreate.mockClear();
  getTeams.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
});

test("blocks notification creation until a title is supplied", async () => {
  const renderer = await render();

  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });

  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByProps({ role: "alert" })).toHaveLength(0);
  expect(
    renderer.root
      .findAllByType("div")
      .map((node) => node.children.join(""))
      .join(" "),
  ).toContain("requiredFields");
  act(() => renderer.unmount());
});

test("creates a global notification with the selected email channel", async () => {
  const renderer = await render();
  const [title] = renderer.root.findAllByType("input");

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    renderer.root
      .findByType("textarea")
      .props.onChange({ target: { value: "Tonight" } });
    renderer.root
      .findAllByProps({ id: "channel-email" })
      .find((node) => typeof node.props.onChange === "function")!
      .props.onChange({ target: { checked: true } });
  });
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });

  expect(adminCreate).toHaveBeenCalledWith(
    expect.objectContaining({
      scope: "global",
      title: "Maintenance",
      content: "Tonight",
      notify_channels: ["email"],
    }),
    { silent: true },
  );
  expect(success).toHaveBeenCalledWith("toast.created");
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});
