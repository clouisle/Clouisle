import { describe, expect, mock, test } from "bun:test";
import type { ReactNode } from "react";

const state: unknown[] = [];
let stateIndex = 0;
const jsx = (type: unknown, props: Record<string, unknown>) => ({
  type,
  props,
});

mock.module("react/jsx-runtime", () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("react/jsx-dev-runtime", () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for("react.fragment"),
}));
mock.module("react", () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++;
    state[index] ??= initial;
    return [
      state[index] as T,
      (value: T) => {
        state[index] = value;
      },
    ] as const;
  },
}));
mock.module("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
mock.module("@/components/ui/collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => children,
  CollapsibleContent: ({ children }: { children: ReactNode }) => children,
  CollapsibleTrigger: ({ children }: { children: ReactNode }) => children,
}));
mock.module("lucide-react", () => ({
  Download: () => null,
  Eye: () => null,
  FileArchive: () => null,
  FileAudio: () => null,
  FileCode: () => null,
  FileIcon: () => null,
  FileImage: () => null,
  FileText: () => null,
  FileVideo: () => null,
}));

// Dynamic import is required so Bun module mocks are registered before file components evaluate.
const { FileContent, FileListContent } = await import("./file-content");

type Tree = { type: unknown; props: Record<string, unknown> };

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== "object" || !("type" in node)) return node;
  const tree = node as Tree;
  return typeof tree.type === "function"
    ? resolve(
        (tree.type as (props: Record<string, unknown>) => ReactNode)(
          tree.props,
        ),
      )
    : tree;
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    const tree = resolve(child);
    if (Array.isArray(tree)) {
      try {
        return find(tree, predicate);
      } catch {
        /* keep searching */
      }
      continue;
    }
    if (!tree || typeof tree !== "object" || !("type" in tree)) continue;
    if (predicate(tree as Tree)) return tree as Tree;
    try {
      return find((tree as Tree).props.children as ReactNode, predicate);
    } catch {
      /* keep searching */
    }
  }
  throw new Error("Element not found");
}

function render<T>(component: () => T) {
  stateIndex = 0;
  return component();
}

describe("file message parts", () => {
  test("shows formatted metadata and a download action for downloadable files", () => {
    const tree = render(() =>
      FileContent({
        file: {
          type: "file",
          filename: "data.json",
          url: "https://files.test/data.json",
          mimeType: "application/json",
          size: 1536,
        },
      }),
    );

    expect(JSON.stringify(tree)).toContain("1.5 KB");
    expect(find(tree, (node) => node.type === "a").props).toMatchObject({
      href: "https://files.test/data.json",
      download: "data.json",
    });
  });

  test("opens downloadable files in the side preview", () => {
    const onPreview = mock(() => {});
    const file = {
      type: "file" as const,
      filename: "data.json",
      url: "https://files.test/data.json",
      mimeType: "application/json",
    };
    const tree = render(() => FileContent({ file, onPreview }));
    const previewButton = find(
      tree,
      (node) => node.type === "button" && node.props["aria-label"] === "openCodePreview: data.json",
    );

    const onClick = previewButton.props.onClick;
    if (typeof onClick !== "function") throw new Error("preview button is not clickable");
    onClick();
    expect(onPreview).toHaveBeenCalledWith(file);
  });

  test("renders image previews and separates image files from other attachments", () => {
    const files = [
      {
        type: "file" as const,
        filename: "photo.png",
        url: "https://files.test/photo.png",
        mimeType: "image/png",
      },
      {
        type: "file" as const,
        filename: "archive.zip",
        mimeType: "application/zip",
      },
    ];
    const tree = render(() => FileListContent({ files }));

    expect(JSON.stringify(tree)).toContain("photo.png");
    expect(JSON.stringify(tree)).toContain("archive.zip");
    expect(
      find(
        tree,
        (node) => node.type === "img" && node.props.alt === "photo.png",
      ).props.src,
    ).toBe("https://files.test/photo.png");
  });

  test("renders an expandable image attachment preview", () => {
    const tree = render(() =>
      FileContent({
        file: {
          type: "file",
          filename: "photo.png",
          url: "https://files.test/photo.png",
          mimeType: "image/png",
        },
      }),
    );

    expect(
      find(
        tree,
        (node) => node.type === "img" && node.props.alt === "photo.png",
      ).props.src,
    ).toBe("https://files.test/photo.png");
  });

  test.each([
    ["text/plain", "note.txt"],
    ["video/mp4", "video.mp4"],
    ["audio/mpeg", "sound.mp3"],
    ["application/javascript", "script.js"],
    ["application/gzip", "archive.gz"],
    [undefined, "unknown.bin"],
  ])(
    "renders %s file metadata without a download URL",
    (mimeType, filename) => {
      const tree = render(() =>
        FileContent({ file: { type: "file", filename, mimeType } }),
      );

      expect(JSON.stringify(tree)).toContain(filename);
    },
  );

  test("does not render an empty attachment list", () => {
    expect(render(() => FileListContent({ files: [] }))).toBeNull();
  });
});
