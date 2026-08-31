import { afterEach, beforeAll, describe, expect, it, mock } from "bun:test";
import { Window } from "happy-dom";
import * as React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const window = new Window({ url: "http://localhost" });
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLButtonElement: window.HTMLButtonElement,
  getComputedStyle: window.getComputedStyle,
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: clearTimeout,
});

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
mock.module("lucide-react", () => ({
  CheckCircleIcon: () => <svg />,
  ChevronDownIcon: () => <svg />,
  CircleIcon: () => <svg />,
  ClockIcon: () => <svg />,
  WrenchIcon: () => <svg />,
  XCircleIcon: () => <svg />,
}));
mock.module("./code-block", () => ({
  CodeBlock: ({ code }: { code: string }) => <pre>{code}</pre>,
}));

let Tool: typeof import("./tool").Tool;
let ToolContent: typeof import("./tool").ToolContent;
let ToolHeader: typeof import("./tool").ToolHeader;
let ToolOutput: typeof import("./tool").ToolOutput;

beforeAll(async () => {
  ({ Tool, ToolContent, ToolHeader, ToolOutput } = await import("./tool"));
});

const roots: Root[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount());
  document.body.replaceChildren();
});

function render(element: React.ReactNode) {
  const container = document.body.appendChild(document.createElement("div"));
  const root = createRoot(container);
  roots.push(root);
  act(() => root.render(element));
  return container;
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    return this.state.error ? <div role="alert">{this.state.error.message}</div> : this.props.children;
  }
}

describe("Tool", () => {
  it("toggles its content and announces tool status", () => {
    const container = render(
      <Tool>
        <ToolHeader type="tool-weather" state="output-available" />
        <ToolContent>Forecast</ToolContent>
      </Tool>
    );

    const trigger = container.querySelector("button")!;
    expect(trigger.textContent).toContain("weather");
    expect(trigger.textContent).toContain("completed");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(container.textContent).not.toContain("Forecast");

    act(() => trigger.click());
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(container.textContent).toContain("Forecast");
  });

  it("keeps sibling tool disclosures independent", () => {
    const container = render(
      <div>
        <Tool>
          <ToolHeader type="tool-weather" state="output-available" />
          <ToolContent>First details</ToolContent>
        </Tool>
        <Tool>
          <ToolHeader type="tool-search" state="output-available" />
          <ToolContent>Second details</ToolContent>
        </Tool>
      </div>
    );

    const triggers = container.querySelectorAll("button");
    expect(triggers).toHaveLength(2);
    expect(triggers[0].getAttribute("aria-expanded")).toBe("false");
    expect(triggers[1].getAttribute("aria-expanded")).toBe("false");

    act(() => triggers[0].click());
    expect(triggers[0].getAttribute("aria-expanded")).toBe("true");
    expect(triggers[1].getAttribute("aria-expanded")).toBe("false");
    expect(container.textContent).toContain("First details");
    expect(container.textContent).not.toContain("Second details");

    act(() => triggers[1].click());
    expect(triggers[1].getAttribute("aria-expanded")).toBe("true");
    expect(container.textContent).toContain("Second details");
  });

  it("renders error text and serialized output", () => {
    const container = render(<ToolOutput errorText="Request failed" output={{ retry: false }} />);

    expect(container.textContent).toContain("error");
    expect(container.textContent).toContain("Request failed");
    expect(container.querySelector("pre")?.textContent).toContain('"retry": false');
  });

  it("surfaces missing Tool context to an error boundary", () => {
    const container = render(
      <ErrorBoundary>
        <ToolHeader type="tool-weather" state="output-error" />
      </ErrorBoundary>
    );

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Tool components must be used within Tool");
  });
});
