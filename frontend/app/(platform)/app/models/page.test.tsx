import { expect, mock, test } from "bun:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "@/test-utils/rtl-renderer";

const getTeamModels = mock(() => Promise.resolve([]));
const currentTeam = { id: "team-1" };
const translate = (key: string) => key;

mock.module("next-intl", () => ({
  useTranslations: () => translate,
}));
mock.module("next/navigation", () => ({ useRouter: () => ({ push: mock() }) }));
mock.module("@/contexts/team-context", () => ({
  useTeam: () => ({ currentTeam }),
}));
mock.module("@/hooks/use-require-team", () => ({ useRequireTeam: mock() }));
mock.module("@/lib/api", () => ({ teamModelsApi: { getTeamModels } }));
mock.module("lucide-react", () => ({
  Bot: () => null,
  Search: () => null,
  X: () => null,
}));
const element = ({
  children,
  ...props
}: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
);
mock.module("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} />
  ),
}));
mock.module("@/components/ui/button", () => ({
  Button: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
mock.module("@/components/ui/skeleton", () => ({ Skeleton: element }));
mock.module("@/components/ui/data-table-faceted-filter", () => ({
  DataTableFacetedFilter: element,
}));
mock.module("./_components", () => ({
  ModelCard: element,
  ModelCardSkeleton: element,
  ModelDetailDialog: element,
}));

const { default: ModelsPage } = await import("./page");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

test("loads the current team's models and shows the empty-state guidance", async () => {
  let renderer: ReactTestRenderer;
  await act(async () => {
    renderer = create(<ModelsPage />);
  });

  expect(getTeamModels).toHaveBeenCalledWith("team-1");
  const paragraphs = renderer!.root
    .findAllByType("p")
    .map((node) => node.children.join(""));
  expect(paragraphs).toContain("models.noModels");
  expect(paragraphs).toContain("models.createModelHint");
  act(() => renderer!.unmount());
});
