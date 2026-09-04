import { afterEach, expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const push = mock(() => {});
let teamState: { currentTeam: { id: string } | null; isLoading: boolean } = {
  currentTeam: { id: "team-1" },
  isLoading: false,
};

mock.module("next/navigation", () => ({
  useRouter: () => ({ push }),
}));
mock.module("@/contexts/team-context", () => ({
  useTeam: () => teamState,
}));
mock.module("@/components/skill-detail-client", () => ({
  SkillDetailClient: (props: Record<string, string>) => (
    <div data-testid="skill-detail" {...props} />
  ),
}));

const { default: PlatformSkillDetailPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let renderer: ReactTestRenderer | undefined;

afterEach(() => {
  if (renderer) act(() => renderer!.unmount());
  renderer = undefined;
  push.mockClear();
});

async function render() {
  await act(async () => {
    renderer = create(
      <PlatformSkillDetailPage params={Promise.resolve({ id: "skill-1" })} />,
    );
    await Promise.resolve();
  });
  return renderer!;
}

test("passes the route and current team to platform skill details", async () => {
  teamState = { currentTeam: { id: "team-1" }, isLoading: false };

  const view = await render();
  const detail = view.root.findByProps({ "data-testid": "skill-detail" });

  expect(detail.props.skillId).toBe("skill-1");
  expect(detail.props.teamId).toBe("team-1");
  expect(detail.props.mode).toBe("platform");
  expect(detail.props.backHref).toBe("/app/capabilities?tab=skills");
  expect(push).not.toHaveBeenCalled();
});

test("redirects to the skills list after team loading finishes empty", async () => {
  teamState = { currentTeam: null, isLoading: false };

  const view = await render();

  expect(view.toJSON()).toBeNull();
  expect(push).toHaveBeenCalledWith("/app/capabilities?tab=skills");
});
