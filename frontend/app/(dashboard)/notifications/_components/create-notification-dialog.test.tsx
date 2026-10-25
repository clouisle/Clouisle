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
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <select
      value={String(props.value ?? "")}
      disabled={Boolean(props.disabled)}
      onChange={(event) => (props.onValueChange as ((value: string) => void) | undefined)?.(event.target.value)}
    >{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value?: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: () => null,
}));
mock.module("@/components/ui/checkbox", () => ({
  Checkbox: ({ onCheckedChange, checked, ...props }: { onCheckedChange?: (checked: boolean) => void; checked?: boolean }) => (
    <input {...props} id={props.id} checked={checked} type="checkbox" onChange={(event) => onCheckedChange?.(event.target.checked)} />
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
  Combobox: ({ children, onValueChange, onInputValueChange, items, value }: React.PropsWithChildren<{
    onValueChange?: (value: unknown) => void;
    onInputValueChange?: (value: string) => void;
    items?: { value: string; label: string }[];
    value?: { value: string; label: string } | null;
  }>) => (
    <div>
      {children}
      <input
        aria-label="Search users"
        value={value?.label ?? ""}
        onChange={(event) => onInputValueChange?.(event.target.value)}
      />
      {items?.map((item) => (
        <button key={item.value} type="button" onClick={() => onValueChange?.(item)}>
          {item.label}
        </button>
      ))}
    </div>
  ),
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
const nodeText = (node: ReactTestRenderer['root']): string =>
  node.children.map((child) => typeof child === 'string' ? child : nodeText(child)).join('');

const submitButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType("button").find((button) => button.children.includes("admin.submit"))!;

beforeEach(() => {
  adminCreate.mockReset();
  adminCreate.mockImplementation(() => Promise.resolve());
  getTeams.mockClear();
  getTeams.mockImplementation(() => Promise.resolve({ items: [] }));
  getUsers.mockReset();
  getUsers.mockImplementation(() => Promise.resolve({ items: [] }));
  success.mockClear();
  onOpenChange.mockClear();
  onSuccess.mockClear();
  validationErrors = {};
});

test("blocks notification creation until a title is supplied", async () => {
  const renderer = await render();

  await act(async () => {
    await submitButton(renderer).props.onClick();
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
  const scope = renderer.root.findAllByType("select")[0];

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
  });
  await act(async () => submitButton(renderer).props.onClick());
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("content: requiredFields");

  await act(async () => {
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
    scope.props.onChange({ target: { value: "team" } });
  });
  await act(async () => submitButton(renderer).props.onClick());
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("team_id: requiredFields");

  await act(async () => scope.props.onChange({ target: { value: "user" } }));
  await act(async () => {
    await submitButton(renderer).props.onClick();
  });
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("user_id: requiredFields");
  act(() => renderer.unmount());
});

test("creates a scheduled team notification", async () => {
  getTeams.mockImplementation(() => Promise.resolve({ items: [{ id: "team-7", name: "Operations" }] }));
  const renderer = await render();
  const [title, link, expires] = renderer.root.findAllByType("input");
  const scope = renderer.root.findAllByType("select")[0];

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    link.props.onChange({ target: { value: "https://example.test/status" } });
    expires.props.onChange({ target: { value: "2030-04-05T09:30" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
    scope.props.onChange({ target: { value: "team" } });
  });
  const team = renderer.root.findAllByType("select").find((node) => node.props.value === "");
  await act(async () => team!.props.onChange({ target: { value: "team-7" } }));
  await act(async () => {
    await submitButton(renderer).props.onClick();
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
    await submitButton(renderer).props.onClick();
  });
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("title: already exists");
  expect(submitButton(renderer).props.disabled).toBe(false);

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
    await submitButton(renderer).props.onClick();
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

test("creates a notification with Feishu delivery selected", async () => {
  const renderer = await render();
  const [title] = renderer.root.findAllByType("input");

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
    renderer.root
      .findAllByProps({ id: "channel-feishu" })
      .find((node) => typeof node.props.onChange === "function")!
      .props.onChange({ target: { checked: true } });
  });
  await act(async () => submitButton(renderer).props.onClick());

  expect(adminCreate).toHaveBeenCalledWith(
    expect.objectContaining({ notify_channels: ["feishu"] }),
    { silent: true },
  );
  act(() => renderer.unmount());
});
test("loads users and creates a notification for the selected user", async () => {
  getUsers.mockImplementation(() => Promise.resolve({
    items: [{ id: "user-9", username: "alex" }],
  }));
  const renderer = await render();
  const title = renderer.root.findAllByType("input").find((node) => !node.props["aria-label"] && node.props.type !== "checkbox")!;
  const scope = renderer.root.findAllByType("select")[0];

  await act(async () => scope.props.onChange({ target: { value: "user" } }));
  expect(getUsers).toHaveBeenCalledWith({ page: 1, pageSize: 20, search: undefined });

  const searchInput = renderer.root.findAllByType("input").find((node) => node.props["aria-label"] === "Search users")!;
  await act(async () => searchInput.props.onChange({ target: { value: " alex " } }));
  expect(getUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: "alex" });
  const userOption = renderer.root.findAllByType("button").find((node) => node.children.includes("alex"))!;
  await act(async () => userOption.props.onClick());
  expect(renderer.root.findAllByType("input").find((node) => node.props["aria-label"] === "Search users")!.props.value).toBe("alex");

  await act(async () => {
    title.props.onChange({ target: { value: "Account notice" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Please review." } });
  });
  await act(async () => submitButton(renderer).props.onClick());

  expect(adminCreate).toHaveBeenCalledWith(expect.objectContaining({
    scope: "user",
    team_id: null,
    user_id: "user-9",
    title: "Account notice",
    content: "Please review.",
  }), { silent: true });
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});

test("clears server validation errors after editing and allows a successful retry", async () => {
  validationErrors = { title: "already exists" };
  adminCreate.mockImplementationOnce(() => Promise.reject(new Error("invalid")));
  const renderer = await render();
  const title = renderer.root.findAllByType("input").find((node) => !node.props["aria-label"] && node.props.type !== "checkbox")!;

  await act(async () => {
    title.props.onChange({ target: { value: "Maintenance" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Tonight" } });
  });
  await act(async () => submitButton(renderer).props.onClick());
  expect(nodeText(renderer.root)).toContain("title: already exists");
  expect(onSuccess).not.toHaveBeenCalled();

  await act(async () => title.props.onChange({ target: { value: "Maintenance update" } }));
  expect(nodeText(renderer.root)).not.toContain("already exists");
  await act(async () => submitButton(renderer).props.onClick());

  expect(adminCreate).toHaveBeenCalledTimes(2);
  expect(adminCreate).toHaveBeenLastCalledWith(expect.objectContaining({ title: "Maintenance update" }), { silent: true });
  expect(onSuccess).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
  act(() => renderer.unmount());
});

test("sends the selected notification type, level and webhook channel", async () => {
  const renderer = await render();
  const title = renderer.root.findAllByType("input").find((node) => !node.props["aria-label"] && node.props.type !== "checkbox")!;
  const selectors = renderer.root.findAllByType("select");
  const level = selectors.find((node) => node.props.value === "medium")!;
  const type = selectors.find((node) => node.props.value === "system_announcement")!;

  await act(async () => {
    title.props.onChange({ target: { value: "Urgent notice" } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "Read this." } });
  });
  await act(async () => type.props.onChange({ target: { value: "security_login_anomaly" } }));
  const updatedLevel = renderer.root.findAllByType("select").find((node) => node.props.value === "medium")!;
  await act(async () => updatedLevel.props.onChange({ target: { value: "high" } }));
  await act(async () => {
    renderer.root.findByProps({ id: "channel-webhook" }).props.onCheckedChange(true);
  });
  await act(async () => submitButton(renderer).props.onClick());
  expect(adminCreate).toHaveBeenCalledWith(expect.objectContaining({
    type: "security_login_anomaly",
    level: "high",
    notify_channels: ["webhook"],
  }), { silent: true });
  act(() => renderer.unmount());
});

test("rejects whitespace-only title and content before creating", async () => {
  const renderer = await render();
  const [title] = renderer.root.findAllByType("input");
  const submit = submitButton(renderer);

  await act(async () => {
    title.props.onChange({ target: { value: "   " } });
    renderer.root.findByType("textarea").props.onChange({ target: { value: "   " } });
    await submit.props.onClick();
  });
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("title: requiredFields");

  await act(async () => title.props.onChange({ target: { value: "Maintenance" } }));
  await act(async () => submitButton(renderer).props.onClick());
  expect(adminCreate).not.toHaveBeenCalled();
  expect(renderer.root.findAllByType("div").map((node) => node.children.join("")).join(" ")).toContain("content: requiredFields");
  act(() => renderer.unmount());
});
