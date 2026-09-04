import { beforeEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const adminCreate = mock(() => Promise.resolve());
const getTeams = mock(() => Promise.resolve({ items: [] }));
const getUsers = mock(() => Promise.resolve({ items: [] }));
const success = mock();
const onOpenChange = mock();
const onSuccess = mock();
let validationErrors: Record<string, string> = {};

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/lib/api/admin/notifications", () => ({
  notificationsApi: { adminCreate },
}));
mock.module("@/lib/api/admin/teams", () => ({ teamsApi: { getTeams } }));
mock.module("@/lib/api/admin/users", () => ({ usersApi: { getUsers } }));
mock.module("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));
mock.module("@/lib/validation", () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const remaining = { ...errors };
    delete remaining[field];
    return remaining;
  },
  formatValidationSummaryMessage: (field: string, message: string) =>
    `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>) =>
    Object.entries(errors),
  normalizeValidationErrors: () => validationErrors,
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
  ComboboxList: () => <div />,
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
  adminCreate.mockReset();
  adminCreate.mockImplementation(() => Promise.resolve());
  getTeams.mockClear();
  getUsers.mockClear();
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
  validationErrors = {};
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

test("validates required content and team audience", async () => {
  const renderer = await render();
  const [title] = renderer.root.findAllByType("input");
  const scope = renderer.root.findAllByProps({ value: "global" })[0];

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
  });
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("content: requiredFields");

  await act(async () => {
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
    scope.props.onValueChange("team");
  });
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("team_id: requiredFields");

  await act(async () => scope.props.onValueChange("user"));
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("user_id: requiredFields");
  act(() => renderer.unmount());
});

test("creates a scheduled team notification", async () => {
  getTeams.mockImplementation(() => Promise.resolve({ items: [{ id: "team-7", name: "Operations" }] }));
  const renderer = await render();
  const [title, link, expires] = renderer.root.findAllByType("input");
  const scope = renderer.root.findAllByProps({ value: "global" })[0];

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    link.props.onChange({ target: { value: "https://example.test/status" } });
    expires.props.onChange({ target: { value: "2030-04-05T09:30" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
    scope.props.onValueChange("team");
  });
  const team = renderer.root.findAllByProps({ value: "" }).find((node) => typeof node.props.onValueChange === "function")!;
  await act(async () => team.props.onValueChange("team-7"));
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });

  expect(adminCreate).toHaveBeenCalledWith(expect.objectContaining({
    scope: "team",
    team_id: "team-7",
    user_id: null,
    link_url: "https://example.test/status",
    expires_at: new Date("2030-04-05T09:30").toISOString(),
  }), { silent: true });
  act(() => renderer.unmount());
});

test("shows a create failure and recovers when the title changes", async () => {
  validationErrors = { title: "already exists" };
  adminCreate.mockImplementation(() => Promise.reject(new Error("rejected")));
  const renderer = await render();
  const [title] = renderer.root.findAllByType("input");

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
  });
  await act(async () => {
    await renderer.root.findAllByType("button").at(-1)!.props.onClick();
  });
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("title: already exists");
  expect(renderer.root.findAllByType("button").at(-1)!.props.disabled).toBe(false);

  await act(async () => title.props.onChange({ target: { value: "Maintenance notice" } }));
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).not.toContain("already exists");
  expect(onSuccess).not.toHaveBeenCalled();
  expect(onOpenChange).not.toHaveBeenCalled();
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
  expect(renderer.root.findAllByType("input")[0].props.value).toBe("");
  expect(renderer.root.findByType("textarea").props.value).toBe("");
  expect(renderer.root.findAllByProps({ id: "channel-email" }).find((node) => typeof node.props.onChange === "function")!.props.checked).toBe(false);
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});
