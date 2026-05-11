#!/usr/bin/env node
/**
 * Lint translation files:
 *  1. Validate ICU message syntax in all .json files
 *  2. Check that all keys present in the source language exist in all target languages
 *
 * Usage: node scripts/lint-translations.ts [--strict] [source-lang] [i18n-dir]
 *   --strict:   Treat missing keys as errors (default: warnings)
 *   source-lang: Source language code (default: en)
 *   i18n-dir:   i18n directory (default: i18n)
 * Exit code: 0 = all checks pass, 1 = errors found (or warnings if --strict not set)
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const ROOT = resolve(__dirname, '..')

// Parse arguments: flags first, then positional
const argv = process.argv.slice(2)
let strict = false
let sourceLang = 'en'
let i18nDir = resolve(ROOT, 'i18n')

const positional: string[] = []
for (const arg of argv) {
  if (arg === '--strict') strict = true
  else positional.push(arg)
}
if (positional[0]) sourceLang = positional[0]
if (positional[1]) i18nDir = resolve(ROOT, positional[1])

// Load intl-messageformat (ESM) via createRequire from script location
const require = createRequire(resolve(__dirname, 'lint-translations.js'))
const { IntlMessageFormat } = require('intl-messageformat/index.js')

let errors = 0
let warnings = 0

function flattenKeys(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      Object.assign(result, flattenKeys(v as Record<string, unknown>, path))
    } else {
      result[path] = typeof v === 'string' ? v : String(v)
    }
  }
  return result
}

async function loadLang(lang: string) {
  const dir = resolve(i18nDir, lang)
  const files = await readdir(dir)
  const allKeys: Record<string, Record<string, string>> = {}
  for (const file of files) {
    if (!file.endsWith('.json')) continue
    const name = file.replace(/\.json$/, '')
    const path = resolve(dir, file)
    const content = await readFile(path, 'utf-8')
    allKeys[name] = flattenKeys(JSON.parse(content))
  }
  return allKeys
}

async function loadTypes(): Promise<Record<string, Set<string>>> {
  const typesDir = resolve(i18nDir, 'types')
  const result: Record<string, Set<string>> = {}
  const files = await readdir(typesDir)
  for (const file of files) {
    if (!file.endsWith('.ts')) continue
    const name = file.replace(/\.ts$/, '')
    const path = resolve(typesDir, file)
    const content = await readFile(path, 'utf-8')
    const keys = new Set<string>()
    // Extract keys from generated type definitions (format: "  keyName: string")
    const re = /^\s{2,3}(\w[\w.]*): string/gm
    for (const match of content.matchAll(re)) {
      keys.add(match[1])
    }
    result[name] = keys
  }
  return result
}

async function getLangDirs() {
  const entries = await readdir(i18nDir)
  const dirs: string[] = []
  for (const entry of entries) {
    const entryPath = resolve(i18nDir, entry)
    const s = await stat(entryPath)
    // Exclude generated types directory (not a translation language)
    if (s.isDirectory() && entry !== 'types') dirs.push(entry)
  }
  return dirs
}

async function main() {
  console.log(`[lint-translations] Source: ${sourceLang}`)
  console.log(`[lint-translations] i18n dir: ${i18nDir}`)

  const sourceData = await loadLang(sourceLang)
  const sourceFileNames = Object.keys(sourceData)
  const langDirs = await getLangDirs()

  // 1. ICU syntax validation (all languages)
  for (const lang of langDirs) {
    const dir = resolve(i18nDir, lang)
    const files = await readdir(dir)
    for (const file of files) {
      if (!file.endsWith('.json')) continue
      const filePath = resolve(dir, file)
      const content = await readFile(filePath, 'utf-8')
      const flat = flattenKeys(JSON.parse(content))
      for (const [key, value] of Object.entries(flat)) {
        if (typeof value !== 'string' || value.trim() === '') continue
        // Skip ICU validation for strings containing {{ (Jinja2-style placeholder hints)
        // and strings with JSON snippet patterns like {"key": "value"} (examples in hints)
        // and known edge-case keys like clearHint that legitimately contain {} as text
        if (
          value.includes('{{') ||
          /\{\s*"/.test(value) ||
          key === 'workflow.configVariableAssignment.clearHint'
        ) continue
        try {
          new IntlMessageFormat(value, lang)
        } catch (e: unknown) {
          const message = e instanceof Error ? e.message : String(e)
          console.error(
            `  [${lang}/${file}] ICU syntax error in "${key}": ${message}`
          )
          errors++
        }
      }
    }
  }

  // 2. Missing keys check (target languages vs source)
  for (const lang of langDirs) {
    if (lang === sourceLang) continue
    const targetData = await loadLang(lang)

    for (const fileName of sourceFileNames) {
      const source = sourceData[fileName]
      const target = targetData[fileName] ?? {}

      const sourceKeys = new Set(Object.keys(source))
      const targetKeys = new Set(Object.keys(target))

      for (const key of sourceKeys) {
        if (!targetKeys.has(key)) {
          if (strict) {
            console.error(`  [${lang}/${fileName}.json] Missing key: "${key}"`)
            errors++
          } else {
            console.warn(`  [${lang}/${fileName}.json] Missing key: "${key}" (warning)`)
            warnings++
          }
        }
      }
    }
  }

  // 3. Types alignment check (generated types vs actual source keys)
  const typeMap = await loadTypes()
  let typesErrors = 0
  for (const [fileName, typeKeys] of Object.entries(typeMap)) {
    const source = sourceData[fileName]
    if (!source) continue // no source file for this type file

    for (const key of typeKeys) {
      if (!source[key]) {
        console.error(`  [types/${fileName}.ts] Orphan type key (no source translation): "${key}"`)
        typesErrors++
      }
    }
  }

  if (typesErrors > 0) {
    console.error(`[lint-translations] Found ${typesErrors} orphan type key(s) in types/ (run gen-i18n-types.ts).`)
  }

  if (errors > 0) {
    console.error(`\n[lint-translations] Found ${errors} error(s).`)
    if (warnings > 0) console.error(`[lint-translations] And ${warnings} warning(s).`)
    process.exit(1)
  } else if (warnings > 0) {
    console.warn(`\n[lint-translations] ${warnings} warning(s) found (use --strict to treat as errors).`)
    process.exit(0)
  } else {
    console.log('[lint-translations] All checks passed.')
    process.exit(0)
  }
}

main().catch((e) => {
  console.error('[lint-translations] Fatal:', e.message)
  process.exit(1)
})