#!/usr/bin/env node
/**
 * Project-wide i18n usage scanner.
 * Scans all TS/TSX source files, parses useTranslations / getTranslations calls,
 * resolves lexical scope of translation functions (handling shadowing across components/functions),
 * and verifies that all accessed translation keys exist in frontend/i18n/en/<namespace>.json.
 *
 * Usage:
 *   node scripts/check-i18n-usage.mjs
 */

import { readdir, readFile } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const ROOT = resolve(__dirname, '..')
const I18N_DIR = resolve(ROOT, 'i18n')

function flattenKeys(obj, prefix = '') {
  const result = new Set()
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      for (const nested of flattenKeys(v, path)) {
        result.add(nested)
      }
    } else {
      result.add(path)
    }
  }
  return result
}

async function loadEnKeys() {
  const dir = resolve(I18N_DIR, 'en')
  const files = await readdir(dir)
  const allKeys = new Set()
  for (const file of files) {
    if (!file.endsWith('.json')) continue
    const content = await readFile(resolve(dir, file), 'utf-8')
    const json = JSON.parse(content)
    for (const key of flattenKeys(json)) {
      allKeys.add(key)
    }
  }
  return allKeys
}

async function collectSourceFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const res = resolve(dir, entry.name)
    if (entry.isDirectory()) {
      if (
        entry.name === 'node_modules' ||
        entry.name === '.next' ||
        entry.name === 'dist' ||
        entry.name === 'types'
      ) {
        continue
      }
      files.push(...(await collectSourceFiles(res)))
    } else if (
      (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) &&
      !entry.name.endsWith('.d.ts') &&
      !entry.name.includes('.test.') &&
      !entry.name.includes('.spec.')
    ) {
      files.push(res)
    }
  }
  return files
}

function extractScopes(content) {
  const scopes = []
  const useRegex = /(?:const|let|var)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*['"]([^'"]+)['"]\s*\)/g
  let match

  while ((match = useRegex.exec(content)) !== null) {
    const varName = match[1]
    const namespace = match[2]
    const declIndex = match.index

    // Find enclosing function/component body by matching braces backwards skipping literals
    let blockEnd = content.length
    let depth = 0
    let inString = false
    let stringChar = ''
    let inLineComment = false
    let inBlockComment = false

    // Scan forward from declaration to find matching end of the current function block
    for (let i = declIndex; i < content.length; i++) {
      const ch = content[i]
      const nextCh = content[i + 1]

      if (inLineComment) {
        if (ch === '\n') {
          inLineComment = false
        }
        continue
      }
      if (inBlockComment) {
        if (ch === '*' && nextCh === '/') {
          inBlockComment = false
          i++
        }
        continue
      }
      if (inString) {
        if (ch === stringChar && content[i - 1] !== '\\') {
          inString = false
        }
        continue
      }

      if (ch === '/' && nextCh === '/') {
        inLineComment = true
        i++
        continue
      }
      if (ch === '/' && nextCh === '*') {
        inBlockComment = true
        i++
        continue
      }

      if (ch === "'" || ch === '"' || ch === '`') {
        inString = true
        stringChar = ch
        continue
      }
      if (ch === '{') {
        depth++
      } else if (ch === '}') {
        if (depth > 0) {
          depth--
        } else {
          blockEnd = i
          break
        }
      }
    }
    scopes.push({
      start: declIndex,
      end: blockEnd,
      varName,
      namespace,
    })
  }

  return scopes
}

async function main() {
  console.log('🔍 Loading i18n English definitions...')
  const enKeys = await loadEnKeys()
  console.log(`✅ Loaded ${enKeys.size} translation keys.`)

  console.log('📂 Scanning frontend source files...')
  const sourceFiles = await collectSourceFiles(ROOT)
  console.log(`Found ${sourceFiles.length} source files to check.`)

  const missing = []
  let totalChecked = 0

  // Match only complete literal strings: t('some.key'), avoiding dynamic concatenation like t('prefix.' + var)
  const callRegex = /\b(\w+)\(\s*['"]([a-zA-Z0-9_.-]+)['"]\s*[,)]/g

  for (const filePath of sourceFiles) {
    const relPath = relative(ROOT, filePath)
    const content = await readFile(filePath, 'utf-8')
    const scopes = extractScopes(content)

    if (scopes.length === 0) continue

    let match
    callRegex.lastIndex = 0

    while ((match = callRegex.exec(content)) !== null) {
      const fnName = match[1]
      const subKey = match[2]
      const callIndex = match.index

      const matchingScopes = scopes.filter(
        (s) => s.varName === fnName && callIndex >= s.start && callIndex <= s.end
      )

      if (matchingScopes.length === 0) continue

      const activeScope = matchingScopes.reduce((prev, curr) =>
        curr.start > prev.start ? curr : prev
      )

      totalChecked++
      const fullKey = `${activeScope.namespace}.${subKey}`

      if (!enKeys.has(fullKey)) {
        const line = content.slice(0, callIndex).split('\n').length
        missing.push({
          file: relPath,
          line,
          key: fullKey,
          namespace: activeScope.namespace,
          subKey,
        })
      }
    }
  }

  console.log(`\nChecked ${totalChecked} literal translation invocations across the project.`)

  if (missing.length === 0) {
    console.log('🎉 All translation keys exist in frontend/i18n/en/*.json!')
    process.exit(0)
  }

  console.error(`\n❌ Found ${missing.length} missing translation keys:`)
  const byKey = new Map()
  for (const item of missing) {
    if (!byKey.has(item.key)) {
      byKey.set(item.key, [])
    }
    byKey.get(item.key).push({ file: item.file, line: item.line })
  }

  for (const [key, locations] of byKey.entries()) {
    console.error(`\n  • ${key}`)
    for (const loc of locations) {
      console.error(`      at ${loc.file}:${loc.line}`)
    }
  }

  process.exit(1)
}

main().catch((err) => {
  console.error('Fatal scanner error:', err)
  process.exit(1)
})
