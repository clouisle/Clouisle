import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let pathname = "/app";

mock.module("next/navigation", () => ({ usePathname: () => pathname }));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "zh",
}));
const boundary = ({ children }: React.PropsWithChildren) => <>{children}</>;
mock.module("@/components/layout/platform-header", () => ({
  PlatformHeader: () => <div data-testid="platform-header" />,
}));
mock.module("@/contexts/team-context", () => ({
  TeamProvider: boundary,
  useTeam: () => ({ currentTeam: null }),
}));
mock.module("@/components/password-expiration-banner", () => ({
  PasswordExpirationBanner: () => <div data-testid="password-banner" />,
}));
mock.module("@/components/auth-guard", () => ({ AuthGuard: boundary }));
mock.module("@/components/onboarding/onboarding-provider", () => ({ OnboardingProvider: boundary }));
mock.module("@/components/onboarding/onboarding-tour", () => ({
  allTourIds: ["welcome"],
  OnboardingTour: ({ tourId }: { tourId: string }) => <div data-tour={tourId} />,
}));
mock.module("@/components/watermark/global-watermark", () => ({
  GlobalWatermark: () => <div data-testid="watermark" />,
}));

const { default: PlatformLayout } = await import("./layout");

test("uses normal scrolling layout outside workflow editor routes", () => {
  pathname = "/app/apps";
  const html = renderToStaticMarkup(<PlatformLayout>content</PlatformLayout>);

  expect(html).toContain('data-testid="platform-header"');
  expect(html).toContain("overflow-y-auto");
  expect(html).toContain('data-tour="welcome"');
});

test("hides the header and locks scrolling in a workflow editor", () => {
  pathname = "/app/apps/workflow/workflow-1";
  const html = renderToStaticMarkup(<PlatformLayout>editor</PlatformLayout>);

  expect(html).not.toContain('data-testid="platform-header"');
  expect(html).toContain("relative overflow-hidden");
  expect(html).toContain('data-tour="welcome"');
});
