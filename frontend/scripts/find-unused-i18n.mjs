#!/usr/bin/env node
/**
 * Unused i18n translation key scanner.
 * Identifies keys in frontend/i18n/en/*.json that are never referenced
 * either as direct translation calls, template strings, or object property lookups in code.
 *
 * Usage:
 *   node scripts/find-unused-i18n.mjs
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
      !entry.name.endsWith('.d.ts')
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

    let openBrace = content.lastIndexOf('{', declIndex)
    let blockEnd = content.length
    if (openBrace !== -1) {
      let depth = 1
      for (let i = openBrace + 1; i < content.length; i++) {
        if (content[i] === '{') depth++
        else if (content[i] === '}') {
          depth--
          if (depth === 0) {
            blockEnd = i
            break
          }
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

  console.log('📂 Scanning source files for translation calls and references...')
  const sourceFiles = await collectSourceFiles(ROOT)
  console.log(`Found ${sourceFiles.length} source files to check.`)

  const usedKeys = new Set()
  const allContentBlocks = []

  const callRegex = /\b(\w+)\(\s*['"]([a-zA-Z0-9_.-]+)['"]/g

  for (const filePath of sourceFiles) {
    const content = await readFile(filePath, 'utf-8')
    allContentBlocks.push(content)
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

      usedKeys.add(`${activeScope.namespace}.${subKey}`)
    }
  }

  const combinedContent = allContentBlocks.join('\n')

  // Analyze unreferenced keys
  // Some keys are dynamic or referenced directly by string (e.g. error codes, backend messages, full paths)
  const unused = []
  for (const key of enKeys) {
    if (usedKeys.has(key)) continue

    const parts = key.split('.')
    const leaf = parts[parts.length - 1]
    const parentLeaf = parts.length > 2 ? `${parts[parts.length - 2]}.${leaf}` : null

    // Check if full key or parent.leaf or exact leaf is referenced anywhere in code
    const isReferenced =
      combinedContent.includes(`'${key}'`) ||
      combinedContent.includes(`"${key}"`) ||
      (parentLeaf && (combinedContent.includes(`'${parentLeaf}'`) || combinedContent.includes(`"${parentLeaf}"`))) ||
      combinedContent.includes(`'${leaf}'`) ||
      combinedContent.includes(`"${leaf}"`) ||
      combinedContent.includes(`\`${leaf}\``)

    if (!isReferenced) {
      unused.push(key)
    }
  }

  console.log(`\n📊 Translation Usage Summary:`)
  console.log(`   Total defined keys: ${enKeys.size}`)
  console.log(`   Directly verified used keys: ${usedKeys.size}`)
  console.log(`   Candidate unused/orphan keys: ${unused.length}`)

  if (unused.length > 0) {
    console.log(`\n⚠️  The following ${unused.length} keys appear to be unreferenced in the codebase:\n`)
    // Group by top-level namespace
    const byNamespace = new Map()
    for (const key of unused) {
      const ns = key.split('.')[0]
      if (!byNamespace.has(ns)) byNamespace.set(ns, [])
      byNamespace.get(ns).push(key)
    }

    for (const [ns, keys] of byNamespace.entries()) {
      console.log(`📁 [${ns}] (${keys.length} unreferenced):`)
      for (const k of keys.slice(0, 10)) {
        console.log(`   - ${k}`)
      }
      if (keys.length > 10) {
        console.log(`   ... and ${keys.length - 10} more`)
      }
      console.log()
    }
  } else {
    console.log('🎉 No unused keys found!')
  }
}

main().catch((err) => {
  console.error('Fatal scanner error:', err)
  process.exit(1)
})
