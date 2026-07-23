import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";

const adminCreate = mock(() => Promise.resolve());
const success = mock();
const onOpenChange = mock();

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/lib/api/admin/notifications", () => ({
  notificationsApi: { adminCreate },
}));
mock.module("sonner", () => ({ toast: { success } }));
mock.module("@/lib/validation", () => ({
  clearValidationError: (errors: Record<string, string>, field: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  formatValidationSummaryMessage: (field: string, message: string) =>
    `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>) =>
    Object.entries(errors),
  normalizeValidationErrors: () => ({}),
}));
mock.module("lucide-react", () => ({ Loader2: () => null }));

const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/dialog", () => ({
  Dialog: element,
  DialogContent: element,
  DialogDescription: element,
  DialogFooter: element,
  DialogHeader: element,
  DialogTitle: element,
}));
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
mock.module("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
    <textarea {...props} />
  ),
}));
mock.module("@/components/ui/label", () => ({ Label: element }));
mock.module("@/components/ui/badge", () => ({ Badge: element }));
mock.module("@/components/ui/field", () => ({ FieldError: element }));
mock.module("@/components/ui/select", () => ({
  Select: element,
  SelectContent: element,
  SelectItem: element,
  SelectTrigger: element,
  SelectValue: element,
}));

const { SendNotificationDialog } = await import("./send-notification-dialog");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const render = () => {
  let renderer: ReactTestRenderer;
  act(() => {
    renderer = create(
      <SendNotificationDialog
        open
        onOpenChange={onOpenChange}
        userIds={["user-1"]}
        users={[{ id: "user-1", username: "Ada", email: "ada@example.test" }]}
      />,
    );
  });
  return renderer!;
};

beforeEach(() => {
  adminCreate.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
});

test("blocks delivery without a notification title", async () => {
  const renderer = render();

  await act(async () => {
    await renderer.root
      .findByType("form")
      .props.onSubmit({ preventDefault: mock() });
  });

  expect(adminCreate).not.toHaveBeenCalled();
  expect(
    renderer.root
      .findAllByType("div")
      .map((node) => node.children.join(""))
      .join(" "),
  ).toContain("notificationTitleRequired");
  act(() => renderer.unmount());
});

test("sends a notification to the selected users", async () => {
  const renderer = render();
  const [title] = renderer.root.findAllByType("input");

  await act(async () => {
    title.props.onChange({ target: { value: "Service notice" } });
    renderer.root
      .findByType("textarea")
      .props.onChange({ target: { value: "Maintenance tonight" } });
  });
  await act(async () => {
    await renderer.root
      .findByType("form")
      .props.onSubmit({ preventDefault: mock() });
  });

  expect(adminCreate).toHaveBeenCalledWith(
    {
      scope: "user",
      user_ids: ["user-1"],
      type: "admin_notification",
      title: "Service notice",
      content: "Maintenance tonight",
      level: "medium",
    },
    { silent: true },
  );
  expect(success).toHaveBeenCalledWith("notificationSent");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});
