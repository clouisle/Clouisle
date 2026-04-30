'use client'

import * as React from 'react'
import { Check, Copy, Download, X } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Streamdown } from 'streamdown'
import { bundledLanguages } from 'shiki'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CodeBlock } from '@/components/ai-elements/code-block'
import type { CodePreviewPayload } from './types'
import type { BundledLanguage } from 'shiki'

function escapeClosingScriptTag(code: string) {
  return code.replace(/<\/script/gi, '<\\/script')
}

function getSourceLanguage(preview: CodePreviewPayload): BundledLanguage | null {
  if (preview.kind === 'source') {
    return preview.language in bundledLanguages ? preview.language as BundledLanguage : null
  }

  switch (preview.kind) {
    case 'html':
      return 'html'
    case 'svg':
      return 'xml'
    case 'css':
      return 'css'
    case 'javascript':
      return 'javascript'
    case 'markdown':
      return 'markdown'
  }
}

function getDownloadExtension(preview: CodePreviewPayload) {
  const language = preview.language.toLowerCase()
  const extensionByLanguage: Record<string, string> = {
    html: 'html',
    htm: 'html',
    xhtml: 'html',
    svg: 'svg',
    xml: 'xml',
    css: 'css',
    js: 'js',
    javascript: 'js',
    mjs: 'mjs',
    markdown: 'md',
    md: 'md',
    ts: 'ts',
    typescript: 'ts',
    tsx: 'tsx',
    jsx: 'jsx',
    json: 'json',
    python: 'py',
    py: 'py',
    go: 'go',
    rust: 'rs',
    rs: 'rs',
    java: 'java',
    sql: 'sql',
    sh: 'sh',
    bash: 'sh',
    yaml: 'yaml',
    yml: 'yml',
  }

  return extensionByLanguage[language] ?? 'txt'
}

function buildPreviewDocument(preview: CodePreviewPayload) {
  switch (preview.kind) {
    case 'html':
      return preview.code
    case 'svg':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body { min-height: 100%; margin: 0; background: #fff; }
    body { display: grid; place-items: center; padding: 24px; box-sizing: border-box; }
    svg { max-width: 100%; height: auto; }
  </style>
</head>
<body>${preview.code}</body>
</html>`
    case 'css':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; padding: 32px; font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; }
    .preview-card { max-width: 720px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 16px; background: white; padding: 24px; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08); }
    .preview-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
    button, input { border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 14px; font: inherit; }
    button { cursor: pointer; background: #0f172a; color: white; }
    ${preview.code}
  </style>
</head>
<body>
  <main class="preview-card">
    <p class="preview-kicker">CSS Preview</p>
    <h1>Preview Card</h1>
    <p>This sample page provides headings, paragraphs, buttons, cards, lists, and form controls for the CSS block.</p>
    <ul>
      <li>First sample item</li>
      <li>Second sample item</li>
    </ul>
    <div class="preview-actions">
      <button>Primary button</button>
      <input placeholder="Sample input" />
    </div>
  </main>
</body>
</html>`
    case 'javascript':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; padding: 32px; font-family: system-ui, sans-serif; background: #fff; color: #111827; }
    #console { margin-top: 24px; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
    #console-title { background: #f3f4f6; padding: 10px 12px; font-weight: 600; font-size: 13px; }
    #console-output { min-height: 64px; padding: 12px; white-space: pre-wrap; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .warn { color: #b45309; }
    .error { color: #dc2626; }
  </style>
</head>
<body>
  <h1>JavaScript Preview</h1>
  <p>The script runs in this sandboxed iframe.</p>
  <div id="console">
    <div id="console-title">Console</div>
    <div id="console-output"></div>
  </div>
  <script>
    const output = document.getElementById('console-output');
    const write = (type, args) => {
      const line = document.createElement('div');
      line.className = type;
      line.textContent = args.map((value) => {
        if (typeof value === 'string') return value;
        try { return JSON.stringify(value); } catch { return String(value); }
      }).join(' ');
      output.appendChild(line);
    };
    ['log', 'warn', 'error'].forEach((type) => {
      const original = console[type].bind(console);
      console[type] = (...args) => {
        write(type, args);
        original(...args);
      };
    });
    window.addEventListener('error', (event) => write('error', [event.message]));
  </script>
  <script>${escapeClosingScriptTag(preview.code)}</script>
</body>
</html>`
    default:
      return ''
  }
}

export function CodePreviewCanvas({
  preview,
  onClose,
}: {
  preview: CodePreviewPayload
  onClose: () => void
}) {
  const t = useTranslations('chat.message')
  const sourceLanguage = getSourceLanguage(preview)
  const [copied, setCopied] = React.useState(false)
  const [activeTab, setActiveTab] = React.useState(preview.kind === 'source' ? 'source' : 'preview')
  const srcDoc = React.useMemo(() => (
    preview.kind === 'markdown' || preview.kind === 'source' ? '' : buildPreviewDocument(preview)
  ), [preview])

  React.useEffect(() => {
    setActiveTab(preview.kind === 'source' ? 'source' : 'preview')
  }, [preview])

  const handleCopy = React.useCallback(async () => {
    await navigator.clipboard.writeText(preview.code)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }, [preview.code])

  const handleDownload = React.useCallback(() => {
    const blob = new Blob([preview.code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `code.${getDownloadExtension(preview)}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }, [preview])

  return (
    <div className="flex h-full min-w-0 flex-col border-l bg-background">
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{t('codePreviewCanvasTitle')}</div>
          <div className="truncate text-xs text-muted-foreground">{preview.language}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleCopy} title={copied ? t('copied') : t('copy')}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleDownload} title={t('mermaidDownloadLabel')}>
            <Download className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose} title={t('closeCodePreview')}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="min-h-0 flex-1 gap-0">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-2">
          <TabsList>
            {preview.kind !== 'source' && (
              <TabsTrigger value="preview">{t('codePreview')}</TabsTrigger>
            )}
            <TabsTrigger value="source">{t('codeSource')}</TabsTrigger>
          </TabsList>
          {preview.kind !== 'markdown' && preview.kind !== 'source' && (
            <span className="hidden text-xs text-muted-foreground lg:inline">
              {t('previewScriptsEnabled')}
            </span>
          )}
        </div>

        {preview.kind !== 'source' && (
          <TabsContent value="preview" className="min-h-0 overflow-hidden p-0">
            {preview.kind === 'markdown' ? (
              <div className="h-full overflow-auto p-6">
                <Streamdown>{preview.code}</Streamdown>
              </div>
            ) : (
              <iframe
                title={t('codePreview')}
                sandbox="allow-scripts"
                srcDoc={srcDoc}
                className="h-full w-full border-0 bg-white"
              />
            )}
          </TabsContent>
        )}

        <TabsContent value="source" className="min-h-0 overflow-auto p-0">
          {sourceLanguage ? (
            <CodeBlock
              code={preview.code}
              language={sourceLanguage}
              showLineNumbers
              className="h-full rounded-none border-0 [&>div]:h-full [&>div>div]:h-full [&_pre]:min-h-full"
            />
          ) : (
            <pre className="h-full overflow-auto p-4 text-sm"><code>{preview.code}</code></pre>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
