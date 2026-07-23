import { expect, mock, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/font/local", () => ({
  default: ({ variable }: { variable: string }) => ({ variable }),
}));
mock.module("next-intl", () => ({
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
mock.module("next-intl/server", () => ({
  getLocale: () => Promise.resolve("zh"),
  getMessages: () => Promise.resolve({ platform: {} }),
  getTranslations: () => Promise.resolve((key: string) => `platform.${key}`),
}));
mock.module("@/components/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
mock.module("@/components/ui/sonner", () => ({
  Toaster: (props: Record<string, unknown>) => <div data-toaster={JSON.stringify(props)} />,
}));
mock.module("./globals.css", () => ({}));

const { default: RootLayout, generateMetadata } = await import("./layout");

test("builds localized metadata and theme-aware icons", async () => {
  const metadata = await generateMetadata();

  expect(metadata.title).toBe("Clouisle - platform.admin");
  expect(metadata.description).toBe("platform.home.description");
  expect(metadata.icons).toEqual({
    icon: [
      { url: "/clouisle-light.svg", type: "image/svg+xml", media: "(prefers-color-scheme: light)" },
      { url: "/clouisle-dark.svg", type: "image/svg+xml", media: "(prefers-color-scheme: dark)" },
    ],
  });
});

test("renders the localized document shell with providers and toaster", async () => {
  const html = renderToStaticMarkup(
    await RootLayout({ children: <main>Workspace</main> }),
  );

  expect(html).toContain('<html lang="zh"');
  expect(html).toContain("--font-geist-sans");
  expect(html).toContain("--font-geist-mono");
  expect(html).toContain("Workspace");
  expect(html).toContain("top-center");
});
