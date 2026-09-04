import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create } from "@/test-utils/rtl-renderer";

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("lucide-react", () => ({
  Mail: () => null,
  Clock: () => null,
  Rocket: () => null,
  ChevronRight: () => null,
}));

const { NoTeamState } = await import("./no-team-state");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("shows the three onboarding steps when a user has no team", () => {
  let renderer: ReturnType<typeof create>;
  act(() => {
    renderer = create(<NoTeamState />);
  });

  const text = renderer!.root
    .findAllByType("h3")
    .map((node) => node.children.join(""));

  expect(text).toEqual([
    "steps.step1.title",
    "steps.step2.title",
    "steps.step3.title",
  ]);
  expect(
    renderer!.root.findAllByType("h1").map((node) => node.children.join("")),
  ).toEqual(["title"]);
  act(() => renderer!.unmount());
});
