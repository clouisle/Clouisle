"use client";
import {
  CodeBlock as BaseCodeBlock,
  CodeBlockActions,
  CodeBlockContent,
  CodeBlockCopyButton as BaseCodeBlockCopyButton,
} from "@/components/ui/code-block";
import { cn } from "@/lib/utils";
import {
  type ComponentProps,
  createContext,
  type HTMLAttributes,
  useContext,
  useEffect,
  useState,
} from "react";
import { type BundledLanguage, codeToHtml, type ShikiTransformer } from "shiki";

type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  code: string;
  language: BundledLanguage;
  showLineNumbers?: boolean;
};

type CodeBlockContextType = {
  code: string;
};

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: "",
});

const lineNumberTransformer: ShikiTransformer = {
  name: "line-numbers",
  line(node, line) {
    node.children.unshift({
      type: "element",
      tagName: "span",
      properties: {
        className: [
          "inline-block",
          "min-w-10",
          "mr-4",
          "text-right",
          "select-none",
          "text-muted-foreground",
        ],
      },
      children: [{ type: "text", value: String(line) }],
    });
  },
};

export async function highlightCode(
  code: string,
  language: BundledLanguage,
  showLineNumbers = false
) {
  const transformers: ShikiTransformer[] = showLineNumbers
    ? [lineNumberTransformer]
    : [];

  return await Promise.all([
    codeToHtml(code, {
      lang: language,
      theme: "one-light",
      transformers,
    }),
    codeToHtml(code, {
      lang: language,
      theme: "one-dark-pro",
      transformers,
    }),
  ]);
}

function getCodeHtml(html: string) {
  const code = /<code\b[^>]*>([\s\S]*?)<\/code>/.exec(html);
  if (code) return code[1];

  return html.replace(/^<pre\b[^>]*>/, "").replace(/<\/pre>$/, "");
}

export const CodeBlock = ({
  code,
  language,
  showLineNumbers = false,
  className,
  children,
  ...props
}: CodeBlockProps) => {
  const [html, setHtml] = useState<string>("");
  const [darkHtml, setDarkHtml] = useState<string>("");

  useEffect(() => {
    let active = true;
    highlightCode(code, language, showLineNumbers).then(([light, dark]) => {
      if (active) {
        setHtml(getCodeHtml(light));
        setDarkHtml(getCodeHtml(dark));
      }
    });

    return () => {
      active = false;
    };
  }, [code, language, showLineNumbers]);

  return (
    <CodeBlockContext.Provider value={{ code }}>
      <BaseCodeBlock className={cn("overflow-hidden", className)} {...props}>
        {children && <CodeBlockActions>{children}</CodeBlockActions>}
        <CodeBlockContent
          data-theme="one-light"
          className="overflow-auto dark:hidden [&>code]:font-mono [&>code]:text-sm"
        >
          <code dangerouslySetInnerHTML={{ __html: html }} />
        </CodeBlockContent>
        <CodeBlockContent
          data-theme="one-dark-pro"
          className="hidden overflow-auto dark:block [&>code]:font-mono [&>code]:text-sm"
        >
          <code dangerouslySetInnerHTML={{ __html: darkHtml }} />
        </CodeBlockContent>
      </BaseCodeBlock>
    </CodeBlockContext.Provider>
  );
};

export type CodeBlockCopyButtonProps = ComponentProps<typeof BaseCodeBlockCopyButton> & {
  onCopy?: () => void;
  onError?: (error: Error) => void;
  timeout?: number;
};

export const CodeBlockCopyButton = ({
  children,
  ...props
}: CodeBlockCopyButtonProps) => {
  const { code } = useContext(CodeBlockContext);

  return (
    <BaseCodeBlockCopyButton value={code} {...props}>
      {children}
    </BaseCodeBlockCopyButton>
  );
};

