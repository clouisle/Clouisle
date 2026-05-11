#!/usr/bin/env node
/**
 * Generate TypeScript type definitions from source language JSON files.
 * Output: i18n/types/index.ts (plus per-file .ts in the same dir)
 *
 * Usage: node scripts/gen-i18n-types.ts [source-lang] [output-dir]
 *   source-lang: Language code (default: en)
 *   output-dir:  Output directory (default: i18n/types)
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises'
import { resolve, join, basename } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const ROOT = resolve(__dirname, '..')
const SOURCE_LANG = process.argv[2] ?? 'en'
const OUTPUT_DIR = resolve(ROOT, process.argv[3] ?? 'i18n/types')

function buildType(value: unknown, indent = 0): string {
  const pad = '  '.repeat(indent)
  if (typeof value === 'string') return 'string'
  if (typeof value === 'number') return 'number'
  if (typeof value === 'boolean') return 'boolean'
  if (value === null) return 'null'
  if (Array.isArray(value)) {
    if (value.length === 0) return 'string[]'
    const itemType = buildType(value[0], 0)
    return `${itemType}[]`
  }
  if (typeof value === 'object' && value !== null) {
    const objectValue = value as Record<string, unknown>
    const keys = Object.keys(objectValue)
    if (keys.length === 0) return 'Record<string, unknown>'
    const inner = keys
      .map((k) => {
        const safeKey = /^[a-zA-Z_$][a-zA-Z0-9_$]*$/.test(k) ? k : JSON.stringify(k)
        return `${pad}  ${safeKey}: ${buildType(objectValue[k], indent + 1)}`
      })
      .join('\n')
    return `{\n${inner}\n${pad}}`
  }
  return 'unknown'
}

function toPascalCase(str: string): string {
  return str
    .replace(/[-_\s]+(.)/g, (_, c) => c.toUpperCase())
    .replace(/^(.)/, (c) => c.toUpperCase())
}

async function main() {
  const sourceDir = resolve(ROOT, 'i18n', SOURCE_LANG)
  const files = await readdir(sourceDir)

  await mkdir(OUTPUT_DIR, { recursive: true })

  const indexLines = [
    '// GENERATED FILE — do not edit manually',
    '// Run: bun run scripts/gen-i18n-types.ts',
    '',
  ]

  for (const file of files) {
    if (!file.endsWith('.json')) continue
    const name = basename(file, '.json')
    const safeName = toPascalCase(name)
    const filePath = join(sourceDir, file)
    const content = await readFile(filePath, 'utf-8')
    const data = JSON.parse(content)

    const typeStr = buildType(data)
    const outFile = join(OUTPUT_DIR, `${name}.ts`)
    await writeFile(
      outFile,
      `// GENERATED — ${new Date().toISOString()}\n` +
        `// Source: i18n/${SOURCE_LANG}/${file}\n` +
        `export type ${safeName}Messages = ${typeStr}\n`,
      'utf-8'
    )

    indexLines.push(`export type { ${safeName}Messages } from './${name}.js'`)
  }

  await writeFile(
    join(OUTPUT_DIR, 'index.ts'),
    indexLines.join('\n') + '\n',
    'utf-8'
  )

  console.log(`[gen-i18n-types] Generated types for ${SOURCE_LANG} → ${OUTPUT_DIR}`)
}

main().catch((e) => {
  console.error('[gen-i18n-types] Error:', e.message)
  process.exit(1)
})
